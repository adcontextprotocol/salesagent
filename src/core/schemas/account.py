"""Account-related Pydantic schemas.

Extends adcp library account types per pattern #1 (schema inheritance).
All classes are re-exported from ``src.core.schemas`` for backward compatibility.


SDK 5.7 type:ignore tracking (adcontextprotocol/adcp-client-python#913):
- [misc] on line ~127: SyncAccountsResponse class def. Pydantic metaclass
  interaction in SDK hierarchy; permanent.
- [assignment] on line ~79: idempotency_key override (required -> optional).
  Architectural; permanent.
"""

from typing import ClassVar

from adcp.types import Account as LibraryAccountDomain
from adcp.types import Error as LibraryError
from adcp.types import ListAccountsRequest as LibraryListAccountsRequest
from adcp.types import ListAccountsResponse as LibraryListAccountsResponse
from adcp.types import NotificationConfig as LibraryNotificationConfig
from adcp.types import Setup as LibrarySetup
from adcp.types import SyncAccountsRequest as LibrarySyncAccountsRequest
from adcp.types.aliases import SyncAccountsSuccessResponse as LibrarySyncAccountsSuccess
from adcp.types.generated_poc.core.brand_ref import BrandReference as LibraryBrandReference
from adcp.types.generated_poc.core.business_entity import BusinessEntity as LibraryBusinessEntity
from pydantic import ConfigDict

from src.core.config import get_pydantic_extra_mode
from src.core.schemas._base import (
    AlwaysIncludeFieldsMixin,
    CompletedTaskStatusMixin,
    NestedModelSerializerMixin,
    SalesAgentBaseModel,
)

# ---------------------------------------------------------------------------
# Core domain Account (used in ListAccountsResponse.accounts)
# ---------------------------------------------------------------------------


