# Backend API Acceptance Contract

The normative contract is [feature 003](../../003-telebot-operaciones-api/contracts/telebot-operaciones.md); the implementation scope and clarifications are [feature 004](../spec.md). This document maps those rules to backend boundaries and acceptance scenarios without redefining consumer/bot behavior.

## In-Scope Endpoints

| Operation | Endpoint | Identifier behavior |
|---|---|---|
| 3G cell state | `POST /mml/cell-summary-umts` | One `nodeb_name`; resolve using directory `nodeb`. |
| 4G cell state | `POST /mml/cell-summary-lte` | `ne_names`; resolve each using directory `nodo`. |
| 5G cell state | `POST /mml/cell-summary-nr` | `ne_names`; resolve each using directory `nodo`. |
| Site alarms | `GET /alarms/{site_name}` | Preserve current `CURRENT` query, fields, and pagination. |
| KPIs | `POST /mml/kpis` | `ne_names`; resolve each using directory `nodo`; fixed latest 24 hours. |

All state/KPI responses include `name_resolution` with the original input, canonical result or null, and resolution status. The bot repository, `/mml/command`, other alarm routes, historical alarms, and overall cross-technology status are outside scope.

## Response Rules

- Errors about an individual identifier use HTTP 200 and a stable `errors[].code` where applicable: `NODE_NOT_FOUND`, `NODE_DISCONNECTED`, or `TECHNOLOGY_UNAVAILABLE`.
- Each node error includes a Spanish `message`, original `input`, `ne_name` (canonical value or null), and original Huawei `error` text when available. Not-found errors include suggestions when available.
- Request/authentication/Huawei/directory failures remain HTTP errors (400, 401, 422, 502, 503, or 504 as applicable) and do not expose a node code in `errors[].code`.
- Successful records are retained when other nodes, controllers, or per-node commands fail. A 3G NodeB whose returned cells are all `Unavailable` keeps those records and also receives `NODE_DISCONNECTED`.
- A missing/ambiguous mapping does not trigger a Huawei request and maps to `TECHNOLOGY_UNAVAILABLE`; a directory miss maps to `NODE_NOT_FOUND`.
- `alarmClearedTime` controls `cleared`: null means `Activa`, non-null means `Limpia`. Alarms are queried only with `dataType=CURRENT`.
- KPI dates are fixed to the latest 24 hours; request period fields are ignored. A resolved node with no measurements has no node error.
- Existing field names/types remain compatible except the specified 3G not-found HTTP 404 to HTTP 200 change and additive KPI error data.

## Acceptance Matrix

| Scenario | Backend verification |
|---|---|
| AT-01 | Mock one directory identifier with distinct `nodeb`/`nodo`; verify per-technology canonical calls and `name_resolution`. |
| AT-02 | Exercise unknown identifiers in 3G, 4G/5G batch, and KPIs; verify HTTP 200, empty/partial records, `NODE_NOT_FOUND`, and suggestions. |
| AT-03 | Return Huawei's disconnected-NE result for LTE/NR; verify `NODE_DISCONNECTED` without records for that node. |
| AT-04a | Make all RNC probes report not configured; verify 3G `NODE_NOT_FOUND` and no records. |
| AT-04b | Return all `Unavailable` cells, then mixed `Unavailable`/available cells; verify retention and classification in both cases. |
| AT-05 | Test missing/ambiguous mapping and connected-without-cells; verify `TECHNOLOGY_UNAVAILABLE` and no guessed Huawei request. |
| AT-06 | Return valid 3G cells from one RNC and errors from another; verify all records remain and no false node-level error. |
| AT-07 | Use a mixed LTE/NR batch; verify successful node records remain beside the failed node's error. |
| AT-08 | Cover HTTP 400/401/422/502/503/504 responses; verify no stable node code is returned as an `errors[]` item. |
| AT-09 | Test null, present, and contradictory clear time/flag combinations; verify the time-derived invariant. |
| AT-10 | Send KPI period fields and verify they do not alter the fixed window; verify each row's `startTime`. |
| AT-11 | Assert successful response field names/types and existing full-node input behavior; document only 3G not-found status as an intentional compatibility change. |
| AT-12 | Combine unresolved KPI names, resolved names with data, and a resolved name without measurements; verify records and node errors independently. |
| AT-13 | Assert the site alarm request uses `CURRENT` and preserves `count`, `marker`, and current fields. |
| AT-14 | Ensure committed fixtures/assertions contain no credentials or tokens; use fake test tokens only in-memory where the existing tests require auth headers. |

## Verification Boundaries

Route acceptance tests replace external Huawei/directory boundaries. Existing `tests/test_node_resolution.py` continues to validate resolver semantics and its versioned suggestion fixture. Full test suite execution is required before implementation is considered complete. No test requires a bot checkout or live Huawei credentials.
