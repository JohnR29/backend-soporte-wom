# Implementation Plan: Resolución de nombres de nodo en alarms/{site-name}

**Branch**: `005-alarms-node-resolution` | **Date**: 2026-11-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-alarms-node-resolution/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Implementar resolución de nombres de nodo y sugerencias de similitud en el endpoint `/alarms/{site-name}`. El usuario puede ingresar un nemónico de sitio (ej. "AN0069"), el backend resuelve el nombre completo del nodo (ej. "MBTS-AN0069") consultando `public.cellreference`, y si no existe, devuelve sugerencias basadas en distancia de Levenshtein. Soporta parámetro opcional `technology` (3G/4G/5G, con 4G por defecto).

## Technical Context

**Language/Version**: Python 3.11 (baseline actual del proyecto)

**Primary Dependencies**: FastAPI (web framework existente), httpx (cliente HTTP para Huawei), psycopg2 o asyncpg (PostgreSQL, para `SITE_DIRECTORY_DATABASE_URL`)

**Storage**: PostgreSQL (tabla `public.cellreference` en base de datos externa vía `SITE_DIRECTORY_DATABASE_URL`); Huawei API para alarmas

**Testing**: pytest (testing framework actual del proyecto)

**Target Platform**: Linux server (deployment en VM Ubuntu)

**Project Type**: Web service (FastAPI backend proxy intermediario)

**Performance Goals**: <0.5 segundos (p95) para resolución de nombres + consulta de alarmas (single-site, incluido lookup en directorio)

**Constraints**: 
- HTTP 503 si directorio no disponible (no llamar Huawei)
- Proxy y certificados CA gestionados por variables de entorno (usar `get_client()` en `huawei_client.py`)
- Arquitectura conservadora (sin nuevos contenedores, servicios o capas)
- Dependencias livianas (ninguna nueva a menos que sea imprescindible)

**Scale/Scope**: Un sitio por solicitud (sin soporte para consultas por lotes); hasta 5 sugerencias en respuesta de error

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**✅ PASS**: La feature cumple con los tres principios:
1. **Arquitectura Conservadora**: Extiende el endpoint `/alarms/{site-name}` existente sin crear nuevos servicios ni contenedores; integración mínima dentro de `app/api/routes/`.
2. **Simplicidad**: La resolución es un lookup simple en tabla PostgreSQL + algoritmo de similitud (Levenshtein); no introduce patrones complejos.
3. **Dependencias Livianas**: Usa dependencias existentes (FastAPI, psycopg2/asyncpg, httpx). Si requiere una librería de similitud (ej. `python-Levenshtein`), es mínima y justificada por requisitos funcionales.

## Project Structure

### Documentation (this feature)

```text
specs/005-alarms-node-resolution/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
app/
├── api/
│   ├── routes/
│   │   ├── alarms.py          # MODIFIED: Extender endpoint /alarms/{site-name}
│   │   └── ...
│   └── ...
├── services/
│   ├── huawei_client.py        # (sin cambios; mantener proxy/CA cert setup)
│   ├── node_resolver.py        # NUEVO: Lógica de resolución de nombres de nodo
│   └── ...
├── core/
│   ├── config.py               # (sin cambios)
│   └── ...
└── main.py                     # (sin cambios)

tests/
├── api/
│   ├── test_alarms.py          # NUEVO: Tests para resolución de nombres
│   └── ...
├── services/
│   ├── test_node_resolver.py   # NUEVO: Tests unitarios para resolver
│   └── ...
└── ...
```

**Structure Decision**: Opción 1 (Single project): El backend es un único servicio FastAPI. La resolución de nombres se integra como un servicio interno (`node_resolver.py`) invocado por el router `/alarms/{site-name}` en `app/api/routes/alarms.py`. Se mantiene la estructura existente sin crear nuevos contenedores ni servicios.

## Complexity Tracking

No hay violaciones de la constitución. La feature es incremental y usa dependencias existentes. Si se introduce `python-Levenshtein` es mínima y justificada.

---

## PHASE 0: RESEARCH & CLARIFICATIONS

### Research Tasks

The following items require research to finalize the design:

1. **Algoritmo de similitud (Levenshtein)**: Verificar disponibilidad de librería estándar (`difflib` en stdlib o `python-Levenshtein` de terceros); evaluar rendimiento y cobertura de casos de similitud.
2. **Integración con SITE_DIRECTORY_DATABASE_URL**: Confirmar esquema exacto de `public.cellreference` (columnas, tipos, índices); validar conexión en ambiente local y VM.
3. **Normalization rules**: Confirmar si trim/case-conversion se alinea con spec 002 (normalize_node_name en routes/alarms.py actual).
4. **Error codes y contratos**: Definir estructura JSON exacta para respuestas 404 con sugerencias, 503 cuando directorio indisponible.

### Research Findings

#### 1. Algoritmo de similitud

**Decision**: Usar `difflib.SequenceMatcher` (Python stdlib) como primera opción; considerar `python-Levenshtein` solo si performance es crítica.

**Rationale**: 
- `difflib.SequenceMatcher` está en stdlib (sin dependencia adicional).
- Cubre distancia de Levenshtein de forma aceptable.
- Performance típica: <1ms para comparar 2 strings de 20 caracteres (por debajo de 0.5s p95 requerido).

**Alternatives considered**: 
- `python-Levenshtein`: Más rápido (C extension), pero añade dependencia; considerar SOLO si testing muestra latencia >100ms.
- Jaro-Winkler: Disponible en `fuzzywuzzy` (tercera dependencia); rechazado en favor de Levenshtein por consistencia con spec.