class Account(AlwaysIncludeFieldsMixin, LibraryAccountDomain):
    """Extends library Account with salesagent model_config.

    Library provides: account_id, name, advertiser, billing_proxy, status,
    brand, operator, billing, rate_card, payment_terms, credit_limit, setup,
    account_scope, governance_agents, sandbox, ext.
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    # Derived from the pin, not declared. core/account.json types advertiser,
    # rate_card and payment_terms as plain non-nullable optionals and lists none of
    # them in `required`, so the intersection is empty and all three are omitted
    # when null. Declaring them always-include emitted a document that FAILED
    # validation against that schema, on list_accounts — a registered A2A skill.
    _PINNED_SCHEMA_REF: ClassVar[str] = "core/account.json"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ListAccountsRequest(LibraryListAccountsRequest):
    """Extends library ListAccountsRequest.

    Library provides: account, status, pagination, sandbox, context, ext.
    idempotency_key added locally -- the library type doesn't declare it
    (unlike SyncAccountsRequest), but v3.1.1's read-tool-idempotency.yaml
    compliance phase requires read tools to tolerate it (salesagent-tm97 F5;
    previously rejected under Pattern #7 extra=forbid).
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    idempotency_key: str | None = None


class SyncAccountsRequest(LibrarySyncAccountsRequest):
    """Extends library SyncAccountsRequest.

    Library provides: idempotency_key, accounts, delete_missing, dry_run,
    push_notification_config, context, ext.
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    # adcp 4.3 makes idempotency_key required.  Override as optional —
    # generated at the transport boundary when not supplied by the caller.
    idempotency_key: str | None = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ListAccountsResponse(NestedModelSerializerMixin, LibraryListAccountsResponse):
    """Extends library ListAccountsResponse.

    Library provides: accounts, errors, pagination, context, ext.
    NestedModelSerializerMixin ensures nested Account objects serialize correctly.
    Accounts field redeclared for Pattern #4 (nested serialization with local subclass).
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    # Required (no default): pinned 3.1 list-accounts-response marks 'accounts'
    # required. Redeclared for Pattern #4 (nested serialization with local subclass)
    # and to enforce the spec-required field (#1399 Plan-B).
    accounts: list[Account]  # type: ignore[assignment]

    def __str__(self) -> str:
        """Return human-readable summary message for protocol envelope."""
        count = len(self.accounts) if self.accounts else 0
        return f"Found {count} account{'s' if count != 1 else ''}."


class SyncResponseAccount(SalesAgentBaseModel):
    """Per-account result in a sync_accounts response.

    SDK 4.3 provided this as adcp.types.generated_poc.account.sync_accounts_response.Account.
    SDK 5.7 restructured the response; we now own this model.

    Fields are typed with adcp library models (Error, Setup) so Pydantic
    reconstructs them properly on transport roundtrip (A2A/MCP/REST).

    brand/operator/action/status are REQUIRED per the pinned AdCP schema
    (adcontextprotocol/adcp@04f59d2d5, sync-accounts-response success variant,
    accounts.items.required) — the model enforces them rather than relying on every
    call site. billing stays optional (not in the schema's required set).
    """

    brand: LibraryBrandReference
    operator: str
    action: str
    status: str
    account_id: str | None = None
    name: str | None = None
    billing: str | None = None
    payment_terms: str | None = None
    sandbox: bool | None = None
    errors: list[LibraryError] | None = None
    setup: LibrarySetup | None = None
    # #1592 T2: the applied notification subscriber set, echoed on created/updated/
    # unchanged. None omits the field ("never configured"); [] is emitted as an
    # empty array ("cleared") -- the two are different states to the buyer.
    # authentication.credentials is write-only and is stripped before this is built
    # (see _scrub_notification_credentials in src/core/tools/accounts.py).
    notification_configs: list[LibraryNotificationConfig] | None = None
    # "Echoed from the request. Sellers MAY add fields the agent omitted ... but
    # MUST NOT return data from a different entity. Bank details are omitted
    # (write-only)" (v3.1.1 sync-accounts-response.json, accounts.items.
    # billing_entity). The bank strip happens in _build_sync_result via
    # _scrub_business_entity, the single place a persisted entity becomes a
    # response object.
    billing_entity: LibraryBusinessEntity | None = None


class SyncAccountsResponse(
    CompletedTaskStatusMixin,
    NestedModelSerializerMixin,
    LibrarySyncAccountsSuccess,  # type: ignore[misc]
):
    """Extends library SyncAccountsResponse success variant.

    adcp 3.10: SyncAccountsResponse is a union TypeAlias (not RootModel).
    Since the error variant is never constructed (ToolError handles failures),
    we subclass the success variant directly.

    SDK 5.7 had collapsed the success envelope to just `status`, and this class
    carried local copies of accounts/dry_run/context/ext as a result. adcp 6.6
    re-added all four, typed, so only `accounts` is still declared here — and only
    to narrow its item type (Pattern #4). The rest are inherited.
    """

    model_config = ConfigDict(extra=get_pydantic_extra_mode())

    # Protocol-envelope `status` comes from CompletedTaskStatusMixin (composed above).
    # account/sync-accounts-response.json composes the envelope arm via a top-level
    # allOf, and this class is a TEMPORARY adopter: at adcp 6.6
    # SyncAccountsSuccessResponse has no ProtocolEnvelope in its MRO and no status
    # field, so the mixin is ADDITIVE here and deletes as a no-op the day the SDK
    # ships the field.
    #
    # "completed" is invariant rather than a TaskStatus: the pinned response's oneOf
    # arms are [['accounts'], ['errors']] with NO submitted arm, the error variant is
    # never constructed here, and sync_accounts models approval PER ACCOUNT
    # (src/core/tools/accounts.py) rather than per task — so the task itself always
    # completes. Same shape and same obsolescence condition as SyncCreativesResponse
    # (src/core/schemas/creative.py, GH #1710).

    # Pattern #4: narrowed to SyncResponseAccount for proper deserialization on
    # transport roundtrip. `accounts` is REQUIRED (no default): AdCP 3.1
    # sync-accounts-response is oneOf(SyncAccountsSuccess requires `accounts` |
    # SyncAccountsError requires `errors`). This model is the success variant, so
    # omitting `accounts` entirely is invalid (it would be neither a valid success
    # nor error). May be an empty list for a zero-account sync, but must be present.
    #
    # dry_run / context / ext are NOT redeclared. They carried a stale "SDK 5.7
    # removed these from the parent" note; adcp 6.6 re-added all three, typed, and
    # the SyncCreativesResponse twin already inherits them. Two of the local copies
    # were also strictly worse: `context` widened to accept a raw dict although
    # SyncAccountsRequest.context is itself a ContextObject, and `ext` weakened the
    # parent's ExtensionObject to a bare dict while no construction site passes it.
    accounts: list[SyncResponseAccount]

    def __str__(self) -> str:
        """Return human-readable summary message for protocol envelope."""
        count = len(self.accounts) if self.accounts else 0
        dry_run_note = " (dry run)" if self.dry_run else ""
        return f"Synced {count} account{'s' if count != 1 else ''}{dry_run_note}."


__all__ = [
    "Account",
    "ListAccountsRequest",
    "ListAccountsResponse",
    "SyncAccountsRequest",
    "SyncAccountsResponse",
    "SyncResponseAccount",
]
