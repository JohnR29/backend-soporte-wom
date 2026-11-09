# Research: Implementar el contrato de API Operaciones

## Decision: Contract and scope sources

**Decision**: Treat `specs/003-telebot-operaciones-api/spec.md` and its `contracts/telebot-operaciones.md` as the behavioral source of truth. Reuse name-resolution semantics from feature 002. The feature 001 deployment behavior is not changed.

**Rationale**: Feature 004 explicitly implements the backend portion of feature 003 and says that the consumer/bot repository is out of scope. Feature 002 already owns directory lookup and canonical node names. Feature 001 addresses code reload/deployment rather than API response behavior.

**Alternatives considered**: Copying or redefining the contract in feature 004 would invite drift; changing deployment or bot behavior would expand the explicitly bounded scope.

## Decision: Existing route and integration boundaries

**Decision**: Extend `app/api/routes/huawei.py` for UMTS/LTE/NR/KPI responses and `app/api/routes/alarms.py` for alarm normalization. Continue to call `resolve_names()` for directory lookup, and use the shared Huawei client/header functions for upstream calls.

**Rationale**: These routes already own the required behavior, and the repository instructions designate `huawei_client.py` as the single Huawei client and certificate/proxy boundary. The directory resolver owns its async database engine and already maps directory unavailability to HTTP 503.

**Alternatives considered**: A route-specific HTTP client, direct route-level directory query, or a new service layer would duplicate lifecycle/configuration and add structure without a demonstrated need.

## Decision: Acceptance test boundary

**Decision**: Exercise public endpoints with FastAPI `TestClient`; replace the resolver and Huawei calls with deterministic fakes/mocks. Keep actual directory algorithm coverage in `tests/test_node_resolution.py`.

**Rationale**: The existing route tests use this pattern and already control authentication, upstream payloads, and resolved names. It validates HTTP status, serialization, payload shape, call parameters, and partial-result behavior without network credentials or external services.

**Alternatives considered**: Direct function calls omit FastAPI validation/dependencies/serialization. Live Huawei or database tests would make acceptance runs environment-dependent and conflict with the feature's controlled-dependency assumption.

## Decision: Node-level and HTTP-level failures

**Decision**: Map directory resolution and Huawei per-node outcomes into stable `errors[]`/`name_resolution` records with HTTP 200; preserve successful records when sibling nodes, RNCs, or per-node MML commands return failures. Keep request, authentication, directory availability, and Huawei transport/rejection failures as HTTP errors, with no node error codes.

**Rationale**: This preserves the distinction in FR-003/004/005 and the contract's AT-06/07/08. A Huawei result containing a per-node failure is different from a failed HTTP communication. The existing route helpers already preserve raw node errors and return transport failures as `HTTPException`.

**Alternatives considered**: Converting all upstream failures to node errors would conflate transport and operational state. Failing a mixed batch on one node/controller would discard valid data.

## Decision: Stable classification and special cases

**Decision**: Follow the contract's classification precedence `NODE_NOT_FOUND` > `NODE_DISCONNECTED` > `TECHNOLOGY_UNAVAILABLE`. Map an absent or ambiguous technology mapping to `TECHNOLOGY_UNAVAILABLE` without calling Huawei. For 3G, all RNCs reporting that a NodeB is not configured yields `NODE_NOT_FOUND`; cells all marked `Operation state = "Unavailable"` yield `NODE_DISCONNECTED` while retaining those cells. Mixed cell availability does not yield disconnection. A resolved KPI node with no measurements has no node error.

**Rationale**: These cases are explicitly settled by feature 003 and repeated in feature 004 clarifications. They avoid inferring connectivity from empty KPI results or trying a guessed node name.

**Alternatives considered**: Returning the current UMTS 404/422 responses or treating every empty result as disconnected conflicts with the accepted contract.

## Decision: Alarm and KPI semantics

**Decision**: Derive `cleared` solely from normalized `alarmClearedTime`: null means `Activa`, non-null means `Limpia`; preserve current `CURRENT` query and pagination. Keep KPIs on the existing fixed latest-24-hour query, ignore request date fields, add `errors` for unresolved names, and leave resolved nodes with no measurements error-free.

**Rationale**: Feature 003 fixes the alarm invariant and explicitly excludes history. Feature 004 clarifies fixed-window KPI behavior and no connectivity inference for empty results. Existing KPI window construction and `startTime` conversion already implement the time behavior.

**Alternatives considered**: Trusting the upstream `cleared` flag can produce contradictory fields. Adding historical alarm queries or caller-selected KPI windows is outside the contract.

## Decision: Dependencies, storage, and deployment

**Decision**: Add no packages, schema, migration, container, or deployment behavior. Keep the 001 `git pull` workflow unchanged.

**Rationale**: Existing FastAPI/Pydantic/HTTPX/SQLAlchemy and test helpers support the requirements. Feature 004 assumes the directory and authentication are already available and explicitly excludes external bot changes.

**Alternatives considered**: New dependencies or schema would add maintenance and deployment requirements without a requirement in the feature specification.

## Resolved questions and residual validation

- Ambiguous/missing technology mapping classification is resolved by feature 003 FR-006 and feature 004 acceptance scenario 5: return `TECHNOLOGY_UNAVAILABLE`, do not call Huawei.
- Partial valid data applies to per-node/controller/command results. A failed HTTP communication remains an HTTP error under FR-004; it must not be encoded as a node error.
- AT-08 verifies that any listed HTTP error response has no node `errors[].code`; it does not require adding a new 504-producing path.
- Whether Huawei `CURRENT` responses actually include cleared alarms remains an external integration limitation already acknowledged in feature 003. Acceptance tests validate normalization and the absence of a historical query, not Huawei retention behavior.
