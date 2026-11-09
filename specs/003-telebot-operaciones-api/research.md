# Research: API de Operaciones para Telebot

## Existing technology and architecture

**Decision**: Keep the existing Python 3.11, FastAPI, Pydantic, HTTPX, SQLAlchemy async, and pytest stack; add no dependencies or services.

**Rationale**: The five in-scope endpoints already exist in `app/api/routes/huawei.py` and `app/api/routes/alarms.py`. Node lookup is centralized in `app/services/node_resolution.py`, and Huawei calls use the shared client. The requested phase is contract definition, not code implementation.

**Alternatives considered**: Introducing a Telebot-specific service, schema package, or new API client was rejected because no new runtime behavior is implemented in this phase and the existing architecture already owns the relevant endpoints.

## UMTS NodeB disconnected behavior

**Decision**: Classify a 3G NodeB as `NODE_DISCONNECTED` when every returned cell has `Operation state = "Unavailable"`. Preserve those cells in `records` and also return the node error. If availability is mixed, preserve the records without `NODE_DISCONNECTED`.

**Rationale**: The domain owner confirmed the state value, all-cells threshold, and requirement to preserve records with the error. Existing route tests currently show `Operation state: Available`; implementation should add fixtures for all-unavailable and mixed-availability results. All-RNC `NodeB is not configured` remains `NODE_NOT_FOUND`.

**Alternatives considered**: Reusing the LTE/NR disconnected message or treating any empty 3G result as disconnected was rejected because neither is supported by repository evidence and both conflate distinct failure states.

## Cleared alarms in CURRENT query

**Decision**: Consume cleared alarms only when the existing `dataType=CURRENT` response contains them. Do not add a history query or promise cleared-alarm availability.

**Rationale**: Local tests verify that a supplied cleared-alarm row is transformed, but do not establish which rows the MAE returns for `CURRENT`. The feature spec accepts that cleared alarms may be absent and explicitly excludes historical queries.

**Alternatives considered**: Inferring that `CURRENT` includes cleared alarms from mocked response tests, or querying history, was rejected: the former is unverified and the latter is out of scope.

## KPI behavior for resolved NEs without measurements

**Decision**: An empty measurement result for a resolved node means `records: []` and `errors: []`; do not infer `NODE_DISCONNECTED`. Limit stable per-node errors to directory resolution outcomes defined by the spec.

**Rationale**: The performance query does not expose a documented per-NE connection state in the repository. Current tests cover successful direct and asynchronous KPI responses, not disconnected NEs. The spec explicitly leaves KPI disconnection behavior unspecified.

**Alternatives considered**: Mapping an empty result or a task-level error to `NODE_DISCONNECTED` was rejected because it cannot distinguish no data from loss of connectivity. Expanding the contract for per-NE performance failures is deferred until Huawei response evidence and a requirement are available.

## Contract and implementation boundary

**Decision**: Treat `contracts/telebot-operaciones.md` as the target API contract and this feature's code changes as out of scope. The next implementation phase should use the acceptance criteria to close differences between current route behavior and the target contract.

**Rationale**: The current route code does not yet emit all newly specified error fields; the alarm `cleared` field is currently translated independently of `alarmClearedTime`; KPI responses currently omit `errors`. The specification explicitly describes contract changes without authorizing runtime implementation here.

**Alternatives considered**: Altering route behavior while generating the plan was rejected because it would violate the feature's stated phase boundary.