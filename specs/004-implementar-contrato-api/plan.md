# Implementation Plan: Implementar el contrato de API Operaciones

**Branch**: `004-implementar-contrato-api` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Implementar en el backend el contrato aceptado en la feature 003, añadir pruebas de aceptación y no modificar ni depender del repositorio del bot.

## Summary

Implementar el contrato de Operaciones para estado 3G/4G/5G, alarmas y KPIs, reutilizando la resolución de nombres de la feature 002 y el cliente Huawei compartido. Los errores operacionales por nodo serán datos de respuesta HTTP 200 con códigos estables; los errores de solicitud, autenticación, directorio y comunicación con Huawei conservarán sus estados HTTP. Se preservarán registros válidos en resultados parciales, se armonizará el estado de clareo de alarmas con su fecha, y KPIs seguirá consultando la ventana fija de 24 horas. Las pruebas de aceptación del backend cubrirán AT-01 a AT-14 con dependencias externas controladas.

## Technical Context

**Language/Version**: Python 3.11.

**Primary Dependencies**: FastAPI, Pydantic, HTTPX, pandas, SQLAlchemy async; all are existing dependencies.

**Storage**: No schema changes. The feature reads the existing site directory through `resolve_names`; audit storage remains unchanged.

**Testing**: pytest, FastAPI `TestClient`, route-boundary mocks/fakes, and existing node-resolution tests.

**Target Platform**: Dockerized Linux/Ubuntu deployment; local development also runs on Windows.

**Project Type**: FastAPI web service / Huawei API proxy.

**Performance Goals**: Preserve current request and Huawei timeout behavior; no new latency target is introduced by this feature. KPI period remains the latest fixed 24-hour window.

**Constraints**: Implement only in this backend repository; preserve the shared Huawei client, existing directory resolver, proxy/CA configuration, authentication and response fields. Do not add a dependency, database migration, container, endpoint, or bot-repository change without a concrete requirement and approval. 3G accepts one NodeB per request; 4G/5G/KPIs accept up to 100 names.

**Scale/Scope**: Five contract surfaces: UMTS, LTE, NR, site alarms, and KPIs; 14 acceptance scenarios. `/mml/command`, other alarm routes, bot behavior, historical alarms, and deployment mechanics are outside this feature.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Arquitectura Conservadora**: PASS. Extend the existing Huawei/alarm routes and their tests; retain existing client, resolver, and application structure. No new service, container, schema, or broad reorganization is planned.
- **II. Simplicidad**: PASS. Use direct response mapping and focused acceptance tests; introduce a shared helper only if it removes meaningful duplication across the affected route paths.
- **III. Dependencias y Contenedor Livianos**: PASS. No new package, image component, or container change is needed.
- **Additional Constraints**: PASS. Reuse `get_client()` and `resolve_names()`, preserve proxy/CA and authentication paths, and keep every implementation/test change in this backend repository.

**Post-design re-check**: PASS. The proposed artifacts retain the same existing architecture, add no dependencies or storage changes, and keep the acceptance harness within the current test suite.

## Project Structure

### Documentation

```text
specs/004-implementar-contrato-api/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── backend-api-acceptance.md
└── tasks.md              # Phase 2 output, not created by this plan
```

### Source and Tests

```text
app/api/routes/
├── huawei.py             # 3G, 4G, 5G and KPI behavior
└── alarms.py             # Site alarm normalization
app/services/
└── node_resolution.py    # Existing directory resolution; reuse
tests/
├── test_huawei_route.py
├── test_alarms_route.py
└── test_node_resolution.py
```

**Structure Decision**: Keep behavior in the existing route modules and exercise it through the current tests. Do not add a production module or touch the bot repository. Design documents live in this feature directory; `specs/003-telebot-operaciones-api/` remains the canonical contract source and `specs/002-node-name-resolution/` remains the name-resolution source.

## Complexity Tracking

No constitution violations or additional complexity are planned.
