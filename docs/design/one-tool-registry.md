# One tool registry

**Status:** design, not implemented.
**Measured at:** `c7a3a98d5`, 2026-09-04.

## The rule

A tool is declared **once**. Everything else is derived from that declaration:
the MCP tool, the A2A skill, the A2A agent card entry, the REST route, and the
request handed to the implementation.

There is **one builder**. Not one per tool. One.

## What exists today

A tool is declared between **three and four times**, and each declaration can
disagree with the others.

| transport | where a tool is declared | count |
|---|---|---|
| MCP | `_register_tool(fn)` in `src/core/main.py` | 16 |
| A2A | `AgentSkill(...)` literal in the agent card, **and** a row in the `skill_handlers` dict | 13 |
| REST | `@router.post(...)` decorator, **and** a `derived_body_model_for(...)` assignment | 13 |

Plus 16 hand-written `build_*_request` functions.

Three tools — `get_task`, `list_tasks`, `complete_task` — exist on MCP and
nowhere else. Nothing declares that to be deliberate; it is what the three
lists happen to contain.

### The cost, measured

`build_*_request` functions are hand-written subsets of their DTO:

| | |
|---|---|
| DTO fields no builder accepts | **68** |
| builders that take the DTO's field set exactly | 6 of 16 |
| builder parameters that are not DTO fields | 2 (`flight_start_date`, `flight_end_date`, one tool) |

Because all three transports build through the per-tool builder, **all three are
missing the identical set** in 11 of the 13 shared tools. The divergence is not
transport-vs-transport. It is builder-vs-DTO, reproduced three times.

`get_products` accepts **5 of its 21 declared fields**.

## What makes this possible now

Two facts, both measured, that were not true when the builders were written:

1. **Every `_impl` already takes `req`.** All twelve. Three additionally take
   `context_id`, `raw_wire_payload` or `request_hash` — transport-derived values,
   not buyer fields. (Two of those three are gone now; see the table below.)
2. **Every DTO is, or extends, the SDK's pinned request model.** `_register_tool`
   already refuses to register a tool whose DTO is not SDK-grounded.

So the implementation boundary is already uniform. Only the construction of the
request is not.

## The design

### One declaration

The tool's shape is **a subclass of the SDK's spec model with the unimplemented
fields removed**. That subclass is the whole definition: it is what we announce,
what we validate against, and what we pass around internally.

```python
# src/core/schemas/product.py

class GetProductsRequest(LibraryGetProductsRequest):
    """What this seller implements of get_products.

    The SDK model is the spec. This is the subset we have built.
    """
    TAGS: ClassVar[tuple[str, ...]] = ("products", "inventory", "catalog", "adcp")
```

```python
def omit(*fields: str):
    def deco(cls):
        for f in fields:
            cls.model_fields.pop(f, None)
        cls.model_rebuild(force=True)
        return cls
    return deco
```

**`model_rebuild(force=True)` is not optional, and skipping it fails in the
dangerous direction.** `model_fields` is metadata; the validator and the JSON
schema are compiled separately. Popping without rebuilding leaves them stale, so
the class *looks* narrowed and is not:

| after `model_fields.pop("c")` | without rebuild | with rebuild |
|---|---|---|
| `model_fields` | `['a']` | `['a']` |
| `model_json_schema()` | `['a', 'c']` | `['a']` |
| `model_validate({"a":1,"c":9})` | **accepted**, `hasattr(i,"c")` True | rejected |

That is the same three-sets-out-of-step failure this design exists to remove,
occurring inside pydantic. The rebuild is what makes `model_fields`, the
published schema, and the validator one thing.


**This is a Liskov violation, stated rather than discovered later.** The subtype
strengthens a precondition: it accepts a strict subset of what the parent accepts.
Concretely, code typed to `LibraryGetProductsRequest` doing `req.catalog` gets an
`AttributeError` on our instance, and **mypy will not catch it**, because mypy
believes the parent's contract.

It is accepted for one measurable reason: **the victim set is empty and is
cheaply kept empty.** A `Library*Request` used as an annotation or isinstance
target outside `src/core/schemas/` appears once in `src/`, at
`task_management.py:230`, where it is used *as* the DTO with no narrowing — so it
cannot be a victim. LSP is a theorem about consumers; with no consumers it has no
operational content. A guard forbidding `Library*Request` annotations outside the
schemas package is what makes that provable rather than incidental, and it is
part of this design rather than a follow-up.

