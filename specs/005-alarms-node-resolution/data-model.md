# Data Model: Resolución de nombres de nodo en alarms/{site-name}

**Branch**: `005-alarms-node-resolution` | **Date**: 2026-11-09

This document defines the domain entities and their relationships for the site name resolution feature.

---

## Entities

### 1. Site (Sitio)

Representa un sitio de red identificado por un nemónico único.

#### Fields
| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `nemonica` | `VARCHAR` | PK, NOT NULL | Identificador único; ej. "AN0069". Normalizado a mayúsculas para búsqueda. |
| `nodo` | `VARCHAR` | NULL | Nombre completo del nodo para 4G/5G; ej. "MBTS-AN0069" o "MicroBTS-AN4689". |
| `nodeb` | `VARCHAR` | NULL | Nombre completo del nodo para 3G; ej. "UAN0069". |
| `region` | `VARCHAR` | NULL | Región geográfica (opcional); para futuros agrupamientos. |
| `status` | `VARCHAR` | DEFAULT 'active' | Estado del sitio: 'active', 'inactive', 'planned'. |
| `created_at` | `TIMESTAMP` | DEFAULT now() | Timestamp de creación (auditoría). |
| `updated_at` | `TIMESTAMP` | DEFAULT now() | Timestamp de última modificación. |

#### Validation Rules
- `nemonica` MUST be non-empty and unique.
- `nemonica` is normalized (stripped, uppercased) before DB lookups.
- At least one of `nodo` or `nodeb` MUST be non-null (site must have at least one mapping).
- `status = 'active'` is required for name resolution queries (inactive sites return as "not found").

#### State Transitions
- **Created** → `status = 'active'` (default on insert).
- **Active** → **Inactive**: Site remains in DB but excluded from resolution queries.
- **Inactive** → **Active**: Re-enable site for queries (no re-creation).

#### Indexes (for performance)
- PRIMARY KEY on `nemonica`.
- INDEX on `status` (filter active sites during resolution).
- INDEX on `nodo` (future: reverse lookups by node name if needed).
- INDEX on `nodeb` (future: reverse lookups by 3G node name if needed).

---

### 2. Node (Nodo)

Represent a fully-qualified network node name used by the Huawei API.

#### Fields
| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `name` | `VARCHAR` | PK | Nombre completo del nodo; ej. "MBTS-AN0069". |
| `technology` | `VARCHAR` | NOT NULL, ENUM('3G', '4G', '5G') | Tecnología a la que pertenece este nodo. |
| `site_nemonica` | `VARCHAR` | FK → Site.nemonica | Referencia al sitio asociado (usado para reverse resolution). |

#### Validation Rules
- `name` MUST match the canonical format stored in `public.cellreference`.
- `technology` MUST be one of: '3G', '4G', '5G'.
- `site_nemonica` MUST correspond to an active site (if not found during name resolution, return error).

#### State Transitions
None (nodes are read-only; created/updated via site maintenance).

#### Indexes (for performance)
- PRIMARY KEY on `name`.
- UNIQUE INDEX on (`technology`, `site_nemonica`) (ensure no duplicate mappings for same tech+site).

---

### 3. NameResolutionRecord

Encapsulates the input, resolution result, and metadata for a single name resolution request.

#### Fields (In-Memory Model)
| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `user_input` | `str` | NOT NULL | Entrada del usuario; ej. "AN0069" o "MBTS-AN0069". |
| `technology` | `str` | DEFAULT '4G', ENUM | Tecnología seleccionada (desde query param). |
| `resolved_site` | `Optional[Site]` | NULL | Sitio encontrado; NULL si no existe. |
| `resolved_node` | `Optional[str]` | NULL | Nombre canónico del nodo resuelto; NULL si no existe o no hay mapping. |
| `is_missing_mapping` | `bool` | DEFAULT False | True si sitio existe pero carece de mapeo para la tecnología. |
| `suggestions` | `List[SiteSuggestion]` | DEFAULT [] | Lista de sitios sugeridos si no hay coincidencia exacta. |
| `error_type` | `str` | ENUM | Tipo de error: None, 'not_found', 'missing_mapping', 'service_unavailable'. |
| `timestamp` | `datetime` | DEFAULT now() | Hora de la resolución. |
| `latency_ms` | `int` | ≥ 0 | Latencia total de la resolución (DB query + similarity search). |

