# Rate Limits & Gotchas

## Rate Limits

- System-wide gateway throughput: ~300 req/s across all endpoints.
- **No `Retry-After`/quota headers exist** — the client must self-throttle based on the concurrency caps below, and back off on `429`/`90064`.
- Per-endpoint concurrency caps are generally low; notable ones:
  - Login: max 30 concurrent, max 5,000 accumulated active sessions.
  - MML single command: max 30 concurrent.
  - Alarms — current: max 5 concurrent; historical/logs: max 2 concurrent.
  - Performance query creation: max 5 concurrent; result fetch: max 30 concurrent.
  - Lightweight performance queries: dynamic (10-300 concurrent, scales with managed NE count).
  - Topology NE query/modify: max 5 concurrent; lightweight NE query: max 10.
  - Backup/restore create: max 5 concurrent (max 10,000 tasks total).
- When adding a new integration, check the specific endpoint's cap in the original Huawei guide (Chapter 5.x, "Constraints") and size any internal semaphore/connection pool accordingly — do not assume a single global limit applies everywhere.

## Timeouts

- Topology cell info query: set client read timeout ≥ 5 minutes.
- Lightweight performance query: gateway itself cuts off at 20s server-side, returns HTTP 500 / `retCode 90012` ("query time is too long").
- No documented value for most other endpoints — 30-60s client timeout is a reasonable default.

## Gotchas (things that fail silently or confusingly)

- **Async results expire fast** — poll promptly:
  - Alarms / NE list / topology query tasks: deleted if not fetched within **1 minute**.
  - Measurement status query task: **1 minute**.
  - Setting-measurement task: **2 minutes** after completion.
  - NE create/modify/delete task status: **30 minutes**.
  - Performance query tasks (v1/v2): **12 hours** — explicitly delete after downloading to free resources.
  - MML batch script tasks: **2 days**.
  - iSStar script tasks: **2 days** after execution completes.
  - Uploaded `.hsp3` script files: **24 hours**.
- **413 payload-too-large trap**: requests over 2MB (MML scripts, batch configs) can get a `413` *and* an abrupt connection reset, so the HTTP client may raise a connection error instead of a clean 413 response. Validate payload size client-side before sending.
- **GET vs POST for backup file queries**: `GET` NE-backup-file routes only work if the NE name/FDN has no special characters (`/`, `=`, `[`, `]`); otherwise you must use the equivalent `POST` route.
- **Account lockout is API-unrecoverable**: 5 failed logins locks the account; only fixable via the MAE admin GUI. Don't build retry loops around login without a failure counter.
- **v1 vs v2 duplication**: Performance queries, lightweight performance queries, and iSStar task creation each have a deprecated `v1` path and an active `v2` path — always implement against `v2` for these.
- **Post-upgrade permission trap** (MAE V100R023C10 upgrade): third-party users previously in the default `NBI User Group` start failing with permission-denied after upgrade; must be manually rebound to `NBI OpenAPI User Group` by an admin. Relevant if the VM's MAE instance gets upgraded.
