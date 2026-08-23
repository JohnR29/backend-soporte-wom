# Endpoints

All requests require header `X-Auth-Token` (see [authentication.md](./authentication.md)) unless noted otherwise. Base URL: `https://[MAE_IP]:31127`.

## MML Commands

### Issue single MML command (synchronous)
`POST /api/rest/mmlManagement/v1/command`

Body: `{ "command": "LST VER:;", "neNames": ["pml", "pTest"] }` (max 100 NEs; duplicates are de-duplicated server-side).

Response includes `results[]` with per-NE `report`, `result`, `retCode`.

### Create async MML batch task (script upload)
`POST /api/rest/mmlManagement/v1/tasks`, `Content-Type: multipart/form-data`

Form fields: `file` (TXT script, max 2MB), `taskName` (optional), `secretKey` (optional, encrypts script), `runMode` (`serial`|`parallel`, default `parallel`).

Response: `{ "taskId": "123" }`. Task auto-deleted 2 days after creation.

## Alarms

### Query alarms
`GET /api/rest/faultSupervisonManagement/v1/alarms`

Query params: `dataType` (`CURRENT`|`HISTORY`|`ALARM_LOG`|`EVENT_LOG`, required), `alarmAckState`, `baseObjectInstance`, `filter` (URL-encoded JSON, max 1500 chars), `specialAlarm` (bool), `limit` (1-1000, default 500), `marker` (cursor).

Response: `alarmInformationList[]`, `marker` (next-page cursor or null), `retCode`/`retMessage`.

**Gotcha**: query results are deleted if not fetched within 1 minute of task creation.

## Performance Management (prefer v2, v1 deprecated)

### Create performance query task
`POST /api/rest/performanceManagement/v2/measurementResults`

Body: `timeFormat`, `startTime`, `endTime` (must be within 24h of `startTime`), `period` (minutes), `counterIds` (max 150, ≤10 function subsets), `isQueryAllNe` (0|1), `neTypeName`/`ratTypeName` (if `isQueryAllNe=1`), `neNames` (if `isQueryAllNe=0`, all same NE type).

Small results return directly; large ones return `202 Accepted` + `{ "retCode": "90037", "taskId": "1" }` — poll the fetch endpoint below.

### Fetch performance query results
`GET /api/rest/performanceManagement/v2/measurementResults/{taskId}?limit=&marker=`

Response includes `result[]`, `marker` (null = last page), `totalSize`. Task auto-deleted 12h after creation — delete explicitly after download to free resources.

## Topology / NE Management

### Query NE list
`GET /api/rest/resourceManagement/v1/neList`

Query params: `attrSelector` (comma-separated fields), `filter` (URL-encoded JSON, max 1024 chars), `limit` (1-5000, default 5000), `marker`.

### Create/modify/delete NEs (batch, max 100 per call)
`PATCH /api/rest/resourceManagement/v1/neList?confirm=`

Body: array of `{ fdn | neName, attributes: { name, IP, neType, subnet, subarea, enableSSL, enableAuthPeer } }`. `confirm=true` required to execute deletions. `enableAuthPeer` supports `"true"`/`"false"`/`"PSK"` for NE-side mutual TLS.

Response: `{ "href": "/api/rest/resourceManagement/v1/taskStatus/15", "id": "15" }` — poll `href` for completion. Result cleared if not queried within 30 min.

## Session Management

See [authentication.md](./authentication.md) for Login/Logout/Handshake.
