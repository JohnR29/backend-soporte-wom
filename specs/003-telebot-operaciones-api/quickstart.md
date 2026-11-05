# Quickstart: Validar el contrato de Telebot Operaciones

This guide validates the target contract using the existing route and directory tests. This feature phase is documentation-only, so current runtime behavior may not satisfy the new contract until a later implementation phase.

## Prerequisites

- Python 3.11 and the repository's configured environment/dependencies.
- Repository root as the working directory.
- For live smoke tests, a reachable backend, configured site directory and Huawei MAE, plus the existing API authentication mechanism. Do not put credentials or tokens in this guide, source control, or captured output.

## Focused regression tests

Run the existing route and directory-resolution tests from the repository root:

```powershell
pytest -q tests/test_huawei_route.py tests/test_node_resolution.py
```

Expected outcome: both test modules pass. During the future implementation phase, add focused cases for the target scenarios below and run the same command.

## Contract scenarios

Use the authenticated API with the existing authorization header format; do not include the token in logs or saved examples.

1. Submit the same site identifier separately to `POST /mml/cell-summary-umts` (`nodeb_name`), `POST /mml/cell-summary-lte` (`ne_names`), and `POST /mml/cell-summary-nr` (`ne_names`). Verify each `name_resolution` reflects the correct directory column and that valid records are preserved.
2. Submit an unknown identifier to each state endpoint and `POST /mml/kpis`. Verify HTTP 200, empty records, `NODE_NOT_FOUND`, and suggestions when available. For a known node with no KPI measurements, verify `records: []` and `errors: []` instead.
3. Simulate a 4G/5G Huawei response of `Ne is not connected.` and verify `NODE_DISCONNECTED`; do not infer KPI or 3G disconnection from empty results.
4. Simulate a partial 3G result where one RNC returns cells and others fail. Verify the cells remain in `records` and no node-level not-found/disconnected error is emitted.
5. Provide alarm rows with null, non-null, and contradictory clear fields. Verify the output `cleared` value is derived consistently from `alarmClearedTime`; the API makes no claim that `CURRENT` includes cleared alarms.
6. Submit invalid authentication and malformed request bodies. Verify 401 and 422 respectively, without node error codes.

## Contract references

See [the endpoint contract](contracts/telebot-operaciones.md) for request/response examples and [the data model](data-model.md) for field and error semantics. AT-01 through AT-11 in the contract map to the scenarios above; AT-04b requires a real or representative Huawei fixture before implementing 3G disconnected mapping.