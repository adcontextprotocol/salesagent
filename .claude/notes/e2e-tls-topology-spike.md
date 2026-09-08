# Design spike: one test environment, in-network, https both directions

Status: proposed. Owner decision recorded 2026-08-05.
Epic: `salesagent-amht` (close SSRF completely — the seam's two methods are the only URL policy).

## The problem

Three worktrees each grew the slice of TLS their own feature needed, and nobody
asked what the test environment *is*:

| worktree | branch | what it built | what it left |
|---|---|---|---|
| a3-signing | `feat/rfc9421-request-signing` | generated private CA + one nginx front for the main server (`proxy.adcp.test:8443`) + `E2E_CA_BUNDLE` for **test-side** clients | `CREATIVE_AGENT_URL: http://…`, `ADCP_WEBHOOK_HOST: tests`, **no production-side CA trust at all** |
| a2-fetch | `feat/secure-outbound-fetch` | `SSL_CERT_FILE` → combined CA so **production** code verifies; a *second copy* of the nginx front for creative-agent; in-process TLS for the webhook capture | one nginx per upstream; capture is not a service |
| main | — | — | — |

Both halves of the same chain exist, in different worktrees, and neither branch
has both. a3 verifies **inbound** (client → our server). a2 verifies
**outbound** (our seam → an origin). Signing needs outbound too — it fetches a
counterparty's JWKS — so a3's chain is incomplete by its own requirements.

### Evidence

`a3:tests/e2e/test_jwks_publication_e2e.py` documents the gap rather than
fixing it:

> the SDK's THIRD hop is `async_default_jwks_fetcher`, which builds its own
> `httpx.AsyncClient` with `trust_env=False` and takes no client-factory seam
> (`_brand_jwks_client_factory` reaches hop 2 only). Against a leaf signed by the
> private e2e CA that hop can only ever raise `jwks_fetch_failed` — a RIG failure
> whose one obvious "fix" is `verify=False`

a3 has **no** `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` anywhere; `E2E_CA_BUNDLE`
is read only by `tests/e2e/conftest.py`, `tests/bdd/conftest.py`,
`tests/e2e/_signing_e2e.py` — all test-side.

## Why the topology is one-nginx-per-upstream today

Not a compose limitation. **A compose service can carry any number of network
aliases.** The constraint is self-inflicted:
`config/nginx/nginx-tls-test.conf.template` has a single `${TLS_UPSTREAM}` and
no `server_name`, so one container serves exactly one upstream. The topology
followed the template. The `# compose network aliases are per-SERVICE` comment
at `docker-compose.e2e.yml` (tls-proxy-creative block) is **wrong as written**
and must be deleted with the service.

The cert is already a `*.adcp.test` wildcard, so SNI routing across many names
needs no new material.

## Target design

### 1. One nginx, N names, N upstreams

One `tls-proxy` service carrying every alias, with the upstream chosen by the
requested name:

```nginx
map $ssl_server_name $tls_upstream {
    proxy.adcp.test           adcp-server:8080;
    creative-agent.adcp.test  creative-agent:8080;
    webhooks.adcp.test        webhook-capture:8080;
}
```

Adding an origin is one map line and one alias. This is the real-life shape:
one edge, many virtual hosts.

Shared `ssl_*` / `proxy_set_header` boilerplate goes in an nginx `include`
snippet so the shared config and the per-worker sidecar template do not carry
two copies (DRY invariant — the reason we are here at all).

### 2. The per-worker bdd_e2e sidecars stay as they are

`run_all_tests.sh:194` starts one proxy per xdist worker, named
`<project>-tls-gwN.adcp.test`, because `docker compose run` has **no
`--network-alias`** — the dotted *container name* is the whole mechanism. Those
fronts are per-isolated-server by construction, so one-nginx-per-server is
correct there. They keep the `${TLS_UPSTREAM}` template; only the shared stack
stops using it.

### 3. The webhook capture becomes a service

This is the item that actually costs something, and the reason in-process TLS
exists today.

`tests/e2e/_webhook_capture.py::run_webhook_capture_server` is a **per-test
context manager** binding an **ephemeral port** (`serve_in_thread` →
`0.0.0.0:0`; the port is known only after start — the file says so at line 83).
Several e2e modules open one per test, concurrently under xdist. No static
nginx upstream can name that.

Target: a long-lived `webhook-capture` compose service — fixed name, fixed
port, one nginx server block, tests read captured payloads back over its own
HTTP API instead of sharing a Python object. That is what a webhook receiver
is in production, and it deletes:

- the in-process `ssl_context` path and `_tls_context_for()`
- `ADCP_WEBHOOK_HOST` and its `host.docker.internal` fallback
- `host.docker.internal` from the cert SANs and from
  `src/core/security/url_validator.py::BLOCKED_HOSTNAMES`'s relevance to tests

Interim if this is split out: the in-process front is not a second TLS
*mechanism* (same CA, same leaf, same `SSL_CERT_FILE` anchor via
`tests/helpers/test_tls_material.py`) — only a second *terminator*. It is
acceptable to carry briefly, not to keep.

### 4. `SSL_CERT_FILE` is the standard trust anchor on every dialing service

Already on `adcp-server` and `tests` in a2. Must also be on: a3's stack, the
per-worker servers, and any service that dials (creative-agent when it calls
back). Combined bundle (system roots ++ our CA) is mandatory, not optional —
`SSL_CERT_FILE` *replaces* the default cafile, and the private-CA-only version
broke `uv sync` reaching pypi.org mid-run.

### 5. No reservations left

Success criterion, stated as the owner did: **in-network inbound and outbound
requests all work over https with no carve-outs.** Concretely, at the end:

- no `ADCP_OUTBOUND_ALLOW_INSECURE` (already deleted from `src/` by
  `salesagent-e6h0` — must not return)
- every `*_URL` origin in `docker-compose.e2e.yml` is `https://…adcp.test:8443`
- `ADCP_OUTBOUND_ALLOW_PRIVATE` stays open and that is **correct, not a
  reservation**: every compose origin is on a private bridge network by
  construction, and no amount of TLS changes an RFC 1918 address. The property
  that matters — cloud-metadata addresses are refused regardless — already
  holds with the hatch open, which is exactly why the BDD egress scenarios pin
  it open.

### 6. Guard

Extend `tests/unit/test_architecture_e2e_compose_tls_origins.py` from "these
two env vars are https" to the structural invariant: exactly one TLS-terminating
service in the shared stack, every dialed origin https, no service serving TLS
from anything other than the generated material.

## There is no upstream SDK gap here — checked, and the belief was wrong

a3's `test_jwks_publication_e2e.py:26-34` claims the SDK's hop-3 JWKS fetcher
"can only ever raise `jwks_fetch_failed`" against a privately-signed leaf,
because it sets `trust_env=False` and takes no client-factory seam. That is
incorrect, and it is why a3 hand-walks the chain instead of grading
`async_resolve_agent`.

Verified empirically against installed `adcp==6.6.0` and upstream `main`
(`688b3e4c`), calling `default_jwks_fetcher` against a real TLS origin serving
the generated test leaf:

```
SSL_CERT_FILE unset        -> ConnectError: CERTIFICATE_VERIFY_FAILED
SSL_CERT_FILE=ca.pem       -> OK, keys=1
SSL_CERT_FILE=combined-ca  -> OK, keys=1
```

`trust_env=False` is irrelevant here: the fetcher passes its **own**
`ssl_context` to the transport, and `build_ip_pinned_transport` →
`_build_ssl_context()` → a **bare `ssl.create_default_context()`**, which Python
honors `SSL_CERT_FILE` for via `set_default_verify_paths`. httpx's `trust_env`
logic only governs a context httpx would have built itself, and it never builds
one on this path. All three hops (capabilities, brand.json, JWKS) go through
`build_async_ip_pinned_transport`, so all three behave the same.

`trust_env=False` is also *correct* and must stay — its comment is right that
`HTTPS_PROXY` would route around the IP pin.

Residual, documented and not worth an upstream ticket: `verify` is a bool, so
`verify=False` remains the only escape for a deployment that cannot set a
process-wide `SSL_CERT_FILE`. `SSL_CERT_FILE` covers our case.

Related but distinct, and genuinely open upstream: `adcp-client-python#1004`
(DNS-free validation split + a transport injection point on the **MCP client**
path). Not a dependency of anything here.
