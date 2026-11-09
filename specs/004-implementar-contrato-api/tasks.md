---
description: "Task list for implementing the Operaciones API contract"
---

# Tasks: Implementar el contrato de API Operaciones

**Input**: Design documents from `specs/004-implementar-contrato-api/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/backend-api-acceptance.md`

**Tests**: Acceptance tests are required by FR-008 and cover AT-01 through AT-14. Add or update tests before the corresponding implementation tasks.

**Organization**: Tasks are grouped by user story. Reuse the current FastAPI routes, authentication, directory resolver, Huawei client, and test harness; no dependency, schema, container, or bot-repository changes are planned.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Tasks in different files with no dependency on unfinished work can run in parallel.
- **[Story]**: User story addressed by the task.
- Every task names its exact implementation or test file.

## Path Conventions

- Backend routes: `app/api/routes/`
- Acceptance and regression tests: `tests/`
- Feature design artifacts: `specs/004-implementar-contrato-api/`

## Phase 1: Setup

**Purpose**: Project initialization and shared infrastructure.

No setup changes are required: the FastAPI application, dependencies, authentication, shared Huawei client, directory resolver, and route test harness already exist.

---

## Phase 2: Foundational

**Purpose**: Blocking prerequisites for all user stories.

No foundational changes are required. Continue to use `app/services/node_resolution.py`, `app/services/huawei_client.py`, and the existing authentication dependency; do not add a second client or resolver.

---

## Phase 3: User Story 1 - Consultar estado por tecnología con errores consistentes (Priority: P1)

**Goal**: Resolve identifiers by technology, classify per-node outcomes consistently, and retain valid partial results for UMTS, LTE, and NR.

**Independent Test**: Run AT-01 through AT-08 against controlled directory and Huawei responses; verify HTTP status, `records`, `errors`, `name_resolution`, and upstream calls.

### Acceptance Tests

- [ ] T001 [US1] Add AT-01 and the 3G/4G/5G state-route cases from AT-02 for technology-specific directory columns, original inputs, suggestions, HTTP 200, and no Huawei call for unresolved names in `tests/test_huawei_route.py`.
- [ ] T002 [US1] Add AT-03 and the state-route cases from AT-05 for disconnected LTE/NR nodes, missing or ambiguous mappings, and connected nodes without technology cells in `tests/test_huawei_route.py`.
- [ ] T003 [US1] Add AT-04a, AT-04b, and AT-06 for unconfigured RNCs, all-unavailable versus mixed 3G cells, and valid cells alongside controller failures in `tests/test_huawei_route.py`.
- [ ] T004 [US1] Add AT-07 and AT-08 for mixed LTE/NR batches and HTTP 400, 401, 422, 502, 503, and 504 responses without stable node error codes in `tests/test_huawei_route.py`.

### Implementation

- [ ] T005 [US1] Implement directory-resolution outcomes, Spanish stable node errors, technology-specific mappings, disconnected LTE/NR handling, and partial batch preservation in `app/api/routes/huawei.py`.
- [ ] T006 [US1] Implement UMTS not-configured and cell-availability classification while retaining valid cells and other-RNC errors in `app/api/routes/huawei.py`.

**Checkpoint**: AT-01 through AT-08 pass independently; node errors remain HTTP 200 and transport/request errors remain HTTP errors.

---

## Phase 4: User Story 3 - Mantener compatibilidad y verificar el contrato del backend (Priority: P1)

**Goal**: Protect existing success response fields and types, verify no credentials or tokens are exposed, and keep acceptance coverage within this backend repository.

**Independent Test**: Run AT-11 and AT-14 using controlled route responses and an in-memory sentinel token; verify response schemas, logs, and test fixtures contain no credentials or token values.

### Acceptance Tests

- [ ] T007 [US3] Add AT-11 success-schema regression assertions for existing field names and types across state, KPI, and site-alarm responses in `tests/test_huawei_route.py` and `tests/test_alarms_route.py`.
- [ ] T008 [US3] Add AT-14 coverage using an in-memory sentinel Huawei token and assert it is absent from route responses and captured logs; review test fixtures for real credentials or tokens in `tests/test_huawei_route.py` and `tests/fixtures/`.