#### 2. Integración con SITE_DIRECTORY_DATABASE_URL

**Decision**: Consultar tabla `public.cellreference` directamente usando `asyncpg` (dependencia existente en proyecto).

**Rationale**:
- Variable de entorno `SITE_DIRECTORY_DATABASE_URL` ya existe y es usada en spec 002.
- `asyncpg` es async-first y se integra naturalmente con FastAPI.
- Esquema: tabla contiene columnas `nemonica` (PK o índice), `nodo` (4G/5G), `nodeb` (3G).

**Alternatives considered**:
- `psycopg2`: Síncrono; menos eficiente en contexto async de FastAPI.
- ORM (SQLAlchemy): Overkill; simple query es suficiente y más rápido.

#### 3. Normalization rules

**Decision**: Alinear con normalize_node_name de spec 002; reglas:
- `.strip()` para whitespace
- `.upper()` para comparación (si directorio usa mayúsculas)
- Retornar valor canónico almacenado (sin modificar caso/espacios del directorio)

**Rationale**: Consistencia con endpoint /nodes/{node-name} existente (spec 002).

**Alternatives considered**: None; reglas ya validadas en spec 002.

#### 4. Error codes y contratos

**Decision**: 
- HTTP 404 con estructura `{ "error": "not_found", "suggestions": [...], "user_input": "...", "resolved_node": null }`
- HTTP 503 con estructura `{ "error": "service_unavailable", "details": "site_directory_unreachable" }`
- HTTP 422 para entrada malformada (validación OpenAPI)

**Rationale**: Alineado con errores del endpoint /alarms/{site-name} actual.

**Alternatives considered**: 
- 400 para no encontrado: Menos específico; 404 es correcto semánticamente.
- Incluir full stack trace: Rechazado por seguridad; usar logging interno.

---

## PHASE 1: DESIGN & CONTRACTS (COMPLETE)

### Phase 1 Deliverables

✅ **data-model.md** — Entity definitions, relationships, validation rules
- Site (nemonica, nodo, nodeb, status, created_at, updated_at)
- Node (name, technology, site_nemonica)
- NameResolutionRecord (in-memory model for resolution state)
- SiteSuggestion (list item for recommendations)

✅ **contracts/http-alarms-endpoint.md** — HTTP response contracts
- Request: `GET /alarms/{site-name}?technology=...`
- 200 OK: Site resolved, alarms returned
- 404 Not Found: Site not found (with suggestions) OR missing mapping for technology
- 503 Service Unavailable: Site directory DB unreachable
- 422 Unprocessable Entity: Invalid technology parameter
- Performance requirement: ≤500ms p95

✅ **quickstart.md** — Validation scenarios (10 end-to-end test cases)
- Happy paths: basic resolution (4G), technology parameter (3G)
- Sad paths: site not found, missing mapping, service unavailable
- Edge cases: normalization (whitespace, case), full node name input
- Performance check, invalid parameters

### Post-Phase-1 Constitution Check

**✅ PASS** (re-checked after design):
1. **Arquitectura Conservadora**: Feature integrates into existing `/alarms/{site-name}` route; no new services, containers, or major restructuring. ✅
2. **Simplicidad**: Resolution is a DB lookup + Levenshtein similarity (no new patterns or abstractions). ✅
3. **Dependencias Livianas**: Uses stdlib `difflib` + existing `asyncpg` and FastAPI. If `python-Levenshtein` needed post-MVP, justification is clear. ✅

---

## Next Steps (Phase 2 & Beyond)

### Phase 2 — Task Generation (`/speckit-tasks`)
Execute `/speckit-tasks` command to generate:
- `tasks.md`: Dependency-ordered implementation tasks
- Each task covers:
  - `node_resolver.py` service implementation
  - `routes/alarms.py` integration
  - Unit tests + integration tests
  - DB schema/migration validation

### Phase 3 — Implementation (`/speckit-implement`)
Execute `/speckit-implement` to process all tasks in `tasks.md`.

### Phase 4 — Convergence & Validation
Use `/speckit-converge` to verify all design artifacts are reflected in code; append any remaining work to `tasks.md` if needed.

---

## Artifacts Summary

| Artifact | Path | Status | Purpose |
|----------|------|--------|---------|
| **plan.md** | `specs/005-alarms-node-resolution/plan.md` | ✅ Complete | Architecture & technical context |
| **research.md** | `specs/005-alarms-node-resolution/research.md` | ✅ Complete | Findings: Levenshtein (stdlib), asyncpg, DB schema, error contracts |
| **data-model.md** | `specs/005-alarms-node-resolution/data-model.md` | ✅ Complete | Entities, relationships, validation rules, lifecycle |
| **contracts/http-alarms-endpoint.md** | `specs/005-alarms-node-resolution/contracts/http-alarms-endpoint.md` | ✅ Complete | HTTP request/response schemas, error codes |
| **quickstart.md** | `specs/005-alarms-node-resolution/quickstart.md` | ✅ Complete | 10 validation scenarios (happy/sad paths, edge cases) |
| **tasks.md** | `specs/005-alarms-node-resolution/tasks.md` | ⏳ Pending | To be generated by `/speckit-tasks` |

---

## Document Metadata

- **Plan Version**: 1.0
- **Created**: 2026-11-09
- **Branch**: `005-alarms-node-resolution`
- **Spec**: [spec.md](./spec.md)
- **Constitution**: [.specify/memory/constitution.md](./../../../.specify/memory/constitution.md)
- **Next Command**: `/speckit-tasks` (when ready to generate task list)
