"""The REST transport boundary leaves the same persistent audit trail as MCP and A2A.

Merge note (feature/spec-gaps-1210 x origin/main): this file was deleted on the
feature branch by "make buyer-facing error text unauthorable, and delete what
watched for it", whose stated destination for its contents was that "the envelope
is graded on the wire by BDD across mcp/a2a/rest/e2e_rest; a second non-BDD grader
is a copy that drifts". That is true of every envelope/recovery/serialization test
this file used to carry, and those are gone for good:

* the parametrized REST recovery propagation and the NOT_FOUND both-layers case ->
  ``tests/unit/test_error_boundary_translation.py::TestRestStatusCodeRoundtrip``,
  which drives each typed class through the real handler stack and grades both
  envelope layers via ``assert_envelope_shape``;
* ``to_dict()`` recovery roundtrip -> the method no longer exists; recovery is a
  read-only property over ``CODE_TABLE`` and is graded on both wire layers by
  ``assert_envelope_shape`` on every use;
* malformed-creative handling -> ``tests/integration/test_creative_validation_rest_obligations.py``
  ``TestMissingFormatIdRejectedThroughImpl`` (UC-006-EXT-E-01) and BR-UC-006's
  "the invalid creative should have action failed";
* invalid ``created_after`` -> ``tests/integration/test_creative_list_behavioral.py``
  ``test_invalid_created_after_raises`` (UC-006-EXT-C-01);
* ``Error`` / ``CreateMediaBuyError`` constructibility smoke tests -> exercised
  behaviorally by ``tests/unit/test_approval_error_handling.py`` and
  ``tests/unit/test_adcp_contract.py``.

What did NOT move is below. ``_envelope_response`` in src/app.py resolves identity
best-effort from the request (``_best_effort_rest_identity``) purely so the REST
boundary can feed the tenant-scoped sinks that MCP and A2A already feed. BDD grades
the wire envelope and BR-SECURITY-001 grades the boundary LOG via caplog; neither
grades the persisted audit row, and no other test in the tree asserts an
``audit_logs`` entry with ``adapter_id == "rest_boundary"``. Deleting this class
would have made that whole best-effort identity path unobserved.
"""

import pytest

from tests.helpers.capture_wrapper_req import registry_impl

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class TestRestBoundaryAuditObservability:
    """A REST boundary error leaves an audit row when identity is resolvable."""

    def test_rest_error_with_valid_token_writes_audit_row(self, factory_session, sample_tenant, sample_principal):
        """REST 4xx with a valid token writes an audit row scoped to the resolved principal."""
        from unittest.mock import AsyncMock

        from starlette.testclient import TestClient

        from src.app import app
        from src.core.database.repositories.audit_log import AuditLogRepository
        from src.core.exceptions import AdCPMediaBuyNotFoundError

        raised = AdCPMediaBuyNotFoundError()

        # Substituted at the REGISTRY ROW: the row holds the function object, so patching a
        # module attribute renames something no transport consults.
        with registry_impl("get_adcp_capabilities", AsyncMock(side_effect=raised)):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/capabilities",
                json={},
                headers={"x-adcp-auth": sample_principal["access_token"]},
            )

        assert response.status_code == 404

        # Read the persisted row back through the tenant-scoped audit repository rather
        # than a raw session: the tenant scoping is then the repository's, the same one
        # production reads audit rows through, and the test states only the one predicate
        # the repository does not carry (the boundary that wrote the row).
        audit_repo = AuditLogRepository(factory_session, sample_tenant["tenant_id"])
        boundary_rows = [row for row in audit_repo.list_by_tenant() if row.adapter_id == "rest_boundary"]

        assert boundary_rows, "REST boundary error must write an audit row when identity resolves"
        audit_log = boundary_rows[0]
        assert audit_log.success is False
        assert audit_log.principal_id == sample_principal["principal_id"]
        # Read the expectation back off the raised error rather than transcribing a
        # sentence: the text is a CODE_TABLE function of the code, and a literal here
        # would be a second copy of the table.
        assert audit_log.error_message == raised.message
