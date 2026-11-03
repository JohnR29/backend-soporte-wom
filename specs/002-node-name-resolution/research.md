# Research: Resolución de nombres de nodo a partir del sitio

## Contexto del repositorio

- `app/db/models.py` y la única migración definen `api_audit_log`; el directorio de sitios externo es `public.cellreference` y no requiere modelo ORM ni migración local.
- `DATABASE_URL` es opcional y habilita la auditoría en `app/services/audit.py`. El ejemplo de producción asigna a ese usuario permisos de solo inserción para auditoría, insuficientes para leer sitios.
- `app/db/session.py` contiene un sessionmaker global creado por auditoría. El resolver no debe depender de que auditoría esté activa ni de ampliar los permisos de su usuario.
- `requirements.txt` ya incluye SQLAlchemy async y asyncpg. No hace falta una dependencia nueva para acceder a PostgreSQL.
- `app/api/routes/huawei.py` recibe `ne_names` en MML, resúmenes LTE/NR y KPIs, y `nodeb_name` en el resumen UMTS. Los lotes admiten hasta 100 nombres. Los fallos de nodo en resúmenes se representan por elemento.
- `app/api/audit_middleware.py` guarda el cuerpo original y extrae nombres enviados a `ne_names`. El modelo de auditoría ya tiene un campo `ne_names` para los nombres consultados.

## Decisiones

### 1. Directorio PostgreSQL de solo lectura, con conexión independiente

**Decision**: Consultar `public.cellreference` mediante un engine asíncrono propio configurado por `SITE_DIRECTORY_DATABASE_URL`. Usar el usuario de solo lectura limitado a esa tabla. Inicializar y cerrar el engine con el lifecycle de la aplicación, independientemente de auditoría (`DATABASE_URL`). No crear ni migrar la tabla.

**Rationale**: La tabla existe en PostgreSQL y ya es accesible desde el backend. La conexión separada mantiene el permiso de lectura acotado y evita acoplarla a la credencial de auditoría, que conserva su función actual.

**Alternatives considered**:
- Reutilizar `DATABASE_URL` y el sessionmaker global: rechazado porque auditoría es opcional y la credencial de directorio tiene un propósito y permisos independientes.
- Añadir una tabla/migración local para copiar sitios: rechazado porque contradice que la fuente sea externa y mantenida por otro proceso.
- Añadir un nuevo driver o servicio: rechazado porque PostgreSQL/asyncpg ya están disponibles.

### 2. Búsqueda exacta normalizada en lote; sugerencias solo ante misses

**Decision**: Recortar espacios y comparar sin distinción de mayúsculas/minúsculas. Resolver cada lote con una consulta acotada, utilizando exclusivamente nombres de columna permitidos (`nodo` o `nodeb`) y parámetros vinculados para valores. Consultar nombres de sitio para sugerencias únicamente si hay misses. Considerar todos los nemónicos no nulos como candidatos, calcular el porcentaje sobre los valores normalizados con `difflib.SequenceMatcher.ratio() * 100` y devolver hasta cinco resultados ordenados de mayor a menor porcentaje; desempatar alfabéticamente por nemónico ascendente sin distinguir mayúsculas/minúsculas. No aplicar un umbral mínimo de similitud.

**Rationale**: Mantiene bajo el número de viajes a la base, cumple la normalización solicitada y evita dependencia o extensión PostgreSQL adicional. La tabla solo se lee.

**Alternatives considered**:
- Una consulta por cada nodo: rechazada por hacer depender latencia del tamaño del lote.
- Extensión PostgreSQL `pg_trgm`: no elegida porque su disponibilidad/índices no están bajo control de este servicio.
- Sugerencias en cada solicitud: rechazado porque se requieren solo cuando falla una coincidencia.

**Validation note**: Medir el p95 de la etapa de resolución (sin Huawei) y la tasa de acierto con una copia representativa de `public.cellreference`. Exigir <0,5 s en cada escenario exacto y de sugerencias, escalar y por lotes de hasta 100 nombres, con al menos 30 repeticiones por escenario; registrar filas y entorno. Recorrer además todos los registros de la copia con `nodo` o `nodeb` informado y comprobar que el nemónico resuelve al valor almacenado. El conjunto versionado de errores de un carácter debe incluir el sitio esperado entre los cinco primeros en ≥90% de los casos. Probar el orden descendente por porcentaje y el desempate alfabético. Si la cardinalidad real no permite cumplir el objetivo de latencia, revisar la estrategia antes de añadir infraestructura o extensiones.

### 3. Resolver los endpoints MML con cambios aditivos

**Decision**: Aplicar resolución a `/mml/command`, `/mml/cell-summary-lte`, `/mml/cell-summary-nr`, `/mml/kpis` y `/mml/cell-summary-umts`. Mantener los campos de solicitud actuales. Agregar `name_resolution`, con una entrada por nombre enviado y su nombre resuelto o estado/error/sugerencias. Ejecutar Huawei solamente para valores resueltos; no descartar los válidos si otros no resuelven.

**Rationale**: Cubre las rutas que aceptan `ne_names` o `nodeb_name`, y hace observable el mapeo requerido por FR-008 sin renombrar datos de entrada.

**Alternatives considered**:
- Reemplazar `ne_names`/`nodeb_name` por `sitio`: rechazado para mantener compatibilidad con nombres completos y clientes actuales.
- Tratar todo lote como fallido al primer nombre inválido: rechazado por FR-005 y por el comportamiento parcial ya existente en MML.
- Cambiar alarmas y tickets: rechazado; usan identificadores de sitio en APIs distintas, no campos de nombre de nodo.

### 4. Conservar auditoría de entrada y registrar nodos efectivos

**Decision**: Mantener el cuerpo original en `request_body` y poblar `ne_names` de auditoría con los nombres efectivamente enviados a Huawei, comunicando la resolución al middleware mediante estado de la solicitud. No cambiar el esquema de auditoría.

**Rationale**: El cuerpo ya conserva el valor ingresado; el campo existente `ne_names` puede seguir representando los nombres consultados sin migración.

**Alternatives considered**:
- Guardar solo la entrada: insuficiente para saber qué nodo Huawei recibió.
- Agregar columnas o una migración: innecesario dado que el cuerpo existente conserva la entrada y `ne_names` los destinos efectivos.

## Alcance no incluido

- `/alarms/{site_name}` y `/tickets/{sitio}` continúan recibiendo el identificador de sitio para sus APIs actuales.
- `/mml/scripts` no expone nombres estructurados y no se reescriben los scripts cargados.
- No se crea CRUD, sincronización, caché ni lógica de escritura para el directorio.

## Configuración de despliegue requerida

El despliegue ya define `SITE_DIRECTORY_DATABASE_URL` para `public.cellreference`, accesible con el usuario de solo lectura. La tabla tiene `sitio`, `nodo`, `enodeb`, `nodeb` y `gnodeb` como `varchar(50) NULL`; la fuente garantiza que `sitio` es único. Si la variable no está configurada o la conexión/tabla no está disponible, los endpoints responderán con error de servicio explícito; no habrá fallback silencioso a Huawei.