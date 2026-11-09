# Data Model: API de Operaciones para Telebot

This document describes the response concepts in the target contract. It does not introduce database entities or migrations.

## Name Resolution

One entry is returned for each submitted identifier.

| Field | Type | Meaning and rules |
|---|---|---|
| `input` | string | Original user-supplied value; preserve it in the response. |
| `resolved` | string or null | Canonical value from the site directory for the requested technology. Null when unresolved or when the mapping is unavailable/ambiguous. |
| `status` | string | `resolved`, `not_found`, `missing_mapping`, or `ambiguous_mapping`. |
| `error` | string, optional | Human-readable resolution detail when resolution did not succeed. |
| `suggestions` | array of strings, optional | Directory suggestions for `not_found`; at most five. |

Matching trims external whitespace and ignores case. Resolution uses `nodeb` for 3G and `nodo` for 4G, 5G, and KPIs, and may match the site name. No prefix is added, removed, or inferred.

## Technology Result

3G, 4G, and 5G responses retain their existing technology-specific fields and include:

| Field | Type | Rules |
|---|---|---|
| `records` | array | Preserve every valid record even when another node, controller, or command fails. |
| `count` | integer | Number of returned records. |
| `errors` | array of Node Error | Per-node or per-controller errors; non-node errors retain their source text and use `code: null`. |
| `name_resolution` | array of Name Resolution | One resolution result per requested identifier. |

An error for a node is returned with HTTP 200. Preserve valid records when a node-level error is also reported. For 3G, all returned cells with `Operation state = "Unavailable"` produce `NODE_DISCONNECTED` alongside the preserved records; mixed availability does not. HTTP-level failures remain distinct and do not use the stable node error codes.

## Node Error

| Field | Type | Rules |
|---|---|---|
| `code` | string or null | `NODE_NOT_FOUND`, `NODE_DISCONNECTED`, `TECHNOLOGY_UNAVAILABLE`, or null for other per-node/controller failures. |
| `message` | string | Readable Spanish text suitable for the consumer. |
| `input` | string | Original identifier from the request. |
| `ne_name` | string or null | Resolved node value, if available; controller name for an existing per-controller source error. |
| `error` | string, optional | Original Huawei/source error retained for compatibility. |
| `suggestions` | array of strings, optional | Suggestions when the code is `NODE_NOT_FOUND` and candidates exist. |

Stable code semantics:

- `NODE_NOT_FOUND`: identifier absent from the directory; Huawei says the NE does not exist; or every RNC reports that a directory-mapped 3G NodeB is not configured.
- `NODE_DISCONNECTED`: in 4G/5G, Huawei reports an existing NE is not connected and supplied no data. For 3G, all returned cells have `Operation state = "Unavailable"`; retain those records and include the node error. Mixed cell availability does not produce this code. Do not infer it for KPIs from empty measurements.
- `TECHNOLOGY_UNAVAILABLE`: mapping is missing/ambiguous, or a connected node returns no cells for the requested state technology. Do not emit it when the node is disconnected.

## Alarm

The site alarm response retains `site_name`, `alarms`, `count`, and `marker`. Each alarm retains the existing Huawei-derived fields, including `alarmId`, `alarmName`, `meName`, `perceivedSeverity`, `alarmRaisedTime`, `alarmClearedTime`, `cleared`, and other current fields.

The target invariant is derived from the normalized clear time: `alarmClearedTime == null` exactly when `cleared == "Activa"`; a non-null clear time corresponds to `cleared == "Limpia"`. The endpoint remains limited to the current `CURRENT` query; it does not fetch historical alarms.

## KPI Measurement Result

The KPI response retains `records` and `name_resolution` and adds `errors` for identifiers that cannot be resolved. Each measurement record retains its current KPI fields and includes `startTime` in Chile local time without an explicit zone. The query window is the latest published 24-hour window.

A resolved node with no returned measurements produces no record and no error. The contract does not infer a disconnected state from missing KPI data. The response does not add `count` or period request fields.

## HTTP Error Boundary

Authentication, request validation, Huawei communication/rejection, and directory availability remain HTTP-level errors (401, 422, 502/504, 400, and 503 as applicable). These are not represented as `Node Error` items and do not contain stable node error codes.