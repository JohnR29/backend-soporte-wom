# Tasks: Resolución de nombres de nodo a partir del sitio

**Input**: Design documents from `/specs/002-node-name-resolution/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/node-resolution.md](./contracts/node-resolution.md), [quickstart.md](./quickstart.md)

**Organization**: Tasks are grouped by user story so each increment can be implemented and validated independently.

## Phase 1: Setup

**Purpose**: Add configuration support for the separate read-only site directory connection.

- [X] T001 [P] Add optional `site_directory_database_url` setting mapped to `SITE_DIRECTORY_DATABASE_URL` in `app/core/config.py`.
- [X] T002 [P] Document the blank `SITE_DIRECTORY_DATABASE_URL` setting, separate from audit `DATABASE_URL`, in `.env.example` and `.env.production.example`; do not include credentials in either file.

## Phase 2: Foundational

**Purpose**: Implement and validate the shared read-only database access before endpoint-specific work.

- [X] T003 Add service tests for normalized exact site lookup, direct full-node lookup, missing target mapping, and unavailable configuration in `tests/test_node_resolution.py`; verify the tests fail before implementation.
- [X] T004 Implement the read-only resolver and its own async engine in `app/services/node_resolution.py`; query fixed relation `public.cellreference` using bound values and an allowlist for `nodo`/`nodeb`. The columns are `sitio`, `nodo`, `enodeb`, `nodeb`, and `gnodeb`, each `varchar(50) NULL`; `sitio` is unique by source-data guarantee, although the DDL has no `UNIQUE` constraint. Do not write to the table or reuse the audit sessionmaker.
- [X] T005 Initialize and close the site-directory engine independently of optional audit startup in `app/main.py`; return a service-unavailable error when `SITE_DIRECTORY_DATABASE_URL` is unset or the directory cannot be queried.

**Checkpoint**: Shared lookup works independently of whether audit is enabled; no Huawei route is changed yet.

## Phase 3: User Story 1 - Consultar 4G/5G escribiendo solo el sitio (Priority: P1)

**Goal**: Accept site mnemonics or full 4G/5G node names across MML, LTE, NR, and KPI routes.

**Independent Test**: Submit known site mnemonics and full node names to all four routes; verify Huawei receives the `nodo` values and each response exposes the input-to-resolved mapping.

- [X] T006 [US1] Add route tests for `POST /mml/command`, `/mml/cell-summary-lte`, `/mml/cell-summary-nr`, and `/mml/kpis` in `tests/test_huawei_route.py`, covering site resolution, full-node compatibility, mixed valid/invalid batches, and resolved response metadata; verify tests fail before implementation.
- [X] T007 [US1] Resolve each `ne_names` entry to `nodo` before Huawei calls in the four MML routes in `app/api/routes/huawei.py`; preserve valid results in mixed batches, skip unresolved values upstream, and add ordered `name_resolution` entries according to `specs/002-node-name-resolution/contracts/node-resolution.md`.

**Checkpoint**: All four 4G/5G routes support site and full-node inputs without losing successful entries from mixed batches.

## Phase 4: User Story 2 - Consultar estado 3G escribiendo solo el sitio (Priority: P1)

**Goal**: Resolve a site or direct NodeB name to the `nodeb` column for the UMTS summary route.

**Independent Test**: Submit a site and a direct NodeB name to `/mml/cell-summary-umts`; verify the MML command uses the canonical NodeB and a site with no `nodeb` mapping gets a distinct error.

- [X] T008 [US2] Add UMTS route tests for site-to-NodeB mapping, direct NodeB compatibility, missing `nodeb`, unknown site, and unavailable directory in `tests/test_huawei_route.py`; verify tests fail before implementation.
- [X] T009 [US2] Resolve `nodeb_name` to `nodeb` before UMTS MML execution in `app/api/routes/huawei.py`; return the resolved value and resolution metadata, with the documented `404` and `422` cases from `specs/002-node-name-resolution/contracts/node-resolution.md`.

**Checkpoint**: UMTS uses `nodeb`, not `nodo`, and existing direct NodeB inputs remain valid.

## Phase 5: User Story 3 - Sugerencias cuando el sitio no existe (Priority: P2)

**Goal**: Return up to five site suggestions with the highest similarity percentage, ordered descending with an alphabetical tie-break.

**Independent Test**: Query a misspelling such as `AN0096`; verify the response includes `AN0069` when it is among the five highest-scoring candidates, orders suggestions by descending percentage with alphabetical tie-breaks, returns no more than five, and returns an empty list when the directory has no sites.

- [X] T010 [US3] Add a versioned set of representative one-character typos in `tests/fixtures/node_resolution_typo_cases.json` and resolver tests in `tests/test_node_resolution.py` for percentage ordering, case-insensitive alphabetical tie-breaking, the five-result limit, empty directories, and at least 90% top-five recall of the expected site; verify tests fail before implementation.
- [X] T011 [US3] Rank non-null `sitio` values by `difflib.SequenceMatcher.ratio() * 100` after the existing trim/case-insensitive normalization in `app/services/node_resolution.py`; break ties alphabetically by site mnemonic without case sensitivity, compute suggestions only after exact lookup misses, and include at most five results in batch and UMTS resolution errors.

**Checkpoint**: Unknown names remain distinct from missing `nodo`/`nodeb` mappings and directory availability errors.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Complete audit traceability, operator documentation, and end-to-end validation.

- [X] T012 Add audit tests proving the original request remains in `request_body` and resolved upstream names are stored in `ne_names` in `tests/test_audit.py`; verify tests fail before implementation.
- [X] T013 Pass resolved node names from the MML routes to the audit middleware through request state and record those names in `app/api/audit_middleware.py` without changing the audit schema.
- [X] T014 Document `public.cellreference`, the read-only `SITE_DIRECTORY_DATABASE_URL`, affected MML endpoints, and resolution response/error behavior in `README.md`.
- [X] T015 Run the focused suite `pytest -q tests/test_node_resolution.py tests/test_huawei_route.py tests/test_audit.py` and follow the configured-directory scenarios in `specs/002-node-name-resolution/quickstart.md`; exhaustively verify all mapped rows in the integration copy, record row count/environment, measure at least 30 repetitions for each exact/miss-suggestion scalar/100-name batch scenario and confirm p95 <0.5 s, and verify the versioned typo set meets the 90% top-five recall target.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 and T002 can run in parallel.
- **Foundational (Phase 2)**: Starts after Setup; T003 is written and verified failing before T004, then T005 wires the lifecycle. This phase blocks all stories.
- **User Stories (Phases 3-5)**: Start after the Foundation checkpoint and follow the spec priority order. US1 and US2 both edit `app/api/routes/huawei.py`, so implement those route changes sequentially. US3 depends on the shared resolver from Phase 2 and can follow either route story.
- **Polish (Phase 6)**: T012 precedes T013; complete documentation and focused end-to-end validation after stories.

### User Story Dependencies

- **US1 (P1)**: Depends on Setup and Foundational; no dependency on another story.
- **US2 (P1)**: Depends on Setup and Foundational; behavior is independently testable, but route edits should follow US1 to avoid conflicts in `app/api/routes/huawei.py`.
- **US3 (P2)**: Depends on the shared lookup service; suggestions can be verified independently of Huawei route behavior.

### Parallel Opportunities

- T001 and T002 touch separate configuration files and can run in parallel.
- T006 and T008 test different route behavior in the same test file, so keep them sequential unless coordinated.
- T010 uses `tests/test_node_resolution.py` and can be prepared separately from route tests, but its implementation T011 shares `app/services/node_resolution.py` with T004 and must follow it.
- Do not parallelize T007 and T009 because both modify `app/api/routes/huawei.py`.

## Parallel Example: Setup

```text
Task: T001 Add SITE_DIRECTORY_DATABASE_URL setting in app/core/config.py
Task: T002 Document the setting in .env.example and .env.production.example
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational phases.
2. Complete US1 to enable site mnemonics for 4G/5G routes.
3. Validate US1 independently with the focused route tests.
4. Add US2, then US3; complete audit, docs, and integration validation.

### Incremental Delivery

1. Establish read-only connection and common exact lookup.
2. Deliver 4G/5G site resolution (US1).
3. Deliver 3G NodeB resolution (US2).
4. Add typo suggestions (US3).
5. Complete audit traceability and quickstart validation.

## Phase 7: Convergence

- [X] T016 Coordinate correction of the conflicting `nodo` and `nodeb` mappings for `RM_in_3G_173` in the externally managed `public.cellreference` directory, then rerun the exhaustive integration-copy resolution check per SC-001 (partial).
- [X] T017 Run `conda run -n backend-soporte python -m pytest -q tests/test_node_resolution.py tests/test_huawei_route.py tests/test_audit.py` successfully and record the result per T015 (partial).