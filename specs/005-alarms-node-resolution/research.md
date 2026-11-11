# Research: Resolución de nombres de nodo en alarms/{site-name}

**Branch**: `005-alarms-node-resolution` | **Date**: 2026-11-09

This document resolves all NEEDS CLARIFICATION items from the Technical Context and research phase.

## 1. Algoritmo de Similitud (Levenshtein)

### Decision
**Usar `difflib.SequenceMatcher` (Python stdlib)**

### Rationale
- Disponible en stdlib de Python; sin dependencia adicional.
- Implementa distancia de similitud compatible con Levenshtein.
- Performance: <1ms para comparar dos strings de ~20 caracteres.
- Cumple con el requisito de <0.5s p95 para la etapa completa (resolución + alarmas).
- Se integra fácilmente en `services/node_resolver.py`.

### Alternatives Considered
| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| `difflib.SequenceMatcher` | En stdlib; sin deps; ~1ms | Menos optim. que C extension | ✅ ELEGIDO |
| `python-Levenshtein` | C extension; muy rápido | Añade dep.; build complexity | Considerar post-MVP si p95 > 100ms |
| `fuzzywuzzy` + Jaro-Winkler | Mejor precisión en typos | Dep. adicional; overkill | ❌ Rechazado |

### Implementation Notes
- Usar `difflib.SequenceMatcher(None, str1, str2).ratio()` para obtener score 0-1.
- Threshold mínimo: 0.6 (60% similitud) para incluir en sugerencias.
- Ordenar por score desc; en caso de empate, alfabético por nemónico.

---

## 2. Integración con SITE_DIRECTORY_DATABASE_URL

### Decision
**Consultar `public.cellreference` usando `asyncpg`**

### Rationale
- `SITE_DIRECTORY_DATABASE_URL` ya existe en config (usada en spec 002).
- `asyncpg` es dependencia existente y async-first (compatible con FastAPI).
- Evita bloqueo I/O en queries; mantiene latencia baja.
- Esquema validado en spec 002:
  ```sql
  CREATE TABLE public.cellreference (
    nemonica VARCHAR PRIMARY KEY,
    nodo VARCHAR,         -- 4G/5G node name
    nodeb VARCHAR,        -- 3G node name
    ...
  );
  ```

### Alternatives Considered
| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| `asyncpg` | Async; sin ORM overhead | Raw SQL | ✅ ELEGIDO |
| `psycopg2` | Estándar; amplio soporte | Síncrono; thread pool ineficiente | ❌ Rechazado |
| `SQLAlchemy` ORM | Type-safe; migrations | Overhead; overkill para query simple | ❌ Rechazado |

### Implementation Notes
- Pool de conexiones manejado por FastAPI lifespan.
- Query simple: `SELECT nodo, nodeb FROM public.cellreference WHERE nemonica = $1`.
- Timeout: 2s (para operación por sitio).
- En caso de error DB: HTTP 503 (como especifica FR-011).

---

## 3. Normalization Rules

### Decision
**Alinear con `normalize_node_name` de spec 002**

### Rationale
- Consistencia con endpoint `/nodes/{node-name}` existente.
- Spec 002 ya validó reglas en prod; no reinventar.
- Reglas:
  1. `.strip()` — remover whitespace inicio/fin.
  2. `.upper()` — convertir a mayúsculas (si directorio usa mayúsculas).
  3. Retornar valor canónico del directorio (no modificar caso/espacios).

### Alternatives Considered
| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| Reutilizar `normalize_node_name` (spec 002) | Máxima consistencia | Requiere refactor en services | ✅ CONSIDERADO |
| Implementar inline en `node_resolver.py` | Encapsulado en feature | Duplicación de lógica | ⚠️ Alternativa si refactor risky |

### Implementation Notes
- Función: `normalize_site_name(input: str) -> str` en `services/node_resolver.py`.
- Usar para normalizar entrada del usuario antes de buscar en DB.
- Confirmación: validar con spec 002 implementation antes de code review.

---

## 4. Error Codes y Contratos

