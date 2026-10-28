# Implementation Plan: Despliegue de cambios con git pull

**Branch**: `001-git-pull-deploy` | **Date**: 2026-10-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-git-pull-deploy/spec.md`

## Summary

Make the checked-out repository the runtime source of application code by mounting
`app/`, `alembic/`, and `alembic.ini` read-only into the existing backend
container. Run the existing Uvicorn process with automatic reload watching only
`app/`, so a `git pull` needs no image rebuild or follow-up command for code-only
changes. Keep the existing non-root container and hardening, preserve the current
proxy/CA configuration, and document that dependency changes, database migrations,
and `.env` changes require explicit operator actions.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: FastAPI; `uvicorn[standard]` (already includes the file-watching extra); Docker Compose

**Storage**: PostgreSQL for optional API audit data; Alembic-managed schema; no new storage

**Testing**: pytest; Docker Compose configuration/build and runtime health checks

**Target Platform**: Docker Engine on Ubuntu VM in production; Windows development host, including Docker Desktop if running the container locally

**Project Type**: Containerized FastAPI web service

**Performance Goals**: Code-only changes become active within 60 seconds of `git pull`; the service returns healthy within 30 seconds after reload.

**Constraints**: Use the repository checkout as runtime source; mount application code, Alembic migrations, and Alembic configuration read-only; retain UID 10001, dropped capabilities, and `no-new-privileges`; add no dependencies or containers; watch application Python code, not `.env` or database migrations; dependency changes require rebuilding the image; migrations and `.env` updates remain manual; proxy and CA behavior remain environment-driven.

**Scale/Scope**: One existing backend service and one Uvicorn worker; no endpoint or response-schema changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / constraint | Result | Rationale |
|---|---|---|
| I. Arquitectura Conservadora | PASS | Reuse the existing backend container, Compose service, and application layout. No new service or architectural layer. |
| II. Simplicidad | PASS | Use Uvicorn's existing reload support and Compose bind mounts instead of a separate watcher or deployment service. |
| III. Dependencias y Contenedor Livianos | PASS | `uvicorn[standard]` is already declared; no new package is needed. The image remains the dependency/runtime environment. |
| Additional Constraints | PASS | The source mount is read-only and the existing container security settings remain in force. |
| Development Workflow | PASS | Validate Compose configuration/build and run focused tests plus the documented reload scenario. |

No constitution violations or unresolved requirement clarifications were identified.

## Project Structure

### Documentation (this feature)

```text
specs/001-git-pull-deploy/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── deployment.md
```

### Source Code (repository root)

```text
app/
├── api/
│   └── routes/
├── core/
├── db/
├── services/
└── main.py
alembic/
├── versions/
└── env.py
alembic.ini
compose.yaml
Dockerfile
requirements.txt
tests/
README.md
```

**Structure Decision**: Preserve the existing single-project FastAPI layout. Compose
will mount `app/`, `alembic/`, and `alembic.ini` read-only at their existing paths
inside `/app`. This keeps the application current after a pull and makes migration
revisions from the checkout available to the explicit Alembic command, without
exposing `.env` or `.git` to the process. The runtime command watches only the
application directory, so configuration and migration changes do not trigger
application reloads. Set the health-check interval to 5 seconds (with the existing
3 retries) to meet the under-30-second recovery criterion.

## Complexity Tracking

No constitution violations; no complexity exception is required.

## Phase 0: Outline & Research

See [research.md](./research.md). The design reuses capabilities already present in
the Dockerfile, Compose service, and `uvicorn[standard]`; no technology unknowns
remain.

## Phase 1: Design & Contracts

- [data-model.md](./data-model.md) defines the runtime source, dependency image,
  configuration, and migration entities and their update rules.
- [contracts/deployment.md](./contracts/deployment.md) describes the operator-facing
  Compose/runtime contract. The HTTP API contract is unchanged.
- [quickstart.md](./quickstart.md) provides the end-to-end Docker validation
  scenarios for reload, failure visibility, dependencies, migrations, and settings.

### Post-design Constitution Check

| Principle / constraint | Result | Rationale |
|---|---|---|
| I. Arquitectura Conservadora | PASS | Only existing Compose/Docker/Uvicorn configuration and deployment documentation need changes. |
| II. Simplicidad | PASS | No custom watcher, sidecar, or new deployment command is introduced for code-only pulls. |
| III. Dependencias y Contenedor Livianos | PASS | Existing Uvicorn extra provides watch support; dependency changes still use an explicit image rebuild. |
| Additional Constraints | PASS | Read-only application mount preserves the service's inability to modify checked-out source. |
| Development Workflow | PASS | Quickstart includes configuration, build, health, reload and test verification. |

No gate failures.
