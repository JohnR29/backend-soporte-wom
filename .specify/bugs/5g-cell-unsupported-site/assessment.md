# Bug Assessment: 5G Cell Summary Returns Incorrect Error for Unsupported Technology

- **Slug**: 5g-cell-unsupported-site
- **Created**: 2026-11-09T16:54:12
- **Source**: Pasted text (curl request and response)
- **Verdict**: Valid
- **Severity**: High

## Report (verbatim or summarized)

User reports that when querying 5G cell status (`/mml/cell-summary-nr`) for a site (RM3644) that does not have 5G technology, the error is misclassified as `NODE_NOT_FOUND` instead of `TECHNOLOGY_UNAVAILABLE`.

**Curl Request**:
```bash
curl -X 'POST' \
  'http://localhost:8000/mml/cell-summary-nr' \
  -H 'accept: */*' \
  -H 'Authorization: Bearer test-token' \
  -H 'Content-Type: application/json' \
  -d '{
  "ne_names": [
    "RM3644"
  ]
}'
```

**Actual Response**:
- Error code: `NODE_NOT_FOUND`
- Message: "No se encontró el nodo RM3644."
- Raw Huawei error: `RETCODE = 939589973 Command does not exist or resources are not ready.`

**Expected Behavior**: 
- Error code should be `TECHNOLOGY_UNAVAILABLE`
- Message: "El nodo no tiene la tecnología 5G disponible."

## Symptom

When a Huawei node (e.g., MBTS-RM3644) does not support a specific technology (5G), the Huawei MML command `DSP NRCELL:;` returns a RETCODE indicating the command does not exist or resources are not ready. The API endpoint incorrectly interprets this as a node-not-found error rather than a technology-unavailable error. This misleads users into thinking the node name is invalid when the node exists but simply lacks 5G capabilities.

## Reproduction

1. Identify a network element that lacks 5G (NR) technology.
2. POST to `/mml/cell-summary-nr` with that element's name (e.g., `RM3644`).
3. Observe that the returned error has code `NODE_NOT_FOUND` and contains the raw Huawei retcode `939589973` (Command does not exist).
4. Expected: error code should be `TECHNOLOGY_UNAVAILABLE`.

**Huawei Raw Error Message**:
```
+++    MBTS-RM3644        2026-11-09 16:26:05
O&M    #17551
%%/*1882672124*/DSP NRCELL:;%%
RETCODE = 939589973  Command does not exist or resources are not ready.
---    END
```

## Suspected Code Paths