**What inheritance is actually claiming here is provenance, not
substitutability**: these field definitions come from the spec, unretyped. That
is precisely what `sdk_grounding()` checks by walking the MRO, and it is why
bumping the SDK moves every advertised type with it. Python offers exactly one
mechanism that carries provenance through the type system.

The alternative — `create_model` from the SDK's own `FieldInfo` objects — was
tested and works, with no mutation and no rebuild. It is rejected because it
breaks `sdk_grounding()`'s MRO walk, and rewriting that gate around a declared
`_SPEC_MODEL` link reintroduces the import-spelling dependence the gate was
rebuilt to eliminate. **A reversal threshold is recorded below**, because that
judgement can change.

### The registry is wiring only

```python
@dataclass(frozen=True)
class RestBinding:
    verb: Literal["POST", "PUT"]
    path: str                       # "/media-buys/{media_buy_id}"
    path_fields: frozenset[str] = frozenset()

@dataclass(frozen=True)
class ToolSpec:
    dto: type[BaseModel]            # the subclass above
    impl: Callable                  # async def (*, req, identity, ...) -> Result
    rest: RestBinding | None        # None = not exposed over REST
    a2a: bool                       # exposed as an A2A skill
    auth: Literal["required", "optional"]   # a property of the TOOL, not of a transport

TOOLS: Mapping[str, ToolSpec] = {
    "get_products": ToolSpec(
        dto=GetProductsRequest,
        impl=_get_products_impl,
        rest=RestBinding("POST", "/products"),
        a2a=True,
        auth="optional",
    ),
    ...
}
```

`ToolSpec` says where a tool is reachable and what runs it. It says nothing about
its shape, because the shape says that itself.

### One builder

```python
def build_request(tool: str, payload: Mapping[str, Any]) -> BaseModel:
    """The ONE construction seam."""
    return TOOLS[tool].dto.model_validate(payload)
```

One line, and it replaces all sixteen `build_*_request` functions. It performs
no selection, because the DTO is already the accepted shape — the narrowing
happened at class definition, once, where a reader looking for "what does this
seller accept" will find it.

There is no `supported_model()`, no `UNIMPLEMENTED` set consulted at runtime, and
no cache. A field we have not implemented is not declared on the class, so:

| | `extra="forbid"` (dev/CI) | `extra="ignore"` (production) |
|---|---|---|
| buyer sends an unimplemented field | **rejected**, naming the field | accepted, **field absent from the instance** |
| `hasattr(instance, field)` | — | `False` |

An unimplemented field therefore **cannot propagate on any transport**. This
matters because the transports are not equally protected: MCP validates against
its published schema and would catch a stray field anyway, but **A2A and REST
have no such boundary** — `model_validate` is their only gate. Narrowing the
class is what makes that one gate sufficient.

The alternative — validate against the full spec model and drop unimplemented
fields afterwards — does not work. A field the model *declares* is not `extra`,
so the extra policy never sees it, and it reaches the implementation to be
silently ignored. That is accept-and-ignore: a 200 with no effect,
indistinguishable from having done what was asked.

Nothing else selects. Coercion (`to_account_reference`, `to_brand_reference`,
the brand shorthand) is what `model_validate` already does; those helpers exist
because the hand-written builders bypassed validation, not because pydantic
cannot do it.

A malformed payload raises `pydantic.ValidationError`, which every transport
boundary already translates to `INVALID_REQUEST` with `field` and `issues`
(`adcp_error_for`, checked before `ValueError` deliberately).

### The implementation is typed to OUR model, not the spec's

```python
async def _get_products_impl(*, req: GetProductsRequest, identity: ResolvedIdentity) -> ...:
```

where `GetProductsRequest` is **our narrowed subclass**, never the SDK's model.

**The `*` is a change, not the status quo.** No implementation is keyword-only
today. It is proposed because this design introduces a *generic* call site: the
registry invokes `spec.impl(...)` for every tool, so a parameter added or
reordered in one implementation would silently rebind under positional calling.
Keyword-only makes that a `TypeError` instead. It costs one character per
signature and is worth stating rather than smuggling in.

