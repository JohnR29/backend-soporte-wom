# Pagination & Error Handling

## Pagination

### Mechanism A — cursor/marker (alarms, NE list, performance results, inventory)
- Request: `limit` (range/default varies by endpoint, see [endpoints.md](./endpoints.md)), `marker` (omit/empty on first call, echo the value from the previous response afterward).
- Response: `marker` (string = more pages exist; `null`/`"null"` = last page), `totalSize`/`count` (total matches).

### Mechanism B — pageNo/pageSize (admin/config/role/account APIs)
- Request body: `pageNo` (>0), `pageSize` (range varies: alarm masking logs 1-5000, roles 5-50, accounts 5-100).
- Response: `totalItems`/`total`, `totalPages`, `curPage`, `datas`/`data` (payload array).

## Error Envelope

Every response — success or failure — carries:
```json
{ "retCode": "90000", "retMessage": "Operation succeeded." }
```
Batch endpoints (e.g. multi-alarm ack) additionally return per-item failures (e.g. `badAlarmInformationReferenceList`) alongside an overall success/partial-success code.

## Key retCode reference

| retCode | Meaning |
|---|---|
| 90000 | Operation succeeded |
| 90001 | Missing parameter |
| 90026 / 90052 | Invalid parameter value |
| 90037 | Status: running (async, keep polling) |
| 90044 | Invalid marker |
| 90045 | No more results |
| 90054 | User lacks permission for these NEs |
| 90064 | Too many concurrent tasks/jobs (throttling) |
| 94001 | Incorrect username or password |
| 94002 | Account locked (5 failed logins — admin-only unlock) |
| 99030 | Access denied |
| 99040 | URL not found |

Full table (90+ codes) is in the original Huawei Developer Guide, Chapter 6 — extend this table here if a new code is encountered in practice.

## Retryable vs Terminal

**Retry / poll:**
- HTTP `202 Accepted`, or `retCode 90037` ("running"/"data being collected") → poll again.
- HTTP `429` or `retCode 90064`/`90004` (concurrency/throttling) → backoff and retry.
- Task state `0` (waiting) / `1` (executing) → keep polling.

**Terminal (do not blindly retry):**
- HTTP `400` / `retCode 90026`/`90052` (bad params) → fix the request.
- HTTP `401` → re-authenticate (see [authentication.md](./authentication.md)), then retry once.
- HTTP `403` / `retCode 90054`/`99030` → permissions issue, needs admin action.
- HTTP `404` / `retCode 90048` → referenced task/file expired or missing, recreate it.
- HTTP `415` → wrong upload file type/extension.
