# Bug Verification: cell-summary LTE/NR con un solo nodo fallido

- **Slug**: cell-summary-single-node-error
- **Tested**: 2026-10-28
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Con un único nodo offline, LTE y NR responden 200 con `records: []`, `count: 0` y `errors`, en lugar de 502 "no tiene columna X". No hubo regresiones.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | `test_cell_summary_single_offline_ne_returns_200_with_errors` (LTE y NR, mock de Huawei) | pass | Reproducción automatizada, no contra Huawei real |
| Tests cell-summary | `pytest tests\test_huawei_route.py -k "single_offline or cell_summary or nr_cell"` | pass | 8 passed |
| Regression suite | `conda run -n backend-soporte python -m pytest -q` | pass | 41 passed |
| Lint | `python -m ruff check app tests` | not-run | ruff no está instalado en el entorno |

## Output Excerpts

- `41 passed, 2 warnings in 4.82s`

## Residual Risks

- Verificado solo con respuestas simuladas; no contra equipos Huawei reales.
- No hay tests para lote totalmente fallido ni LST fallido con DSP exitoso (ruta de código cubierta indirectamente).
- Consumidores que dependieran del 502 verán ahora 200 con `errors`.

## Recommendation

Cerrar el bug. Opcionalmente, confirmar manualmente con un nodo inexistente en el ambiente real.