The direction matters. Ours subclasses the spec model, so
`isinstance(ours, LibraryGetProductsRequest)` is `True` — but
`isinstance(spec_instance, GetProductsRequest)` is `False`. Typing the parameter
to the spec model would therefore accept an instance carrying every omitted
field; typing it to ours cannot, because ours has no such attribute to carry.

So the guarantee is not "the boundary strips unimplemented fields and we trust
it". It is that a value carrying an unimplemented field **cannot be constructed
as the type the implementation accepts**. The narrowing holds at the type level,
checked by mypy, not only at the validation call.

This is the reason the SDK model must never appear in an `_impl` signature. It is
the spec's shape, and the spec's shape is wider than what we built.

### Derived registration

```python
# MCP
for name, spec in TOOLS.items():
    mcp.tool(**_sdk_annotations(name))(_mcp_wrapper(name, spec))

# A2A card + dispatch, from the same mapping
skills = [AgentSkill(id=n, name=n, description=_sdk_description(n), tags=list(s.tags))
          for n, s in TOOLS.items() if s.a2a]
handlers = {n: _a2a_handler(n, s) for n, s in TOOLS.items() if s.a2a}

# REST
for name, spec in TOOLS.items():
    if spec.rest:
        router.add_api_route(spec.rest.path, _rest_handler(name, spec),
                             methods=[spec.rest.verb])
```

There is no `@router.post` to write, no `_register_tool(x)` line to add, no
`AgentSkill` literal to keep in step. The three generators are the only places
that know a transport exists.

### One call path

Every transport reduces to the same three lines:

```python
payload = <transport-specific extraction>      # body, params, or kwargs
req = build_request(name, payload)
return await spec.impl(req=req, identity=identity, **transport_derived)
```

`transport_derived` is a **closed set of one**, not open kwargs:

| impl | beyond `req` and `identity` |
|---|---|
| `_create_media_buy_impl` | `context_id` |
| `_update_media_buy_impl` | `context_id` |
| the other twelve | nothing |

It was a set of three when this was written. Both of the others were idempotency plumbing,
and they are gone because idempotency is not the implementation's job:
`src/core/tools/_boundary.py` probes the replay cache and writes to it around the call, so
`_sync_creatives_impl` needs no `request_hash` and `_create_media_buy_impl` needs no
`raw_wire_payload`. What each transport threaded down, and got subtly different, is now taken
once from the model. `tests/unit/test_architecture_boundary_completeness.py` grades the
closed set: an implementation declaring anything else fails, because nothing could fill it.

**No implementation takes `**kwargs`**, and none may. The generic call passes only
what the target declares — `accepted_kwargs(impl)` already exists for exactly
this. An open `**kwargs` at this seam would let a transport hand an
implementation anything at all, which is the accept-and-ignore hazard one layer
below the one this design removes.

## The DTO is the SDK's model, extended

A tool's request DTO subclasses the SDK's request model and adds nothing the spec does not
declare. That is the whole rule.

An earlier version of this design NARROWED the DTO: an `@omit` list per tool naming the spec
fields this seller does not implement, applied by a decorator that popped them off
`model_fields`, with the lists gathered in `src/core/schemas/conformance.py` as a machine-
readable PICS. All of it is removed. The reasoning is kept so it is not reinvented.

**It bought nothing a buyer can observe.** Production runs `extra="ignore"`, so a field we do
not process is ignored whether it was popped or simply unused. The announced MCP shape is
`DTO fields INTERSECT the implementation's arguments` — already narrow, and popping did not
change it. The only behavioural difference was rejection in dev/CI.

**It cost correctness.** Popping mutates `model_fields`, a DERIVED structure, while the
annotation lives on the SDK parent. Any subclass re-collects from that annotation, so the
popped fields come back — and come back REQUIRED, because the pop destroyed the `FieldInfo`
carrying their defaults. Measured on `ListCreativesInternal`: 8 fields became 19, nine newly
required, and the model stopped being constructible. `model_rebuild(force=True)` does not
help; the hole is in what re-collection reads, not in when the validator is compiled.

**And it pointed at the wrong problem.** Measured at adcp 6.6.0 the SDK marks almost nothing
required — `ListCreativesRequest` has zero required fields, `GetProductsRequest` one. A spec
field we do not implement is not something to hide from the buyer: if the spec requires it and
we do not implement it we are not compliant, and a table asserting so does not change that.

