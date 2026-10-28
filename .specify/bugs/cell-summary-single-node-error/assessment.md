# Bug Assessment: cell-summary devuelve "no tiene columna X" cuando el único nodo consultado falla

- **Slug**: cell-summary-single-node-error
- **Created**: 2026-10-28
- **Source**: pasted text
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> en los endpoints /mml/cell-summary-lte, /mml/cell-summary-nr, /mml/cell-summary-umts, si consultamos un solo sitio a la vez, y este no existe o esta desconectado, no se captura correctamente el error, solamente dice que no existe X columna. Si consultamos multiples nodos a la vez, se captura correctamente el error si el nodo esta desconectado o no existe

## Symptom

Con un solo nodo inexistente/desconectado, el endpoint responde HTTP 502 con `Huawei DSP CELL response has no 'Local Cell ID' column` en vez de `200` con `records: []` y el detalle en `errors`. Con varios nodos, mientras al menos uno responda bien, `errors` se llena correctamente.

## Reproduction

1. `POST /huawei/mml/cell-summary-lte` (o `-nr`) con `ne_names` de un solo nodo inexistente/offline.
2. Se obtiene 502 "has no 'Local Cell ID' column".
3. Repetir con 2+ nodos (uno bueno, uno malo): 200 con el error del malo en `errors`.
4. UMTS: el reportante aclaró que el bug NO ocurre en UMTS (solo LTE y NR). UMTS queda fuera de alcance.

## Suspected Code Paths

- `app/api/routes/huawei.py:_records_dataframe` — salta los resultados con `report.error`; si ninguno aporta registros el DataFrame queda sin columnas y lanza 502 por `key_column` ausente.
- `app/api/routes/huawei.py:create_cell_summary` (LTE) y `create_cell_summary_nr` (NR) — llaman `_records_dataframe` en cada paso sin comprobar antes si hay NE exitosos; no existe el early-return que sí tiene UMTS.
- `app/api/routes/huawei.py:create_cell_summary_umts` — fuera de alcance: ya tiene early-return y el reportante confirmó que funciona.
- `_ne_errors` / `_umts_ne_errors` — ya recolectan bien los errores; solo no se alcanzan.

## Root Cause Hypothesis

`_records_dataframe` valida la existencia de la columna clave sobre el DataFrame combinado. Con varios nodos, los exitosos aportan columnas y el fallo queda en `errors`. Con un solo nodo fallido (o todos fallidos) no hay registros, el DataFrame está vacío y la validación se interpreta como respuesta Huawei malformada (502) antes de llegar a `_ne_errors`. Bug latente también con 2+ nodos si todos fallan, o si el nodo responde OK sin celdas. Confianza: alta (LTE y NR; UMTS no afectado).

## Proposed Remediation

**Preferred**: Que `_records_dataframe` solo lance 502 si hay registros pero falta la columna clave; sin registros debe devolver un DataFrame vacío con las columnas esperadas. En LTE/NR, tras el primer comando, si no hay NE exitosos (`_successful_ne_names` vacío), retornar de inmediato `{commands, records: [], count: 0, errors: _ne_errors(...)}` (como ya hace UMTS), evitando ejecutar los comandos siguientes. Comportamiento decidido: fallo total → HTTP 200 con `records: []`, `count: 0` y `errors`. UMTS no se modifica.

**Alternatives**:
- Helper `_empty_summary_response` usado en cada endpoint: menos invasivo, duplica lógica.

**Files likely to change**:
- `app/api/routes/huawei.py`
- tests de rutas Huawei (ubicación por confirmar en `tests/`)

**Tests to add or update**:
- LTE/NR: un solo nodo con `report.error` → 200, `records == []`, `errors` con el nodo.
- LTE/NR: todos los nodos fallan → igual.
- LTE/NR: nodo OK sin registros → 200 vacío (sin 502).
- Regresión: batch mixto sigue devolviendo registros + errores; reporte con registros pero sin columna clave sigue dando 502.

## Risks & Considerations

- Cambia el contrato: casos antes 502 pasan a 200 con `errors`; revisar consumidores (frontend) que dependan del 502.
- Mantener 502 para respuestas realmente malformadas.
- Cortocircuitar tras el primer comando reduce llamadas a Huawei (rate limits).

## Open Questions

- Resuelto: fallo total debe devolver 200 con `errors`. UMTS fuera de alcance.
