# Authentication

## Token Acquisition (Login)

`PUT /api/rest/securityManagement/v1/oauth/token`

Headers: `Content-Type: application/json`

Body:
```json
{
    "grantType": "password",
    "userName": "northAPIUser",
    "value": "MyPassword123!"
}
```

Response:
```json
{
    "accessSession": "x-o5gb05o8eo1...",
    "roaRand": "58a68cd75382dd55189d0b855463fc2370b994bfdbfead27",
    "expires": 1800,
    "additionalInfo": null
}
```

- `accessSession` → send as `X-Auth-Token` header on every subsequent request.
- `roaRand` → CSRF token, must be included on all **non-GET** requests.
- `expires` → 1800 seconds (30 min) idle timeout, not configurable for third-party users.

## Session Renewal

- Any successful authenticated call automatically renews the 30-minute idle window.
- To renew without side effects, call the Handshake API: `POST /api/rest/securityManagement/v1/oauth/handshake`, header `X-Auth-Token`. Empty `{}` response body on success.
- Expired/invalid token → HTTP `401 Unauthorized`. Must re-login; there is no refresh-token flow.

## Logout

`DELETE /api/rest/securityManagement/v1/oauth/token`, header `X-Auth-Token` → `204 No Content`.

## Account Lockout

5 consecutive failed login attempts locks the account (`retCode 94002`). This **cannot be fixed via the API** — an administrator must unlock it from the MAE GUI. Do not build automatic login retry loops without a failure counter.

## TLS / Certificate

- Requires TLS 1.2+.
- The client must trust the MAE gateway's own `APIGWService` certificate, exported manually from the MAE admin GUI (`Common > Security > Certificate Management > Service Certificate Management > APIGWService > Identity Certificates > Export`).
- This exported cert is what `HUAWEI_CA_CERT_PATH` should point to.