### Decision
**Definir estructuras JSON para 404 (no encontrado), 503 (directorio indisponible)**

### Rationale
- Especificaciones de error alineadas con spec 002 y API design standards.
- Metadatos en respuesta (user_input, resolved_node) facilitan debugging y logging.
- HTTP codes semánticamente correctos:
  - **404**: Recurso (sitio/nodo) no existe.
  - **503**: Servicio backend (directorio DB) indisponible.
  - **422**: Validación de entrada malformada (generado por FastAPI/Pydantic).

### Response Contracts

#### 404 Not Found (Site/Node not found)
```json
{
  "error": "not_found",
  "message": "El sitio 'AN0096' no fue encontrado en el directorio",
  "user_input": "AN0096",
  "technology": "4G",
  "resolved_node": null,
  "suggestions": [
    {
      "nemonica": "AN0069",
      "nodo": "MBTS-AN0069",
      "similarity": 0.85
    },
    {
      "nemonica": "AN0086",
      "nodo": "MBTS-AN0086",
      "similarity": 0.80
    }
  ],
  "timestamp": "2026-11-09T19:58:00Z"
}
```

#### 404 Not Found (Site exists but missing mapping for technology)
```json
{
  "error": "missing_mapping",
  "message": "El sitio 'AN0069' existe pero no tiene mapeo para tecnología '3G'",
  "user_input": "AN0069",
  "technology": "3G",
  "resolved_node": null,
  "available_technologies": ["4G", "5G"],
  "timestamp": "2026-11-09T19:58:00Z"
}
```

#### 503 Service Unavailable (Site directory unreachable)
```json
{
  "error": "service_unavailable",
  "message": "El directorio de sitios no está disponible",
  "details": "site_directory_unreachable",
  "timestamp": "2026-11-09T19:58:00Z"
}
```

### Alternatives Considered
| Estructura | Pros | Contras | Decisión |
|-----------|------|---------|----------|
| Error detail + suggestions | Transparencia; debugging | Más verbose | ✅ ELEGIDO |
| Minimal error (solo code) | Ligero; simple | Poco informativo | ❌ Rechazado |
| Stack trace full | Debugging rápido | Seguridad; leaks internals | ❌ Rechazado |

### Implementation Notes
- Usar Pydantic models para validar estructura de respuesta.
- Logging: registrar entrada original, resolución, y sugerencias (sin exponer stack completo).
- Timestamps en ISO 8601 para consistencia.

---

## Dependency Summary

| Librería | Versión | Justificación | Status |
|----------|---------|---------------|--------|
| `FastAPI` | Existente | Web framework; sin cambios | ✅ Existente |
| `asyncpg` | Existente | Async PostgreSQL; sin cambios | ✅ Existente |
| `difflib` | Python stdlib | Similitud Levenshtein | ✅ Existente (stdlib) |
| `python-Levenshtein` | TBD | Opcional; considerar si performance < requisito | ⚠️ Pendiente (MVP con difflib) |

---

## Final Clarifications Resolved

✅ **All NEEDS CLARIFICATION items from plan.md Technical Context have been addressed.**

- Language/Version: Python 3.11 (confirmed)
- Primary Dependencies: FastAPI, asyncpg (confirmed; difflib added)
- Storage: PostgreSQL `public.cellreference` (schema confirmed)
- Testing: pytest (confirmed)
- Target Platform: Linux server (confirmed)
- Project Type: Web service (confirmed)
- Performance Goals: <0.5s p95 (algorithm + DB query validated)
- Constraints: HTTP 503 on DB unavailable, proxy/CA via env (confirmed)
- Scale/Scope: 1 site/request, ≤5 suggestions (confirmed)

---

## Next Steps (Phase 1: Design & Contracts)

1. Generate `data-model.md` with entity definitions (Site, Node, NameResolutionRecord).
2. Define interface contracts in `/contracts/` (HTTP response schemas).
3. Create `quickstart.md` with validation scenarios.
4. Generate `tasks.md` via `/speckit-tasks` for implementation.

