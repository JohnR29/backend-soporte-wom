# Bug Fix: 5G Cell Summary Misclassifies Unsupported Technology

- **Slug**: 5g-cell-unsupported-site
- **Fixed**: 2026-11-09
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Huawei retcode `939589973` and the message `Command does not exist` are now classified as `TECHNOLOGY_UNAVAILABLE` before the generic node-not-found check. The error message uses the technology of the LTE or NR route that detected it.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `app/api/routes/huawei.py` | modified | Classifies the retcode/message and supplies technology context for LTE/NR errors. |
| `tests/test_huawei_route.py` | added test | Covers both unavailable-technology indicators and confirms disconnected/not-found classifications remain unchanged. |

## Tests Added or Updated

- `tests/test_huawei_route.py::test_nr_cell_summary_classifies_huawei_command_errors` — pins down the retcode, phrase-only, `NODE_DISCONNECTED`, and `NODE_NOT_FOUND` cases at the NR route.

## Local Verification

- Commands run: `pytest tests/test_huawei_route.py -k test_nr_cell_summary_classifies_huawei_command_errors` → could not start because `pytest` was not on `PATH`.
- Commands run: `python -m pytest tests/test_huawei_route.py -k test_nr_cell_summary_classifies_huawei_command_errors` → could not start because the `python` command was unavailable.
- Commands run: `C:/Users/jcrojasm/AppData/Local/miniconda3/envs/backend-soporte/python.exe -m pytest tests/test_huawei_route.py -k test_nr_cell_summary_classifies_huawei_command_errors` → 4 passed.
- Commands run: `C:/Users/jcrojasm/AppData/Local/miniconda3/envs/backend-soporte/python.exe -m pytest tests/test_huawei_route.py` → 65 passed.
- Manual checks: Pylance reported all call sites compatible with the updated signature and no file diagnostics. No live Huawei request was made.

## Deviations from Assessment

None.

## Follow-ups

- Run `/speckit-bug-test slug=5g-cell-unsupported-site` for the formal bug verification report.
