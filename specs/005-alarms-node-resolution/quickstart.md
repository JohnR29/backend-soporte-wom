# Quickstart: Validation Scenarios for Name Resolution Feature

**Branch**: `005-alarms-node-resolution` | **Date**: 2026-11-09

This guide provides runnable validation scenarios to verify that the name resolution feature works end-to-end.

---

## Prerequisites

1. **Backend running**: Start the FastAPI backend with name resolution enabled.
   ```bash
   cd backend-soporte
   conda activate backend-soporte
   uvicorn app.main:app --reload
   ```
   Expected: Server listens on `http://localhost:8000`

2. **Database accessible**: Verify `SITE_DIRECTORY_DATABASE_URL` in `.env` points to PostgreSQL with `public.cellreference`.
   ```bash
   psql "$SITE_DIRECTORY_DATABASE_URL" -c "SELECT nemonica, nodo, nodeb FROM public.cellreference LIMIT 3;"
   ```
   Expected: Returns ≥3 rows with nemonica, nodo, and/or nodeb columns.

3. **Test data in database**:
   ```bash
   psql "$SITE_DIRECTORY_DATABASE_URL" << SQL
   INSERT INTO public.cellreference (nemonica, nodo, nodeb, status)
   VALUES
     ('AN0069', 'MBTS-AN0069', 'UAN0069', 'active'),
     ('AN0086', 'MBTS-AN0086', NULL, 'active'),
     ('AN4689', 'MicroBTS-AN4689', NULL, 'active')
   ON CONFLICT (nemonica) DO NOTHING;
   SQL
   ```
   Expected: ≥0 rows inserted (OK if rows already exist).

4. **Huawei API mock or real endpoint**: Ensure the backend can reach Huawei API (or use a mock via `pytest` fixtures).

---

## Scenario 1: Happy Path — Site resolved successfully (4G, default)

**Objective**: Verify that a user can query alarms with a site nemónico, and the backend resolves the full node name and returns alarms.

### Setup
Ensure site "AN0069" exists in DB with `nodo = "MBTS-AN0069"`.

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/AN0069" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `200 OK`
- **Body includes**:
  ```json
  {
    "error": null,
    "resolved_site": "AN0069",
    "resolved_node": "MBTS-AN0069",
    "technology": "4G",
    "user_input": "AN0069",
    "alarms": [
      { "id": "...", "node": "MBTS-AN0069", ... }
    ]
  }
  ```
- **Verification**: `resolved_node` matches DB value, `technology` defaults to "4G", alarms list is non-empty (or empty if no alarms exist; valid either way).

---

## Scenario 2: Happy Path — Site resolved with 3G technology

**Objective**: Verify that `technology=3G` parameter correctly selects the `nodeb` column.

### Setup
Ensure site "AN0069" exists with `nodeb = "UAN0069"`.

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/AN0069?technology=3G" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `200 OK`
- **Body includes**:
  ```json
  {
    "error": null,
    "resolved_site": "AN0069",
    "resolved_node": "UAN0069",
    "technology": "3G",
    "user_input": "AN0069",
    "alarms": [...]
  }
  ```
- **Verification**: `resolved_node = "UAN0069"` (from `nodeb` column), `technology = "3G"`.

---

## Scenario 3: Sad Path — Site not found; suggestions provided

**Objective**: Verify that typos are caught and alternatives are suggested (Levenshtein similarity).

### Setup
Ensure DB contains sites "AN0069", "AN0086", etc. Query for non-existent site "AN0096".

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/AN0096" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `404 Not Found`
- **Body includes**:
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
    ]
  }
  ```
- **Verification**:
  - Suggestions are sorted by `similarity` descending.
  - Most similar site (AN0069) appears first.
  - All suggestions have similarity ≥ 0.6.
  - Max 5 suggestions included.

---

## Scenario 4: Sad Path — Site exists but missing mapping for technology

**Objective**: Verify that missing column for a specific technology is reported distinctly.

### Setup
Ensure site "AN0086" exists with `nodo = "MBTS-AN0086"` but `nodeb = NULL`.

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/AN0086?technology=3G" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `404 Not Found`
- **Body includes**:
  ```json
  {
    "error": "missing_mapping",
    "message": "El sitio 'AN0086' existe pero no tiene mapeo para la tecnología '3G'",
    "user_input": "AN0086",
    "technology": "3G",
    "resolved_site": "AN0086",
    "resolved_node": null,
    "suggestions": [],
    "available_technologies": ["4G", "5G"]
  }
  ```
- **Verification**:
  - `error = "missing_mapping"` (distinct from "not_found").
  - `resolved_site` is set (site exists).
  - `available_technologies` lists techs for which this site has mappings.
  - Suggestions list is empty (site found, just wrong tech).

---

## Scenario 5: Sad Path — Directory unavailable (503)

**Objective**: Verify that when the site directory DB is unreachable, HTTP 503 is returned and Huawei is not called.

### Setup
Temporarily move/rename `.env` variable `SITE_DIRECTORY_DATABASE_URL` to an invalid value, OR stop the PostgreSQL service.

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/AN0069" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `503 Service Unavailable`
- **Body includes**:
  ```json
  {
    "error": "service_unavailable",
    "message": "El directorio de sitios no está disponible",
    "details": "site_directory_unreachable",
    "timestamp": "2026-11-09T19:58:00Z"
  }
  ```
- **Verification**:
  - HTTP 503 is returned (not 500 or 404).
  - No Huawei API call is made (check logs or mock to confirm).
  - Error message is clear and actionable.

### Cleanup
Restore `SITE_DIRECTORY_DATABASE_URL` to correct value or restart PostgreSQL.

---

## Scenario 6: Edge Case — Input normalization (whitespace, case)

**Objective**: Verify that user input is normalized (trim, uppercase) before matching.

### Setup
Ensure site "AN0069" exists (uppercase in DB).

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/%20an0069%20" \
  -H "Accept: application/json"
```
(URL-encoded: space + "an0069" + space)

