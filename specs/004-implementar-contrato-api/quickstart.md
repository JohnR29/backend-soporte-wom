# Quickstart: Validar el contrato de Operaciones

This guide validates the backend contract using controlled test doubles; it does not require a bot repository, live Huawei account, or live site-directory connection.

## Prerequisites

- Python 3.11 and the backend project's test/runtime dependencies installed.
- Repository root as the working directory.
- No production credentials are needed. Tests override backend authentication and mock external calls.

## Focused Acceptance Run

Run the routes and existing resolver tests:

```powershell
pytest tests/test_huawei_route.py tests/test_alarms_route.py tests/test_node_resolution.py -q
```

Expected outcome: exit code 0; tests cover state routes, alarm normalization/current pagination, KPI window and results, resolver outcomes, and the established directory suggestion fixture. The acceptance additions must cover AT-01 through AT-14 as mapped in [backend-api-acceptance.md](contracts/backend-api-acceptance.md).

## Full Regression Run

```powershell
pytest -q
```

Expected outcome: the complete backend suite passes, including parser, audit, node resolution, and route tests. Any existing environment-specific failure should be reported separately from this feature's acceptance results.

## Manual Contract Review

1. Compare route response shapes with [the canonical feature 003 contract](../../003-telebot-operaciones-api/contracts/telebot-operaciones.md).
2. Verify unknown/missing/ambiguous identifiers never cause guessed Huawei requests, and valid partial results remain present.
3. Verify alarm `cleared` follows `alarmClearedTime` and the request remains `dataType=CURRENT`.
4. Verify KPI calls use a fixed latest-24-hour window, include `startTime`, ignore caller period fields, and leave resolved empty nodes without node errors.
5. Review the changed-file list: implementation and test changes must remain in this backend repository, with no bot-repository paths and no credentials/tokens in fixtures or output.

## Expected Scope

No database migration, dependency installation, image rebuild, or deployment change is required. The implementation is limited to the five in-scope endpoints and their backend acceptance/regression tests.
