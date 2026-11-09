# Quickstart: Validar el contrato de Telebot Operaciones

This guide validates the target contract using the existing route and directory tests. This feature phase is documentation-only, so current runtime behavior may not satisfy the new contract until a later implementation phase.

## Prerequisites

- Python 3.11 and the repository's configured environment/dependencies, including pytest. Activate the `backend-soporte` environment before running the command, or invoke its Python interpreter directly.
- Repository root as the working directory.
- For live smoke tests, a reachable backend, configured site directory and Huawei MAE, plus the existing API authentication mechanism. Do not put credentials or tokens in this guide, source control, or captured output.

## Focused regression tests

Run the existing route and directory-resolution tests from the repository root:

```powershell
python -m pytest -q tests/test_huawei_route.py tests/test_node_resolution.py tests/test_alarms_route.py
```

Expected outcome: all three existing test modules pass. During the future implementation phase, add focused cases for the target scenarios below and run the same command. Passing the existing tests does not demonstrate that the target contract is implemented.

Documentation-phase check (2026-11-08): the command passed using the `backend-soporte` Python interpreter: 51 tests passed, with two dependency deprecation warnings. A terminal without the environment active could not find `pytest`.

## Contract scenarios

Use the authenticated API with the existing authorization header format; do not include the token in logs or saved examples.

1. Submit the same site identifier separately to `POST /mml/cell-summary-umts` (`nodeb_name`), `POST /mml/cell-summary-lte` (`ne_names`), and `POST /mml/cell-summary-nr` (`ne_names`). Verify each `name_resolution` reflects the correct directory column and that valid records are preserved.
2. Submit an unknown identifier to each state endpoint and `POST /mml/kpis`. Verify HTTP 200, empty records, `NODE_NOT_FOUND`, and suggestions when available. For a known node with no KPI measurements, verify `records: []` and `errors: []` instead.
3. Simulate a 4G/5G Huawei response of `Ne is not connected.` and verify `NODE_DISCONNECTED`; do not infer KPI or 3G disconnection from empty results. For 3G, when all returned cells have `Operation state = "Unavailable"`, verify HTTP 200, preserved `records`, and `NODE_DISCONNECTED`; with mixed cell states, verify records are preserved without that code.
4. Simulate a partial 3G result where one RNC returns cells and others fail. Verify the cells remain in `records` and no node-level not-found/disconnected error is emitted. For a mixed 4G/5G batch, preserve records for successful nodes and report the failed node in `errors`.
5. Provide alarm rows with null, non-null, and contradictory clear fields. Verify the output `cleared` value is derived consistently from `alarmClearedTime`; the API makes no claim that `CURRENT` includes cleared alarms.
6. Submit invalid authentication and malformed request bodies, and simulate Huawei and directory failures. Verify the corresponding 400, 401, 422, 502, 503 and 504 responses contain no node error codes.
7. Verify an existing 3G NodeB reported as not configured by every RNC returns `NODE_NOT_FOUND` (AT-04a). Verify configured NodeBs with all cells `Unavailable` and with mixed availability against AT-04b.
8. Verify current response fields, names and types remain compatible except for the agreed 3G not-found HTTP status. Check examples and captured logs for credentials or tokens.
9. For alarms, verify the existing `CURRENT` query, fields, count and marker; do not make a historical query. For a mixed KPI request, preserve measurements from resolved nodes while reporting unresolved identifiers.

## Traceability and handoff

| Requirements | Contract scenarios | Review / runtime status |
|---|---|---|
| FR-001, FR-002, FR-003, FR-004 | AT-01, AT-11 | Contract review; execute with simulated directory in the runtime phase. |
| FR-005, FR-006, FR-007, FR-008, FR-009, FR-010 | AT-02 through AT-05, AT-08, AT-12 | Contract review; test 3G all-unavailable and mixed-cell states, null-code source errors, ambiguous mappings and HTTP failures in the runtime phase. |
| FR-011, FR-012 | AT-06, AT-07 | Test partial results and independent technologies in the runtime phase. |
| FR-013, FR-014, FR-015, FR-016 | AT-09, AT-13 | Test alarm consistency and the existing CURRENT query in the runtime phase. |
| FR-017, FR-018 | AT-10, AT-12 | Test the default window, unresolved identifiers and empty measurements in the runtime phase. |
| FR-019, FR-020 | AT-11, AT-14 | Test compatibility and review examples, responses and logs for secrets. |
| SC-001, SC-002, SC-003, SC-004, SC-006 | AT-02 through AT-09, AT-11 | Runtime acceptance and regression tests remain follow-up work. |
| SC-005 | AT-03, AT-04b | Backend supplies the code; displaying its meaning and testing that display belong to the bot repository. |

The bot currently displays records and only counts errors. Its future integration tests must cover stable-code handling, partial results, HTTP errors, alarm display, and KPI empty results. The API's `name_resolution` remains diagnostic; the bot's choice to use it alongside `errors[].code` is a consumer decision.

## Contract references

See [the endpoint contract](contracts/telebot-operaciones.md) for request/response examples and [the data model](data-model.md) for field and error semantics. The implementation phase should add representative fixtures for the 3G all-unavailable and mixed-cell cases in AT-04b.