#### Validation Rules
- `user_input` MUST be provided and non-empty.
- `technology` MUST be one of '3G', '4G', '5G'; defaults to '4G' if omitted.
- `resolved_site` and `resolved_node` are mutually exclusive with `error_type` (one result XOR error).
- `suggestions` MUST be ordered by similarity descending, then alphabetically by nemonica.
- `suggestions` MUST NOT exceed 5 items.
- `latency_ms` MUST be ≤ 500 (p95 requirement).

#### Transitions (Request Lifecycle)
1. **Input**: User provides `user_input` and optionally `technology`.
2. **Normalize**: Apply `normalize_site_name(user_input)` → normalized string.
3. **Lookup**: Query DB for `Site` with `nemonica = normalized`.
   - **Found + has mapping**: Set `resolved_site`, `resolved_node` (from `nodo` or `nodeb` per tech) → SUCCESS.
   - **Found + missing mapping**: Set `resolved_site`, `is_missing_mapping=True`, `error_type='missing_mapping'` → ERROR.
   - **Not found**: Compute `suggestions` using Levenshtein similarity. Set `error_type='not_found'` → ERROR.
4. **DB error**: Set `error_type='service_unavailable'` → ERROR (HTTP 503).
5. **Output**: Return `NameResolutionRecord` to caller (serialized as HTTP response).

---

### 4. SiteSuggestion

Represents a single suggested site in case of name resolution failure.

#### Fields
| Campo | Tipo | Restricciones | Descripción |
|-------|------|---------------|-------------|
| `nemonica` | `str` | NOT NULL | Nemónico del sitio sugerido. |
| `nodo` | `Optional[str]` | NULL | Nombre del nodo 4G/5G (si existe). |
| `nodeb` | `Optional[str]` | NULL | Nombre del nodo 3G (si existe). |
| `similarity` | `float` | 0.0 ≤ sim ≤ 1.0 | Puntuación de similitud (0=diferente, 1=idéntico). |

#### Validation Rules
- `nemonica` MUST match an active site in the DB.
- `similarity` MUST be computed using `difflib.SequenceMatcher` or equivalent.
- `similarity` MUST be ≥ 0.6 (threshold for inclusion in suggestions).
- List MUST be sorted by `similarity` descending; ties broken alphabetically by `nemonica`.

#### Serialization (JSON)
```json
{
  "nemonica": "AN0069",
  "nodo": "MBTS-AN0069",
  "nodeb": null,
  "similarity": 0.85
}
```

---

## Relationships

### Site ↔ Node (via NameResolutionRecord)
- **1:N** — A Site may have multiple Nodes (one per technology: 3G, 4G, 5G).
- **Resolved via**: User input → Site.nemonica (normalize) → Select Node.name based on requested technology.

### NameResolutionRecord → Site
- **N:1** — Each resolution request targets exactly one Site (or fails).

### NameResolutionRecord → SiteSuggestion
- **1:N** — A failed resolution may generate ≤5 suggestions (each pointing to an alternative Site).

---

## Data Constraints & Invariants

| Constraint | Rule | Enforcement |
|------------|------|-------------|
| **Unique nemonica** | No two sites share the same nemonica. | PK on `Site.nemonica`. |
| **Non-null mapping** | Every active site has at least one node mapping. | CHECK constraint or application-level validation. |
| **Similarity threshold** | Suggestions only include sites with ≥60% similarity. | Application-level filtering in `node_resolver.py`. |
| **Suggestion limit** | Max 5 suggestions per resolution. | Application-level sorting + limit(5). |
| **Canonical node names** | Node names are always returned as stored in DB (never modified). | Read-only on resolution; updates only via site maintenance. |
| **Technology coverage** | Every resolution request specifies a technology (defaults to 4G). | Application-level default. |
| **P95 latency** | Name resolution (DB lookup + similarity) completes in ≤500ms. | Performance testing + monitoring. |

---

## Future Considerations

- **Caching**: Consider in-memory cache of active sites (if DB queries exceed latency targets in prod).
- **Reverse lookups**: If feature 006+ needs to resolve Node.name → Site.nemonica, add indexes on `nodo`/`nodeb`.
- **Multi-site queries**: Spec currently supports 1 site/request; batch queries may require schema changes.
- **Audit trail**: Timestamp fields (`created_at`, `updated_at`) are present; consider adding change log table for site modifications.

