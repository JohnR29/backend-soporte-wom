# Bug Verification: 5G Cell Summary Misclassifies Unsupported Technology

- **Slug**: 5g-cell-unsupported-site
- **Tested**: 2026-11-09
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

The mocked NR endpoint reproduction using Huawei retcode `939589973` now returns `TECHNOLOGY_UNAVAILABLE`, and the Huawei route regression suite passes. The live request to RM3644 was not made, so behavior against the actual Huawei node remains unverified.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | Focused NR endpoint test with the reported raw Huawei error mocked | pass | Exact retcode/message and `/mml/cell-summary-nr` response classification exercised; live RM3644 request skipped because it requires a network/Huawei environment. |
| New / updated tests | `C:/Users/jcrojasm/AppData/Local/miniconda3/envs/backend-soporte/python.exe -m pytest tests/test_huawei_route.py -k test_nr_cell_summary_classifies_huawei_command_errors` | pass | 4 passed, 61 deselected, 1 warning; exit status 0. |
| Regression suite | `C:/Users/jcrojasm/AppData/Local/miniconda3/envs/backend-soporte/python.exe -m pytest tests/test_huawei_route.py` | pass | 65 passed, 2 warnings; exit status 0. |
| Lint / type-check | Not run | skipped | No `pyproject.toml`, `ruff.toml`, `mypy.ini`, or `setup.cfg` configuration was found; `fix.md` records a prior Pylance check. |

## Output Excerpts

```text
Focused: 4 passed, 61 deselected, 1 warning
Regression: 65 passed, 2 warnings
Both commands exited with status 0.
```

## Residual Risks

- The actual Huawei response from RM3644 was not rechecked; the automated route test uses a mocked Huawei payload.
- Huawei may use other retcodes or message variants for unsupported technologies.

## Recommendation

Hold for confirmation against a known NR-unsupported node in a Huawei-connected environment. The mocked route behavior and local regression suite are passing, but the live reproduction remains unverified.