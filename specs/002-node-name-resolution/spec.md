# Feature Specification: Resolución de nombres de nodo a partir del sitio

**Feature Branch**: `002-node-name-resolution`

**Created**: 2026-10-29

**Updated**: 2026-11-02

**Status**: Draft

**Input**: User description: "Los endpoints que piden el nombre de un nodo deben aceptar el nemónico del sitio sin prefijo (ej. RM3644). La tabla PostgreSQL `public.cellreference`, accesible mediante `SITE_DIRECTORY_DATABASE_URL`, contiene las columnas sitio, nodo, enodeb, nodeb y gnodeb. El usuario consulta el sitio y, por detrás, se cruza con la tabla para obtener el `nodo` en los endpoints 4G y 5G y el `nodeb` en el endpoint 3G. Si no existe, sugerir sitios similares."

## Clarifications

### Session 2026-11-02

- Q: ¿SC-001 debe medir el éxito solo entre los sitios que tienen informado el campo requerido para la tecnología consultada? → A: Sí; SC-001 aplica solo a sitios con el mapeo requerido para la tecnología.
- Q: ¿Cómo definimos los casos de prueba para comprobar que un error de un carácter incluya el sitio correcto entre las sugerencias en al menos el 90% de los casos? → A: Usar casos representativos versionados y exigir que el sitio esperado aparezca entre las cinco sugerencias en al menos el 90%.
- Q: Si la entrada ya identifica un nombre completo pero difiere del directorio en espacios o mayúsculas, ¿qué valor se envía a Huawei? → A: El valor canónico almacenado en el directorio; la entrada original se conserva en `name_resolution[].input`.
- Q: ¿Cómo se valida el límite de latencia adicional de la resolución? → A: Medir el p95 de la etapa de resolución, sin incluir Huawei, en al menos 30 repeticiones por escenario; exigir menos de 0,5 s para búsquedas exactas y fallidas con sugerencias, tanto escalares como en lotes de hasta 100 nombres, sobre una copia representativa del directorio y registrando su tamaño y el entorno.
- Q: ¿Cómo se verifica que el 100% de los sitios con mapeo requerido se resuelven? → A: Recorrer exhaustivamente la copia del directorio de integración y comprobar cada registro con `nodo` informado en modo 4G/5G y cada registro con `nodeb` informado en modo 3G contra el valor almacenado correspondiente.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar 4G/5G escribiendo solo el sitio (Priority: P1)

Un usuario de soporte ingresa el nemónico del sitio (ej. "AN0069") en cualquier consulta 4G/5G que pida nombre de nodo (comandos, resumen de celdas, contadores de performance). El sistema busca el sitio en la tabla de sitios, obtiene su `nodo` (ej. "MBTS-AN0069" o "MicroBTS-AN4689") y ejecuta la consulta con ese nombre.

**Why this priority**: Es el flujo diario; hoy el usuario debe recordar el prefijo correcto de cada nodo.

**Independent Test**: Consultar "AN4689" y verificar que se ejecuta contra "MicroBTS-AN4689"; consultar "AN0069" y verificar "MBTS-AN0069".

**Acceptance Scenarios**:

1. **Given** el sitio "AN0069" existe en la tabla con nodo "MBTS-AN0069", **When** el usuario consulta "AN0069", **Then** la consulta se ejecuta con "MBTS-AN0069".
2. **Given** el sitio "AN4689" tiene nodo "MicroBTS-AN4689", **When** el usuario consulta "AN4689", **Then** se usa "MicroBTS-AN4689".
3. **Given** el usuario ingresa un nodo completo que identifica un valor de la columna `nodo`, **When** consulta, **Then** se envía el valor canónico almacenado en el directorio, sin reconstruir el prefijo.
4. **Given** una consulta con varios sitios, **When** se ejecuta, **Then** cada uno se resuelve de forma independiente.

---

### User Story 2 - Consultar estado 3G escribiendo solo el sitio (Priority: P1)

