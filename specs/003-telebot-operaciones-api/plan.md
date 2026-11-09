# Implementation Plan: API de Operaciones lista para Telebot Operaciones

**Branch**: `003-telebot-operaciones-api` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification at `specs/003-telebot-operaciones-api/spec.md`

## Summary

Document and validate the API contract Telebot Operaciones will consume across the 3G, 4G, 5G, alarms, and KPI endpoints. This feature phase produces specification and design artifacts only; it does not change application code. The contract is additive except for the specified 3G not-found response changing from HTTP 404 to HTTP 200 with a stable per-node error.

## Technical Context

**Language/Version**: Python 3.11 (container runtime)

**Primary Dependencies**: FastAPI, Pydantic, HTTPX, SQLAlchemy async; existing dependencies only

**Storage**: Existing PostgreSQL site directory (`public.cellreference`); no new storage

**Testing**: pytest with FastAPI TestClient and mocked Huawei/directory calls

**Target Platform**: Linux Docker container on Ubuntu VM; Windows development environment

**Project Type**: FastAPI backend proxy to Huawei MAE-Access

**Performance Goals**: No new latency or throughput target is specified; retain existing route behavior and Huawei timeout/polling limits

**Constraints**: This feature phase is documentation-only; no source, dependency, or container changes. Keep Huawei access through the shared client in `app/services/huawei_client.py` in any later implementation.

**Scale/Scope**: Five existing endpoints; state requests accept 1-100 NEs for 4G/5G and KPIs, 3G accepts one NodeB, and alarms retain their existing 1-1000 limit. No cross-technology aggregate state.

## Constitution Check

*GATE: Evaluated before Phase 0 and re-checked after Phase 1.*

| Principle | Gate | Result |
|---|---|---|
| I. Arquitectura Conservadora | Do not restructure services, routes, or containers without a concrete need and approval. | PASS: documentation-only; existing endpoint ownership is recorded without proposing a structural change. |
| II. Simplicidad | Prefer direct, minimal behavior and avoid unnecessary abstractions. | PASS: contract documents stable error mapping and preserves existing response fields. |
| III. Dependencias y Contenedor Livianos | Justify new dependencies and container changes. | PASS: none proposed. |

**Pre-research result**: PASS. No gate violations or unresolved technical-context fields.

**Post-design result**: PASS. Design artifacts specify contracts and validation scenarios only; no architectural changes, dependencies, or container additions are introduced.

## Project Structure

### Documentation (this feature)

```text
specs/003-telebot-operaciones-api/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── telebot-operaciones.md
├── checklists/
│   └── requirements.md
└── tasks.md                 # Documentation task list
```

### Relevant Existing Source

```text
app/api/routes/
├── huawei.py                # MML cell summaries and KPI route
└── alarms.py                # Site alarms route
app/services/
└── node_resolution.py       # Site-directory resolution
tests/
├── test_huawei_route.py
└── test_node_resolution.py
```

**Structure Decision**: Keep the design artifacts in the existing feature directory. The feature specification explicitly excludes code implementation, so the existing application and test structure remains unchanged in this phase.

## Complexity Tracking

No constitution violations.