**Checkpoint**: Compatibility assertions pass, no real secret is added to fixtures or examples, and no task requires a bot-repository change.

---

## Phase 5: User Story 2 - Consultar alarmas y KPIs con semántica definida (Priority: P2)

**Goal**: Normalize alarm clear state from its timestamp and preserve the fixed 24-hour KPI contract, including unresolved identifiers and empty results.

**Independent Test**: Run AT-09, AT-10, AT-12, and AT-13 with controlled Huawei payloads; verify clear-state invariants, pagination, query parameters, KPI window, and per-node errors.

### Acceptance Tests

- [ ] T009 [P] [US2] Add AT-09 and AT-13 cases for null, present, and contradictory clear fields, `CURRENT`-only queries, existing alarm fields, count, and marker in `tests/test_alarms_route.py`.
- [ ] T010 [P] [US2] Add AT-10, AT-12, and the KPI case from AT-02 for ignored caller date fields, fixed 24-hour query parameters, `startTime`, unresolved-node errors, preserved measurements, and no error for resolved nodes without measurements in `tests/test_huawei_route.py`.

### Implementation

- [ ] T011 [US2] Derive site-alarm `cleared` exclusively from normalized `alarmClearedTime`, preserving the existing `CURRENT` query and response pagination in `app/api/routes/alarms.py`.
- [ ] T012 [US2] Preserve the fixed latest-24-hour KPI query, ignore request period fields, and return `NODE_NOT_FOUND` only for unresolved names while keeping empty resolved nodes error-free in `app/api/routes/huawei.py`.

**Checkpoint**: AT-09, AT-10, AT-12, and AT-13 pass; alarm and KPI response fields remain compatible.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate the complete acceptance suite and backend scope.

- [ ] T013 Run the focused acceptance and resolver suite from `specs/004-implementar-contrato-api/quickstart.md`: `pytest tests/test_huawei_route.py tests/test_alarms_route.py tests/test_node_resolution.py -q`.
- [ ] T014 Run the full regression suite with `pytest -q` and inspect `git diff --name-only` for changes outside `app/`, `tests/`, or `specs/004-implementar-contrato-api/`, confirming no bot-repository paths or real credentials/tokens.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No work; existing project initialization is sufficient.
- **Foundational (Phase 2)**: No work; existing auth, resolver, and shared client are the prerequisites.
- **User Stories**: Depend on the existing foundation. Execute Phase 3 before Phase 4 because those tasks share `tests/test_huawei_route.py`; Phase 5 follows to avoid concurrent edits to that test file.
- **Polish (Phase 6)**: Depends on all implementation and acceptance tasks.

### User Story Dependencies

- **User Story 1 (P1)**: Independent on existing infrastructure; implement first because it owns state-route behavior and acceptance tests.
- **User Story 3 (P1)**: Its assertions exercise existing public response envelopes and can be added after the state-route tests; no bot-repository dependency.
- **User Story 2 (P2)**: Independent in behavior, but scheduled after US1 and US3 because KPI tests share `tests/test_huawei_route.py`.

### Within Each User Story

- Acceptance tests precede the implementation they verify.
- Route behavior stays in the existing owning route module.
- Parallel tasks are marked only when they modify different files and have no unfinished-task dependency.

### Parallel Opportunities

- In US2, T009 (`tests/test_alarms_route.py`) and T010 (`tests/test_huawei_route.py`) can be authored in parallel.
- US1, US3, and US2 are behaviorally independent, but their existing test-file overlap favors the listed sequential order.

---

## Implementation Strategy

### MVP First (User Story 1)

1. Complete US1 acceptance cases for AT-01 through AT-08.
2. Implement UMTS/LTE/NR response classification and partial-result behavior.
3. Validate US1 independently before moving on.

### Incremental Delivery

1. Deliver US1 state-route behavior as the MVP.
2. Add US3 compatibility and secret-exposure verification.
3. Add US2 alarm and KPI semantics.
4. Run the focused suite, then the full regression suite.