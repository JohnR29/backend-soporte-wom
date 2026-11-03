# Contract: Resolución de nombres de nodo

## Solicitudes

Los esquemas actuales no cambian:

| Endpoint | Campo | Modo de resolución |
|---|---|---|
| `POST /mml/command` | `ne_names` | `sitio` o nombre de nodo -> `nodo` |
| `POST /mml/cell-summary-lte` | `ne_names` | `sitio` o nombre de nodo -> `nodo` |
| `POST /mml/cell-summary-nr` | `ne_names` | `sitio` o nombre de nodo -> `nodo` |
| `POST /mml/kpis` | `ne_names` | `sitio` o nombre de nodo -> `nodo` |
| `POST /mml/cell-summary-umts` | `nodeb_name` | `sitio` o NodeB -> `nodeb` |

Se mantienen límites y campos existentes. Los nombres se normalizan para buscar, pero las respuestas conservan la entrada original en `name_resolution[].input`.

## Respuestas

Todas las respuestas de las rutas anteriores agregan el campo `name_resolution`; sus campos existentes no cambian. El nuevo campo es una lista en el mismo orden de la solicitud:

```json
{
  "name_resolution": [
    {"input": "AN0069", "resolved": "MBTS-AN0069", "status": "resolved"},
    {
      "input": "AN0096",
      "resolved": null,
      "status": "not_found",
      "error": "No se encontró el sitio.",
      "suggestions": ["AN0069"]
    }
  ]
}
```

La forma anterior ilustra solo el campo aditivo; en respuestas reales acompaña `results` (comando), `records`/`errors` (resúmenes), o `records` (KPIs) según el endpoint. Los valores upstream ya resueltos siguen apareciendo en los campos actuales (`results[].name`, `ne_name`, `neName` o `nodeb_name`).

Para solicitudes por lote, una entrada no resuelta no cancela las resueltas. No se realiza una llamada Huawei para entradas `not_found`, `missing_mapping` o `ambiguous_mapping`; los fallos quedan descritos en `name_resolution`. Si el lote no contiene entradas resueltas, la respuesta usa la estructura vacía del endpoint, sin invocar Huawei.

## Errores

| Caso | Comportamiento |
|---|---|
| Sitio tiene varios valores destino distintos | Estado `ambiguous_mapping` en lote, sin llamada Huawei; HTTP `422` para UMTS. Corregir la fuente para dejar un único destino por sitio. |
| Sitio desconocido en lote | Estado `not_found`, `resolved: null` y hasta cinco nemónicos existentes con mayor porcentaje de similitud, ordenados de mayor a menor; empates en orden alfabético ascendente sin distinguir mayúsculas/minúsculas. |
| Sitio desconocido en `/mml/cell-summary-umts` | HTTP `404`; `detail` identifica la entrada y las sugerencias, con el mismo orden por similitud y desempate alfabético. |
| Sitio existe pero falta `nodo`/`nodeb` | Estado `missing_mapping` en lote; HTTP `422` para UMTS escalar. El mensaje indica la tecnología y el campo faltante. |
| Directorio sin configurar, inaccesible o inválido | HTTP `503`; no confundir con un sitio desconocido y no intentar Huawei. |
| Variable de conexión o relación no disponible | HTTP `503`; no confundir con un sitio desconocido y no intentar Huawei. |

Todos los nemónicos de sitio no nulos son candidatos, sin umbral mínimo de similitud. Se devuelven menos de cinco si hay menos de cinco candidatos y una lista vacía si no hay ninguno.

## Compatibilidad y alcance

- Las solicitudes que contienen nombres completos válidos siguen siendo aceptadas y se resuelven al nombre canónico del directorio.
- `/alarms/{site_name}`, `/tickets/{sitio}` y `/mml/scripts` no cambian: no son entradas estructuradas de nombre de nodo de esta feature.
- No se agrega endpoint público para consultar el directorio ni se exponen credenciales/detalles de conexión.