Extending the SDK model gives free, correct validation of everything the spec defines. The
cost is implementing what we declare, which was always the job. A seller MAY widen a field, or
redefine its type where it has reason to; it may not quietly declare a shape narrower than the
protocol's.

## The alignment tests are deleted, not renegotiated

`tests/unit/test_pydantic_schema_alignment.py` — and any other unit test grading
schema-against-model, model-against-implementation, or request-against-schema
alignment — is **deleted**. This design leaves nowhere for them to stand.

They exist because the DTO and the pinned schema were two artifacts that could
disagree, so something had to compare them. Under this design the DTO **is** the
pinned model, minus a declared list. There is nothing to compare: the suite would
be asserting that Python inheritance works.

Concretely, its two central assertions become tautologies or contradictions:

> *"Every property the pinned schema declares is a field on the model. Extra
> model fields are fine; a MISSING schema field is not."*
> — `test_no_model_is_missing_a_field_its_schema_declares`

Every narrowed DTO fails that by construction, and it cannot be repaired — the
design's whole point is that some schema fields are deliberately absent. Its
sibling `test_no_model_rejects_a_field_its_pinned_schema_declares` is the same
assertion from the other side.

**No check replaces them.** A stale table cannot be constructed: the decorator
raises. See below.

Everything the deleted suite was protecting is now structural:

| the old suite checked | now |
|---|---|
| model declares every schema field | inherited; minus the table |
| model rejects nothing the schema declares | the narrowed class is the accepted shape |
| model has no field the schema lacks | derived: `model_fields - library_declared_fields` |
| advertised shape matches the model | MCP announces the model itself |

## Migration order

Each step leaves the tree green and is independently revertible.

1. **Add the registry**, populated from what exists. Assert it agrees with the
   current three declarations. No behaviour change; the assertion is the proof
   the rows are right.
2. **Delete `GET /capabilities`.**
3. **Move internal fields to extended models.** Four fields, three DTOs. No
   buyer-visible change — they are `exclude=True` today, so no transport accepts
   them already. This must precede step 5, because after it the DTO is the
   accepted shape without qualification.
4. **Delete the alignment suite and `_NON_SCHEMA_FIELDS`.** This comes BEFORE any
   guards replace it — the decorator refuses a wrong table at import, and the
   added half is derived rather than declared.
5. **Narrow the DTO and swap its builder, in one change, per tool.**

   These two cannot be separated, and the order matters in both directions:
   swapping the builder first makes the full DTO the accepted shape, widening
   acceptance to fields nothing implements — accept-and-ignore on up to 16 fields
   for one tool. Narrowing first does nothing, because the builder is still
   selecting. Done together, the builder's hand-written subset is replaced by
   the same subset declared on the DTO — which is why the order is what it is.

   **That ordering is not a promise that the wire does not move, and proving it
   did not is NOT the gate.** The two subsets are hand-written and derived
   respectively, so they can differ; discovering exactly where, across four
   transports and sixteen tools, is unbounded work that does not advance the
   architecture. The gate for each tool is structural: the builder is gone, the
   DTO declares the shape, the `_impl` is typed to it. Differences a buyer can
   observe are expected, recorded in the ledger, and reconciled afterwards.

   deliberately, with its blast radius measured over **payload producers, not
   constructions of the class**. A type-name grep found 76 of 89 sites when that
   was measured.

6. **Generate MCP registration from the registry**, deleting the 16
   `_register_tool` calls.
7. **Generate the A2A card and dispatch**, deleting the `AgentSkill` literals and
   the `skill_handlers` dict.
8. **Generate REST routes**, deleting the decorators and body-model assignments.

Steps 6–8 are where "declared once" becomes true. Step 5 is the only one that
touches what a buyer can send, and doing it one tool at a time keeps each
change's fallout attributable to one tool rather than to the migration.

## Why this needs no guards

The guards that exist today — transport parity, A2A-selects-off-the-tool,
REST-forwards-what-it-declares, builders-respect-declared-defaults — all grade
agreement between declarations that this design deletes. A tool cannot be
registered on MCP and missing from A2A when both are `for name, spec in
TOOLS.items()`. A route cannot declare a field it does not forward when the body
model and the forwarded set are the same object.

They should be deleted as the steps that make their diseases unreachable land,
and not before. Each deletion states which structural change made it impossible.
