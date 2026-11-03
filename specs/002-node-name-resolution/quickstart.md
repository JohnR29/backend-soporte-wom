# Quickstart: Validar resolución de nombres de nodo

## Prerrequisitos

- Entorno Python del proyecto y dependencias de `requirements.txt` instaladas.
- Una relación PostgreSQL de prueba con columnas `sitio`, `nodo`, `nodeb`, `enodeb` y `gnodeb`, accesible con credenciales de solo lectura.
- `SITE_DIRECTORY_DATABASE_URL` configurada para `public.cellreference` con la credencial de solo lectura; `DATABASE_URL` continúa siendo independiente y se reserva para auditoría.
- Variables Huawei habituales para ejecutar escenarios HTTP end-to-end. Las pruebas unitarias/de rutas deben simular la consulta al directorio y Huawei.

## Validación focalizada

Ejecutar pruebas del resolver y rutas MML:

```powershell
conda run -n backend-soporte python -m pytest -q tests/test_node_resolution.py tests/test_huawei_route.py
```

Resultado esperado: las pruebas verifican normalización, resolución `sitio -> nodo` y `sitio -> nodeb`, aceptación de nombres completos, entradas faltantes con sugerencias, mapeos vacíos, errores de base de datos, lotes mixtos y que Huawei recibe únicamente nombres resueltos. Las pruebas existentes de nombres completos deben seguir pasando.

## Escenarios de integración

1. Usar una copia representativa de `public.cellreference` en el entorno de integración, con registros equivalentes a `AN0069 -> MBTS-AN0069 / UAN0069` y `AN4689 -> MicroBTS-AN4689`; conservar el acceso de solo lectura.
2. Iniciar el servicio según el README (`uvicorn app.main:app --reload`) con las variables de configuración del proyecto.
3. Enviar `AN0069` a `/mml/cell-summary-lte` y comprobar que el upstream recibe `MBTS-AN0069` y que `name_resolution` relaciona ambos valores.
4. Enviar `AN0069` a `/mml/cell-summary-umts` y comprobar que el comando incluye `NODEBNAME="UAN0069"`.
5. Enviar un lote con un sitio válido y uno inexistente a un endpoint por lotes; comprobar que el válido se consulta, el otro conserva sugerencias y no se pierde el resultado válido.
6. Enviar un nombre completo existente y comprobar que la consulta sigue funcionando con el valor canónico del directorio.
7. Quitar el acceso al directorio y comprobar `503`, no un error de sitio inexistente ni una llamada a Huawei.
8. Recorrer exhaustivamente la copia de integración: para cada registro con `nodo` informado, resolver `sitio` en modo 4G/5G y comparar con `nodo`; repetir para cada registro con `nodeb` informado en modo 3G.

## Criterios de aceptación

- Coincidencia de sitio sin distinguir mayúsculas/minúsculas y sin espacios externos.
- Hasta cinco sugerencias ordenadas por porcentaje de similitud descendente; los empates se ordenan alfabéticamente por nemónico ascendente, sin distinguir mayúsculas/minúsculas. Todos los nemónicos no nulos son candidatos, sin umbral mínimo.
- Para cada escenario de búsqueda exacta y de búsqueda sin coincidencia con sugerencias, escalar y en lotes de hasta 100 nombres, medir al menos 30 repeticiones de la etapa de resolución (sin Huawei) y exigir p95 menor a 0,5 s. Registrar el número de filas de la copia y el entorno de prueba.
- En la copia de integración, el 100% de los registros con `nodo` o `nodeb` informado resuelve desde `sitio` al valor almacenado correspondiente.
- El conjunto versionado de errores de un carácter incluye el sitio esperado entre las cinco sugerencias en al menos el 90% de los casos.
- La auditoría conserva la solicitud original y registra los nombres efectivos enviados a Huawei.

## Validación de integración (2026-11-03)

- Entorno: Windows, Conda `backend-soporte`, Python 3.11.15; `public.cellreference` contiene 6.747 filas.
- Registros con destino y sitios distintos comprobados exhaustivamente: 6.747 con `nodo` y 6.382 con `nodeb`; cero mapeos ambiguos o diferencias contra el valor canónico.
- p95 en 30 repeticiones por escenario, en segundos. El lote de coincidencias exactas usa 100 sitios mapeados; el lote de fallos repite las entradas del fixture versionado hasta completar 100 nombres:

| Destino | Exacto escalar | Miss escalar | Exacto lote de 100 | Miss lote de 100 |
|---|---:|---:|---:|---:|
| `nodo` | 0.0930 | 0.2026 | 0.0742 | 0.4647 |
| `nodeb` | 0.0691 | 0.1991 | 0.0715 | 0.4785 |

- Recall del fixture versionado contra el directorio real: 10/10 (100%) entre las cinco sugerencias.
- Pruebas focalizadas con `conda run -n backend-soporte python -m pytest -q tests/test_node_resolution.py tests/test_huawei_route.py tests/test_audit.py`: `50 passed`; dos advertencias deprecadas de Starlette/FastAPI.