- [app/api/routes/huawei.py:930-955](file:///C:/Users/jcrojasm/Documents/SoporteRAN/Proyectos/backend-soporte/app/api/routes/huawei.py) — `_technology_unavailable_errors()` function; it checks `record_names` to detect which nodes are missing from successful results, but does not distinguish between:
  - **No records because the command failed entirely** (technology unavailable), vs.
  - **No records because something else went wrong** (node not found, disconnected, etc.).

- [app/api/routes/huawei.py:724-766](file:///C:/Users/jcrojasm/Documents/SoporteRAN/Proyectos/backend-soporte/app/api/routes/huawei.py) — `_state_payload_errors()` function; it normalizes and classifies errors by checking for keywords like "not found" / "not exist" / "not connected", but does not detect the specific pattern for "command does not exist" which indicates a technology unavailability.

- [app/api/routes/huawei.py:920-975](file:///C:/Users/jcrojasm/Documents/SoporteRAN/Proyectos/backend-soporte/app/api/routes/huawei.py) — `create_cell_summary_nr()` function; when `nrcell_dataframe.empty`, it calls `_technology_unavailable_errors()` with `record_names=set()`, but that function only catches nodes in the unresolved/failed sets, **not** nodes that appear in `failed_names` but with a "command does not exist" error.

## Root Cause Hypothesis

**Confidence: High**

The logic in `_technology_unavailable_errors()` tries to detect unavailable technologies by checking if a resolved node's name appears **neither** in successful results (`record_names`) **nor** in failed results (`failed_names`). However, when the Huawei `DSP NRCELL:;` command fails for a node, it returns an error result. The error is then classified by `_state_payload_errors()` as `NODE_NOT_FOUND` (because the error string matches "not found" patterns from earlier parsing), and the node is added to `failed_names`, so it is **excluded** from `_technology_unavailable_errors()`.

The problem: **The detection order is wrong.** The node does appear in `failed_names` (because `_state_payload_errors()` already classified the error), so `_technology_unavailable_errors()` filters it out. Meanwhile, `_state_payload_errors()` cannot distinguish between "command does not exist" (technology unavailable) and "node not found" (connectivity issue) because the raw error text does not clearly indicate this.

The Huawei raw error `RETCODE = 939589973 Command does not exist or resources are not ready` should be interpreted as a technology-unavailable indicator, not a node-not-found indicator. Currently, the code does not check for this specific retcode or message pattern.

## Proposed Remediation

**Preferred**: 

1. **Enhance `_state_payload_errors()` to detect technology-unavailable patterns:**
   - Add a check for retcode `939589973` (Command does not exist) or the phrase "Command does not exist" in raw error messages.
   - When detected, classify the error as `TECHNOLOGY_UNAVAILABLE` instead of `NODE_NOT_FOUND`.

2. **Refactor the error classification flow:**
   - Within `_state_payload_errors()`, check for technology unavailability **before** defaulting to "node not found".
   - Example pattern: if raw error contains "939589973" or "Command does not exist", return code `TECHNOLOGY_UNAVAILABLE` with message "La tecnología 5G no está disponible en este nodo."

3. **Update `create_cell_summary_nr()` to handle the new error code:**
   - No change needed if the error code is correctly set; the endpoint already returns `errors` list to the caller.

**Files likely to change**:
- `app/api/routes/huawei.py` — update `_state_payload_errors()` function to detect Huawei retcode 939589973 and classify it as `TECHNOLOGY_UNAVAILABLE`.

**Tests to add or update**:
- Unit test for `_state_payload_errors()` that verifies:
  - A result with retcode 939589973 is classified with code `TECHNOLOGY_UNAVAILABLE`.
  - A result with "Command does not exist" in the error message is classified as `TECHNOLOGY_UNAVAILABLE`.
  - Existing classification logic (NODE_NOT_FOUND, NODE_DISCONNECTED) remains unchanged for other error patterns.
- Integration test (or manual test):
  - Call `/mml/cell-summary-nr` with a known node lacking 5G.
  - Verify the error in the response has code `TECHNOLOGY_UNAVAILABLE` and the expected message.

## Risks & Considerations

- **Breaking change risk (low):** Changing the error code from `NODE_NOT_FOUND` to `TECHNOLOGY_UNAVAILABLE` for sites without 5G is a **behavioral change**. Clients that hardcode checks for `NODE_NOT_FOUND` may need updates. However, this is the correct behavior and clients should be adapted.
  
- **Other technologies (LTE, UMTS):** The same issue likely affects `create_cell_summary_lte()` and `create_cell_summary_umts()` endpoints. If a node lacks LTE or UMTS, Huawei will return similar retcodes. Ensure the fix is applied consistently across all cell-summary endpoints.

- **Retcode variability:** Huawei may return different retcodes for "command does not exist" in different scenarios or API versions. Monitor and update error detection if new patterns are encountered in production.

- **Error message parsing:** The current approach relies on substring matching in error messages. A more robust approach would be to extract and check the retcode (e.g., parse `RETCODE = \d+` from the raw error), but the current text-based approach is pragmatic for now.

## Open Questions

- [NEEDS CLARIFICATION: Does Huawei always return retcode 939589973 for technology-unavailable, or are there other retcodes that indicate this condition?]
- [NEEDS CLARIFICATION: Should the same error logic apply to LTE (`create_cell_summary_lte`) and UMTS (`create_cell_summary_umts`) endpoints?]
- [NEEDS CLARIFICATION: Are there any existing clients/dashboards that depend on the current `NODE_NOT_FOUND` error code that would break with this change?]
