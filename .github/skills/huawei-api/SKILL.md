---
name: huawei-api
description: 'Reference for integrating with the Huawei iMaster MAE-Access V100R026C10 Open API (auth, endpoints, pagination, error codes, rate limits, TLS). Use when implementing or debugging any route in app/api/routes/ that calls the Huawei API, or when adding a new Huawei endpoint to huawei_client.py.'
---

# Huawei iMaster MAE-Access Open API

Source: official Huawei MAE-Access V100R026C10 Developer Guide (see references below for full extracted detail).

## When to Use
- Adding a new route under `app/api/routes/` that proxies a Huawei MAE endpoint.
- Extending `app/services/huawei_client.py` (auth/session handling, error mapping).
- Debugging an unexpected Huawei API response (401, 429, 90xxx `retCode`, etc.).

## Core Facts

- **Auth**: token-based, not OAuth2/API-key. `PUT /api/rest/securityManagement/v1/oauth/token` with `{grantType, userName, value}` returns `accessSession` (send as `X-Auth-Token` header on every subsequent call) and `roaRand` (CSRF token, required on non-GET requests). Session expires after 30 min idle; call the Handshake API or make any authenticated request to renew it. Details: [authentication.md](./references/authentication.md).
- **Base URL**: `https://[MAE_IP]:31127`, versioned by path segment (`v1`, `v2` coexist per module — prefer `v2` where available, `v1` is being phased out).
- **Endpoints**: MML commands, alarms, performance queries, topology/NE management, etc. Full request/response shapes: [endpoints.md](./references/endpoints.md).
- **Pagination**: two mechanisms — cursor/`marker`+`limit` for high-volume data (alarms, NE list, performance results), and `pageNo`+`pageSize` for admin/config APIs. `marker: null` means no more pages. Details: [pagination-and-errors.md](./references/pagination-and-errors.md).
- **Errors**: every response carries a `retCode`/`retMessage` envelope in addition to the HTTP status. Full code table and retryable-vs-terminal classification: [pagination-and-errors.md](./references/pagination-and-errors.md).
- **Rate limits**: per-endpoint concurrency caps (as low as 2-5 concurrent requests for some queries), not a simple global rate limit. No `Retry-After`/quota headers exist — the client must self-throttle. Details: [rate-limits-and-gotchas.md](./references/rate-limits-and-gotchas.md).
- **TLS**: requires TLS 1.2+; the MAE gateway's own `APIGWService` certificate must be exported from the MAE GUI and trusted client-side — this is the cert that goes in `HUAWEI_CA_CERT_PATH` (see [huawei_client.py](../../../app/services/huawei_client.py)).
- **Gotchas that cause silent failures**: async task results are auto-deleted 1 min–2 days after creation depending on the endpoint (poll promptly); payloads over 2MB can trigger a `413` with a reset connection instead of a clean error body; 5 failed logins locks the account (unlockable only via admin GUI, not via API). Full list: [rate-limits-and-gotchas.md](./references/rate-limits-and-gotchas.md).

## Procedure: Adding a New Huawei Endpoint

1. Look up the endpoint's method/path/params in [endpoints.md](./references/endpoints.md); if not listed, check the official guide section referenced there.
2. Check [pagination-and-errors.md](./references/pagination-and-errors.md) for the pagination mechanism and error codes this endpoint can return.
3. Check [rate-limits-and-gotchas.md](./references/rate-limits-and-gotchas.md) for the concurrency cap and any auto-expiry timing that affects retry/polling logic.
4. Implement the call through `get_client()` in `app/services/huawei_client.py` — do not create a separate client.
5. Add the route in `app/api/routes/huawei.py` (or a new file registered in `app/main.py`), translating `retCode` failures into appropriate HTTP responses rather than passing Huawei's envelope straight through.