Un usuario consulta el estado 3G de un sitio con su nemónico. El sistema obtiene el valor de `nodeb` del sitio (ej. "UAN0069") y lo usa como NodeBName.

**Why this priority**: Requerimiento explícito; el nombre 3G difiere del nombre 4G/5G y el usuario no debe conocer ninguno de los dos.

**Independent Test**: Consultar el estado 3G de "AN0069" y verificar que se usa "UAN0069".

**Acceptance Scenarios**:

1. **Given** el sitio existe con `nodeb` "UAN0069", **When** el usuario consulta el estado 3G con "AN0069", **Then** se obtiene el resumen del NodeB "UAN0069".
2. **Given** el usuario ingresa directamente un NodeBName que identifica un valor de la columna `nodeb`, **When** consulta, **Then** se envía el valor canónico almacenado en el directorio.
3. **Given** el sitio existe pero no tiene `nodeb` registrado, **When** consulta 3G, **Then** recibe un error claro indicando que el sitio no tiene nodo 3G.

---

### User Story 3 - Sugerencias cuando el sitio no existe (Priority: P2)

Si el valor ingresado no corresponde a ningún sitio ni nodo conocido, el usuario recibe un error claro con sitios de nombre similar.

**Why this priority**: Evita reintentos a ciegas ante errores de tipeo.

**Independent Test**: Consultar "AN0096" (inexistente) y verificar que se informa que no existe y se sugiere "AN0069".

**Acceptance Scenarios**:

1. **Given** el valor no existe y el directorio contiene sitios, **When** el usuario consulta, **Then** recibe error de no encontrado con hasta 5 sitios de mayor porcentaje de similitud, ordenados de mayor a menor.
2. **Given** dos sitios tienen el mismo porcentaje de similitud, **When** se generan las sugerencias, **Then** aparecen en orden alfabético ascendente por nemónico, sin distinguir mayúsculas/minúsculas.
3. **Given** el directorio no contiene sitios, **When** el usuario consulta un valor inexistente, **Then** recibe el error sin sugerencias.

---

### Edge Cases

- Entrada en minúsculas o con espacios al inicio/fin: se normaliza antes de buscar.
- Sitio presente en la tabla pero sin `nodo` (para 4G/5G) o sin `nodeb` (para 3G): error específico, no "no encontrado".
- Sitio con varios valores distintos en la columna destino: se informa como mapeo ambiguo y no se intenta una llamada a Huawei.
- Sitios con nombres como "ARA_in_3G_002": se buscan por coincidencia exacta del sitio, sin reglas especiales.
- Consulta con varios sitios donde solo algunos no se resuelven: se informa cuáles fallaron, con sugerencias, sin perder los resueltos.
- Tabla de sitios no disponible: error claro de servicio no disponible, sin ocultar la causa.
- Valor ingresado que identifica un `nodo` (4G/5G) o `nodeb` (3G): se busca tras normalizar espacios externos y mayúsculas/minúsculas; se envía el valor canónico del directorio y se conserva la entrada original en los metadatos de resolución.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aceptar el nemónico del sitio además del nombre completo en estos endpoints MML: `/mml/command`, `/mml/cell-summary-lte`, `/mml/cell-summary-nr`, `/mml/kpis` y `/mml/cell-summary-umts`.
- **FR-002**: Para endpoints 4G y 5G, el sistema MUST resolver el sitio al valor de la columna `nodo` de la tabla de sitios.
- **FR-003**: Para el endpoint de estado 3G, el sistema MUST resolver el sitio al valor de la columna `nodeb`.
- **FR-004**: El sistema MUST aceptar también un valor que identifique un `nodo` (4G/5G) o un `nodeb` (3G) válido y enviar el valor canónico correspondiente del directorio, sin reconstruir prefijos.
- **FR-005**: El sistema MUST resolver cada sitio de una solicitud con múltiples sitios de manera independiente.
- **FR-006**: Cuando un valor no corresponde a un sitio ni a un nombre completo válido, el sistema MUST informar que no se encontró y ofrecer hasta 5 nemónicos existentes con mayor porcentaje de similitud, ordenados de mayor a menor y, en caso de empate, alfabéticamente de forma ascendente sin distinguir mayúsculas/minúsculas. Esto aplica a los cinco endpoints MML de FR-001. En solicitudes por lote, MUST informar cada entrada no encontrada individualmente y conservar los resultados resueltos; en la consulta UMTS individual, MUST responder HTTP 404. Si hay menos de cinco sitios, MUST incluir los disponibles; si no hay sitios, MUST devolver la lista vacía. La ausencia del mapeo requerido y la indisponibilidad del directorio se informan según FR-007 y el contrato, sin tratarlas como nombre no encontrado.
- **FR-007**: Cuando el sitio existe pero carece del valor requerido (`nodo` o `nodeb`), el sistema MUST responder con un error distinto y descriptivo.
- **FR-008**: Las respuestas MUST indicar el nombre con el que se resolvió cada sitio.
- **FR-009**: El sistema MUST normalizar la entrada (espacios, mayúsculas/minúsculas) antes de resolver.
- **FR-010**: La auditoría MUST seguir registrando los nodos consultados, idealmente el valor ingresado y el resuelto.
- **FR-011**: Los endpoints existentes MUST seguir funcionando con nombres completos.