### Expected Response
- **Status**: `200 OK`
- **Body includes**:
  ```json
  {
    "error": null,
    "resolved_site": "AN0069",
    "user_input": " an0069 ",
    ...
  }
  ```
- **Verification**:
  - Trimmed and uppercased input resolves correctly.
  - `user_input` shows the original input as provided.
  - `resolved_site` shows the canonical nemonica from DB.

---

## Scenario 7: Edge Case — Full node name (already canonical) as input

**Objective**: Verify that a user can also provide the full node name (not just nemónico) and it resolves correctly.

### Setup
Ensure DB has site with `nodo = "MBTS-AN0069"`.

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/MBTS-AN0069" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `200 OK` or `404 Not Found` (depending on implementation choice):
  - **Option A (Preferred)**: Resolve to nemonica "AN0069" and use its nodo.
    ```json
    {
      "error": null,
      "resolved_site": "AN0069",
      "resolved_node": "MBTS-AN0069",
      "user_input": "MBTS-AN0069"
    }
    ```
  - **Option B**: Treat full node name as not-found and suggest similar nemonica values.
    ```json
    {
      "error": "not_found",
      "user_input": "MBTS-AN0069",
      "suggestions": [{ "nemonica": "AN0069", ... }]
    }
    ```
- **Verification**: Behavior is consistent with specification requirement FR-005 (verify canonical form before using).

---

## Scenario 8: Performance — Latency check

**Objective**: Verify that name resolution completes within performance budget.

### Setup
DB with ≥100 active sites.

### Test Command
```bash
# Run 10 sequential requests and measure time
time for i in {1..10}; do
  curl -X GET "http://localhost:8000/alarms/AN0069" \
    -H "Accept: application/json" \
    -s -o /dev/null
done
```

### Expected Response
- **Total time for 10 requests**: ≤ 5 seconds (500ms per request, p95).
- **Verification**: 
  - Average latency per request: ≤ 500ms.
  - Check backend logs for DB query time (should be <300ms).

---

## Scenario 9: Invalid technology parameter (422)

**Objective**: Verify that invalid `technology` values are rejected with HTTP 422.

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/AN0069?technology=2G" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `422 Unprocessable Entity`
- **Body includes**:
  ```json
  {
    "detail": [
      {
        "type": "enum",
        "loc": ["query", "technology"],
        "msg": "Input should be '3G', '4G' or '5G'",
        "input": "2G"
      }
    ]
  }
  ```
- **Verification**: Parameter validation is strict (enum-based).

---

## Scenario 10: Empty site-name (422)

**Objective**: Verify that empty `site-name` path parameter is rejected.

### Test Command
```bash
curl -X GET "http://localhost:8000/alarms/" \
  -H "Accept: application/json"
```

### Expected Response
- **Status**: `404 Not Found` (path not found, since `/alarms/` without parameter doesn't match route) OR `422` depending on FastAPI routing.
- **Verification**: Invalid input is caught and reported clearly.

---

## Integration with Existing Endpoint (Reference)

The feature extends `/alarms/{site-name}` (existing in spec 002). After resolution succeeds, the backend calls the **existing Huawei alarm logic** without modification. All test scenarios above assume the Huawei integration is already working (or mocked).

---

## Cleanup / Reset

After testing, reset the database to its original state (if test data was inserted):
```bash
psql "$SITE_DIRECTORY_DATABASE_URL" << SQL
DELETE FROM public.cellreference
WHERE nemonica IN ('AN0069', 'AN0086', 'AN4689');
SQL
```

Or if test data should remain, document it in a `.sql` migration file for `alembic/`.

---

## Summary Checklist

- [ ] Scenario 1: Site resolved (4G default) ✅ 200 OK, alarms returned
- [ ] Scenario 2: Site resolved (3G param) ✅ 200 OK, correct nodeb used
- [ ] Scenario 3: Not found with suggestions ✅ 404, suggestions ranked
- [ ] Scenario 4: Missing mapping ✅ 404 missing_mapping, available_technologies shown
- [ ] Scenario 5: Directory unavailable ✅ 503, no Huawei call
- [ ] Scenario 6: Input normalization ✅ Whitespace/case handled
- [ ] Scenario 7: Full node name input ✅ Resolved or not found consistently
- [ ] Scenario 8: Performance ✅ ≤500ms p95
- [ ] Scenario 9: Invalid technology ✅ 422 Unprocessable Entity
- [ ] Scenario 10: Empty parameter ✅ Error caught

Once all scenarios pass, the feature is ready for code review and integration.

