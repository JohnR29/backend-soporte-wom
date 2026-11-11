# Tasks: Resolución de nombres de nodo en alarms/{site-name}

**Input**: Design docs from `/specs/005-alarms-node-resolution/`

**Prerequisites**: `plan.md` (required), `spec.md` (required), `data-model.md`, `contracts/http-alarms-endpoint.md`, `quickstart.md`

**Tests**: Include tests because the feature spec defines explicit acceptance scenarios and independent validation criteria.

**Organization**: This task list is grouped by user story so each story can be implemented and validated independently.

## Phase 1: Setup

- [X] T001 [P] Confirm the environment contract for `SITE_DIRECTORY_DATABASE_URL` and initialize the shared site-directory adapter in `app/services/node_resolution.py`
- [X] T002 [P] Add the exact-match, missing-mapping, and typo-suggestion fixture matrix in `tests/test_node_resolution.py`

## Phase 2: Foundational

- [X] T003 Implement canonical normalization and exact-match lookup helpers in `app/services/node_resolution.py`
- [X] T004 Implement technology-aware column selection (`nodo` vs `nodeb`) and ambiguous/missing mapping guards in `app/services/node_resolution.py`
- [X] T005 Define the shared response metadata contract consumed by `/alarms/{site_name}` and ensure `user_input`, `resolved_site`, `resolved_node`, and `technology` are preserved in `app/api/routes/alarms.py`
- [X] T006 Add the DB-unavailable/503 guard path in `app/services/node_resolution.py` so the resolver fails fast without invoking Huawei when the site directory is down

## Phase 3: User Story 1 - Consultar alarmas del sitio por nemónico

**Story Goal**: Un usuario puede consultar alarmas con un nemónico de sitio y el backend resuelve el nombre canónico correcto antes de consultar Huawei.

**Independent Test Criteria**:
- `/alarms/AN0069` resolves with default `4G` and returns the canonical node value from `public.cellreference`.
- `/alarms/AN0069?technology=3G` resolves using `nodeb` when present.
- A full node name already stored in the directory passes through as the canonical value without modifying the source.

- [X] T007 [US1] Implement the resolver entry path that accepts `site_name` + `technology`, normalizes the input, and returns the canonical node name in `app/services/node_resolution.py`
- [X] T008 [US1] Wire the resolver into the `/alarms/{site_name}` route in `app/api/routes/alarms.py` before the Huawei call and keep the response metadata aligned with the contract
- [X] T009 [US1] Add happy-path route tests for default `4G` resolution and explicit `3G` resolution in `tests/test_alarms_route.py`
- [X] T010 [US1] Add regression assertions for exact-match results and full-node canonicalization in `tests/test_node_resolution.py`
- [X] T011 [US1] Validate missing mapping and ambiguous mapping logic so a site that exists but lacks the requested technology is distinguished from a true not-found condition in `app/services/node_resolution.py`

## Phase 4: User Story 2 - Sugerencias cuando el sitio/nodo no existe

**Story Goal**: Cuando no hay coincidencia exacta, la API responde con un 404 y propone hasta 5 sitios similares, ordenados y limitados según el contrato.

**Independent Test Criteria**:
- `/alarms/AN0096` returns `404` and includes the expected suggestions list.
- Suggestions are sorted by similarity descending and alphabetically on tie.
- For missing mapping (`site exists` but no `nodo`/`nodeb` for the requested tech), the error is `missing_mapping` instead of `not_found`.

- [X] T012 [US2] Implement similarity ranking and threshold filtering in `app/services/node_resolution.py` using the design rules from `specs/005-alarms-node-resolution/data-model.md`
- [X] T013 [US2] Enforce the top-5 suggestion limit and alphabetical tie-break ordering in `app/services/node_resolution.py`
- [X] T014 [US2] Return structured `404` payloads for `not_found` and `missing_mapping`, including `suggestions`, `resolved_site`, and `available_technologies`, from `app/api/routes/alarms.py`
- [X] T015 [US2] Add regression tests covering typo suggestions, top-five recall, and empty-directory behavior in `tests/test_node_resolution.py`
- [X] T016 [US2] Add route-level coverage for the not-found/suggestion contract and missing-mapping response payload in `tests/test_alarms_route.py`

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T017 Validate the final API contract against `specs/005-alarms-node-resolution/contracts/http-alarms-endpoint.md` and ensure the response payload stays consistent with the success/404/503 contracts in `app/api/routes/alarms.py`
- [X] T018 [P] Run the project validation matrix from `specs/005-alarms-node-resolution/quickstart.md`, including the targeted pytest checks for `tests/test_node_resolution.py` and `tests/test_alarms_route.py`, and confirm all acceptance scenarios pass

## Dependencies

- Setup tasks must complete before foundational tasks.
- Foundational tasks must complete before US1 or US2 tasks begin.
- US1 and US2 can proceed in parallel after the foundation work is done, as they rely on the same service contract but cover different branches of the resolver.
- Polish runs after all story work has passed its validation criteria.

## Parallel Execution Examples

- US1 path: `T007` + `T009` can be implemented in parallel after `T005`, since they target the same story but different test and implementation artifacts.
- US2 path: `T012` + `T015` can be advanced in parallel once the service-level contract is in place.
- Cross-cutting validation: `T017` and `T018` are serial checks that should run only after all story tasks complete.

## Implementation Strategy

- MVP first: Ship the exact-match and technology-aware resolution flow in US1, including the DB-unavailable guard and canonical node selection.
- Incremental delivery: Add the typo-suggestion and not-found/error payload behaviors in US2 after the resolver is stable.
- Validation: Keep the acceptance tests lightweight and focused on the contract in `quickstart.md`, then use the broader route tests to catch integration regressions.

## Task Summary

- Total task count: 18
- User Story 1: 5 tasks (T007-T011)
- User Story 2: 5 tasks (T012-T016)
- Foundation + setup: 6 tasks (T001-T006)
- Polish: 2 tasks (T017-T018)
- Suggested MVP: User Story 1 only (T007-T011) for an initial production release, with US2 added immediately after validation if the typo-search behavior is required by support workflows.

## Format Validation

All tasks above follow the required checklist format: they begin with `- [ ]`, include a sequential `T###` identifier, use `[US1]` and `[US2]` only on story-scoped tasks, reference exact repository file paths, and keep each task concrete enough to execute without extra design interpretation.

## Phase 6: Convergence

- [ ] T019 Add repeatable p95 validation for exact and failed name resolutions against a representative directory, and meet the 500 ms target for both paths per SC-003 (partial)