### Key Entities

- **Sitio**: identificador corto (nemónico) de una ubicación (ej. "AN0069").
- **Registro de sitio**: fila de la tabla de sitios con `sitio`, `nodo`, `enodeb`, `nodeb` y `gnodeb`; `enodeb` y `gnodeb` pueden estar vacíos.
- **Nodo 4G/5G**: valor de `nodo` (ej. "MBTS-AN0069", "MicroBTS-AN4689").
- **Nodo 3G (NodeB)**: valor de `nodeb` (ej. "UAN0069").
- **Sugerencia**: sitio de la tabla parecido al valor ingresado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En la copia representativa del directorio de integración, el 100% de los registros con `nodo` o `nodeb` informado se resuelven desde su nemónico al valor almacenado correspondiente; la validación recorre todos esos registros, no una muestra.
- **SC-002**: Los usuarios no necesitan conocer prefijos de ningún tipo para consultar un nodo.
- **SC-003**: En un conjunto representativo y versionado de errores de tipeo de un carácter, el sitio correcto aparece entre las cinco sugerencias en al menos el 90% de los casos.
- **SC-004**: El p95 de la duración añadida por la etapa de resolución (desde que comienza la resolución hasta que termina, sin incluir Huawei) es menor a 0,5 segundos en cada escenario medido: búsqueda exacta y búsqueda sin coincidencia con sugerencias, tanto para una entrada como para un lote de hasta 100 nombres. Cada escenario se mide en al menos 30 repeticiones sobre una copia representativa del directorio; se registran el número de filas y el entorno de prueba.
- **SC-005**: Las consultas existentes con nombre completo siguen funcionando sin cambios.

## Assumptions

- La tabla PostgreSQL `public.cellreference` ya existe y es mantenida externamente; esta funcionalidad solo la lee mediante `SITE_DIRECTORY_DATABASE_URL`, con un usuario de solo lectura limitado a esa tabla.
- Todos los campos de `public.cellreference` son `varchar(50)` y admiten `NULL`. La fuente debería mantener un destino único por sitio, aunque la DDL no declare una restricción `UNIQUE`; si los datos contradicen esa expectativa, se falla cerrado con `ambiguous_mapping`.
- Las columnas `enodeb` y `gnodeb` no se usan en esta funcionalidad; los endpoints 4G y 5G usan `nodo`.
- La tabla de sitios es la fuente de verdad; no se prueban prefijos por intentos contra Huawei. Un sitio ausente de la tabla produce "no encontrado" con sugerencias.
- Las sugerencias se limitan a 5 y solo se calculan cuando el valor no se encuentra.
- Todos los nemónicos no nulos del directorio son candidatos a sugerencia; no se aplica un umbral mínimo de similitud.
- Fuera de alcance: crear, editar o eliminar sitios desde la API, y la carga/actualización de la tabla.
