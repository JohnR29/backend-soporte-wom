# Data Model: Implementar el contrato de API Operaciones

This feature changes API response semantics only. It introduces no persisted entities, database tables, migrations, or ownership changes. The site-directory rows remain owned by the external directory and are read through the existing resolver.

## Name Resolution

| Field | Type | Meaning / validation |
|---|---|---|
| `input` | string | Original identifier supplied by the caller; preserve its spelling and whitespace. |
| `resolved` | string or null | Canonical value from the directory (`nodeb` for 3G; `nodo` for 4G/5G/KPIs), or null if not resolved. |
| `status` | string | Existing resolver status, including `resolved`, `not_found`, `missing_mapping`, and `ambiguous_mapping`. |
| `error` | string, optional | Human-readable resolution detail where resolution failed. |
| `suggestions` | array of strings, optional | Up to five site suggestions for `not_found`; empty when there are no candidates. |

The original request identifier remains distinct from the canonical value sent to Huawei. No prefixes are inferred or modified outside directory values.

## Node Error

| Field | Type | Meaning / validation |
|---|---|---|
| `code` | string or null | `NODE_NOT_FOUND`, `NODE_DISCONNECTED`, `TECHNOLOGY_UNAVAILABLE`, or null for other per-node/controller failures. |
| `message` | string | Spanish, user-readable explanation. |
| `input` | string | Original requested identifier. |
| `ne_name` | string or null | Canonical resolved node, controller name for controller failures, or null if unavailable. |
| `error` | string, optional | Original Huawei error text, retained for compatibility when present. |
| `suggestions` | array of strings, optional | Included for not-found errors when suggestions are available. |

Node errors are returned in HTTP 200 responses. HTTP-level failures use the established `detail` shape and must not contain the stable node codes in `errors[].code`.

## Technology State Result

The 3G, 4G, and 5G success/result envelope retains existing fields: `records`, `count`, `errors`, and `name_resolution`; the current command and UMTS metadata fields also remain unchanged. Valid `records` coexist with node/controller errors when the contract permits partial results.

State rules:

- Unknown directory identifier: `NODE_NOT_FOUND`; do not call Huawei.
- Existing node without a usable technology mapping, or connected node with no cells for that technology: `TECHNOLOGY_UNAVAILABLE`.
- 4G/5G disconnected NE: `NODE_DISCONNECTED`, with no records for that node.
- 3G where all RNCs report “NodeB is not configured”: `NODE_NOT_FOUND`.
- 3G where every returned cell has `Operation state = "Unavailable"`: keep all cells and add `NODE_DISCONNECTED`.
- Mixed 3G cell availability: keep all cells and do not add `NODE_DISCONNECTED`.
- Per-node/controller/command failures do not remove valid records from other results.

## Alarm

The existing alarm fields and pagination envelope (`site_name`, `alarms`, `count`, `marker`) are retained. `alarmClearedTime` is the authoritative normalized state:

- Null time, including Huawei epoch zero: `cleared = "Activa"`.
- Non-null ISO 8601 time: `cleared = "Limpia"`.
- Contradictory upstream `cleared` values are ignored for this field.

Only the existing `dataType=CURRENT` query is used; there is no historical alarm entity/query added.

## KPI Measurement

Each KPI record retains the current flattened fields: `startTime`, `neName`, `Cell Name`, `Local Cell ID`, and the configured counter values. The response adds/retains `errors` and `name_resolution` while preserving existing fields.

- Query window is the existing latest fixed 24-hour period and each returned row retains `startTime` in Chile local time without an explicit zone.
- Caller-provided `period_start` and `period_end` are ignored.
- Unresolved identifiers receive `NODE_NOT_FOUND`; records from resolved identifiers are preserved.
- A resolved identifier with no measurements produces no node error and does not imply disconnected status.
