# Tasks: Despliegue de cambios con git pull

**Input**: Design documents from `/specs/001-git-pull-deploy/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/deployment.md, quickstart.md

**Tests**: Not requested in the spec. Validation uses `pytest`, `docker compose config`, and the manual scenarios in quickstart.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story the task belongs to (US1, US2, US3)

## Phase 1: Setup

**Purpose**: Confirm baseline before changing deployment configuration

- [X] T001 Confirm `uvicorn[standard]` is already declared in `requirements.txt` (provides file watching; add no new dependency) and note the current `CMD` in `Dockerfile` and `healthcheck` in `compose.yaml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Make the checkout the runtime source of code

- [X] T002 Add read-only bind mounts to the `backend` service in `compose.yaml`: `./app:/app/app:ro`, `./alembic:/app/alembic:ro`, `./alembic.ini:/app/alembic.ini:ro` (do not mount `.env` or `.git`; keep `env_file`, `ports`, `init`, `restart`, `security_opt: no-new-privileges:true` and `cap_drop: ALL` unchanged)

**Checkpoint**: Container executes code from the repository checkout (FR-001, FR-002, FR-007).

---

## Phase 3: User Story 1 - Aplicar cambios de código tras git pull (Priority: P1) MVP

**Goal**: After `git pull`, the API serves the new code without rebuilding the image; startup failures stay visible.

**Independent Test**: Change an endpoint response, run `git pull`, verify new behavior with the image ID unchanged; introduce a startup error and verify logs and health expose it.

- [X] T003 [US1] Confirm `Dockerfile` keeps the non-root `USER appuser` (UID 10001) and `PYTHONDONTWRITEBYTECODE=1` so the app runs correctly against the read-only mount; change `Dockerfile` only if it does not
- [X] T004 [US1] Verify `docker compose config` resolves with the new mounts and unchanged proxy/CA env handling (`USE_PROXY`, `PROXY_URL`, `HUAWEI_CA_CERT_PATH` in `.env`) per FR-008
- [X] T005 [US1] Validate failure visibility per quickstart.md "Validate failure visibility": a deliberate error under `app/` in a disposable checkout appears in `docker compose logs backend` and the health check does not report healthy (FR-004)

**Checkpoint**: US1 is functional once US2's reload command is in place (T006); T005 is verified after T006.

---

## Phase 4: User Story 2 - Recarga automática sin intervención (Priority: P2)

**Goal**: Uvicorn detects changed files and reloads on its own, healthy within 30 s, new code active within 60 s.

**Independent Test**: After `git pull`, with no further command, the service returns to healthy and serves new code.

- [X] T006 [US2] Update `CMD` in `Dockerfile` to `["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]` (single process; watch only `app/` so `.env` and migrations do not trigger reloads; remove `--workers 1`, which is incompatible with `--reload`)
- [X] T007 [US2] Set the `healthcheck.interval` in `compose.yaml` from `60s` to `5s`, keeping `retries: 3`, `timeout: 5s`, `start_period: 10s`, so recovery is observed within 30 s (SC-003)
- [X] T008 [US2] Rebuild once (`docker compose build && docker compose up -d`) and run quickstart.md "Validate automatic reload after a code-only pull": confirm reload log line, healthy within 30 s, image ID unchanged
- [X] T009 [US2] Run `pytest` from the repository root to confirm no regressions

**Checkpoint**: US1 and US2 work together; code-only pulls need no rebuild or command.

---

## Phase 5: User Story 3 - Cambios de base de datos y dependencias (Priority: P3)

**Goal**: Operators know which changes still need manual action.

**Independent Test**: A new operator follows the docs for a pull with a migration and for a dependency change, in one attempt.

- [X] T010 [P] [US3] Rewrite the update paragraph in the Docker deployment section of `README.md` (around the line stating "Para actualizar, ejecuta `docker compose build` y `docker compose up -d`") to: code-only changes need only `git pull`; reload is automatic; the initial build is only for setup and dependencies
- [X] T011 [P] [US3] Add to `README.md` a table of changes requiring action, matching contracts/deployment.md: `requirements.txt`/base image -> `docker compose build` + `docker compose up -d`; Alembic migration -> `docker compose run --rm backend alembic upgrade head` (reload never applies it); `.env` change -> `docker compose up -d --force-recreate backend` (or restart); git conflicts/local changes -> resolve before relying on the checkout
- [X] T012 [US3] Update the migration step in `README.md` (line ~396-399, "La imagen incluye `alembic.ini` y `alembic/`") to state that `alembic/` and `alembic.ini` are mounted read-only from the checkout
- [X] T013 [US3] Update the rollback sentence in `README.md` to: `git checkout`/revert the previous commit; reload applies it automatically; rebuild only if dependencies changed

**Checkpoint**: All three stories are independently verifiable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T014 Run quickstart.md "Changes that still need action" scenarios (migration command and `.env` recreate) to confirm the documented commands work
- [X] T015 [P] Update `AGENTS.md` "Run / build" section with a one-line note that the Docker deployment mounts `app/`, `alembic/` and `alembic.ini` read-only and reloads on `git pull`
- [X] T016 Final check: `pytest` and `docker compose config` pass; confirm UID 10001, `no-new-privileges` and `cap_drop: ALL` are retained in `compose.yaml`

---

## Dependencies & Execution Order

- Phase 1 -> Phase 2 -> Phases 3-5 -> Phase 6.
- T006 (reload command) is required before T005 and T008 can validate behavior; T005 runs after T006/T007.
- US3 (docs only) is independent of US1/US2 and can start after Phase 2.
- `compose.yaml` tasks (T002, T007) touch the same file: run sequentially. `Dockerfile` edits (T003, T006) are sequential.

## Parallel Opportunities

- T010 and T011 (different sections of README.md; coordinate edits) and T015 (`AGENTS.md`) can run in parallel with US1/US2 implementation.

## Implementation Strategy

- **MVP**: Phases 1-2 plus T006 and T007 (mounts + reload) deliver the core goal (US1 + US2 behavior); validate with T004, T005, T008.
- **Incremental**: Add US3 documentation (T010-T013), then polish.

## Summary

- Total tasks: 16
- US1: 3 (T003-T005); US2: 4 (T006-T009); US3: 4 (T010-T013); Setup 1, Foundational 1, Polish 3
