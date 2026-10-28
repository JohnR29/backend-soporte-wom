# Bug Fix: cell-summary LTE/NR con un solo nodo fallido

- **Slug**: cell-summary-single-node-error
- **Fixed**: 2026-10-28
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`/mml/cell-summary-lte` y `/mml/cell-summary-nr` ya no devuelven 502 "no tiene columna X" cuando ningún nodo aporta registros; responden 200 con `records: []`, `count: 0` y `errors` por nodo.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `app/api/routes/huawei.py` | modified | `_records_dataframe` acepta `empty_columns` y devuelve un DataFrame vacío si no hay registros (sin ese parámetro mantiene el 502, usado por UMTS). LTE y NR pasan las columnas esperadas en cada comando. |
| `app/api/routes/huawei.py` | modified | LTE/NR hacen early-return tras el primer comando (DSP) si está vacío, sin ejecutar los siguientes. |
| `tests/test_huawei_route.py` | added test | Parametrizado LTE/NR con un único nodo offline. |

## Tests Added or Updated

- `tests/test_huawei_route.py::test_cell_summary_single_offline_ne_returns_200_with_errors` — 200, `records == []`, `errors` con el nodo, solo se ejecuta el primer comando.

## Local Verification

- `conda run -n backend-soporte python -m pytest tests\test_huawei_route.py -q` → 26 passed.

## Deviations from Assessment

- Se añadió manejo de DataFrame vacío también para los comandos LST (si el DSP tiene registros pero un LST falla en todos los nodos, no hay 502/KeyError; los campos quedan `null`). UMTS no se modificó.
- No se añadieron tests para "todos los nodos fallan" en lote ni "nodo OK sin registros" (cubiertos por la misma ruta de código).

## Follow-ups

- Considerar tests de los casos de lote totalmente fallido y de LST fallido con DSP exitoso.
