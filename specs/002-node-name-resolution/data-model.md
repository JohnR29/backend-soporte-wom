# Data Model: Resolución de nombres de nodo a partir del sitio

## Registro de sitio (tabla externa)

La entidad es propiedad de un sistema externo y este servicio solo la consulta desde `public.cellreference`, mediante `SITE_DIRECTORY_DATABASE_URL`. No se crea modelo persistente ni migración Alembic para ella.

| Field | Meaning | Validation / use |
|---|---|---|
| `sitio` | `varchar(50) NULL`; nemónico identificador del sitio | La fuente garantiza unicidad. Se compara después de `strip()` y normalización case-insensitive. Los nulos no son resolubles ni se sugieren. |
| `nodo` | `varchar(50) NULL`; nombre de red utilizado para 4G/5G | Se devuelve para consultas LTE, NR, MML genérico y KPIs. Nulo/vacío produce `missing_mapping`. |
| `nodeb` | `varchar(50) NULL`; nombre UMTS utilizado en `NodeBName` | Se devuelve para el resumen UMTS. Nulo/vacío produce `missing_mapping`. |
| `enodeb`, `gnodeb` | `varchar(50) NULL`; columnas presentes en el directorio | Fuera de uso en esta funcionalidad; no se consultan como destinos. |

La relación es fija (`public.cellreference`) y la conexión se indica mediante `SITE_DIRECTORY_DATABASE_URL`. La aplicación requiere acceso de solo lectura y no altera registros. La unicidad de `sitio` es una garantía de los datos; la DDL no incluye una restricción `UNIQUE`.

## Resultado de resolución (efímero por solicitud)

No se persiste. Cada entrada de `name_resolution` mantiene la relación entre la entrada del cliente y el valor que se envía al sistema upstream.

| Field | Meaning |
|---|---|
| `input` | Valor enviado por el cliente, conservado para trazabilidad |
| `resolved` | Valor del directorio enviado a Huawei; nulo si no se resolvió |
| `status` | `resolved`, `not_found`, `missing_mapping` o `ambiguous_mapping` |
| `suggestions` | Hasta cinco nemónicos no nulos de sitio para `not_found`, ordenados por porcentaje de similitud descendente y, en caso de empate, alfabéticamente de forma ascendente sin distinguir mayúsculas/minúsculas |
| `error` | Descripción breve para `not_found` o `missing_mapping` |

Reglas:

- Para el modo 4G/5G, una coincidencia de `sitio` resuelve a `nodo`; para 3G resuelve a `nodeb`.
- Una entrada que ya sea un nombre de red completo válido en la columna de destino se acepta y se envía sin reconstruir prefijos.
- La salida resuelta usa el valor canónico del directorio. La normalización de búsqueda ignora espacios externos y mayúsculas/minúsculas.
- Las sugerencias contienen valores de `sitio`, nunca valores de `nodo`/`nodeb`.
- Todos los nemónicos no nulos son candidatos, sin umbral mínimo de similitud; si el directorio está vacío, la lista de sugerencias está vacía.
- En lotes, cada elemento se resuelve de manera independiente. Las entradas resueltas siguen a Huawei aunque otras no existan o carezcan de mapeo.
- Si un sitio tiene varios valores distintos para la columna destino, se informa `ambiguous_mapping` y no se envía ningún valor a Huawei.

## Auditoría

Se reutiliza `ApiAuditLog` sin cambio de esquema:

- `request_body` conserva los valores originales recibidos.
- `ne_names` registra los nombres efectivos enviados a Huawei, no solo el nemónico de entrada.
- Las entradas fallidas permanecen visibles en el cuerpo y en la respuesta; no se incluyen en la lista de nombres enviados.

## Estado y transiciones

Cada valor de entrada sigue `received -> normalized -> resolved | not_found | missing_mapping`. Un error de conexión/configuración del directorio produce error de servicio y no se clasifica como `not_found`.