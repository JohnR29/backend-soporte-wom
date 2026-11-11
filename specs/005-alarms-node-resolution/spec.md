# Feature Specification: Resolución de nombres de nodo en alarms/{site-name}

**Feature Branch**: `005-alarms-node-resolution`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "debemos implementar la resolución de nombre y sugerencia de nodos no encontrados en el endpoint "/alarms/{site-name}" para que acepte un nombre sin prefijo, y que internamente el backend resuelva el nombre completo, y si es un nodo que no existe, sugerir nombres similares, al igual que en la spec 002"

## Clarifications

### Session 2026-11-09
- Q: ¿Cómo debe decidir `/alarms/{site-name}` qué mapeo de nodo usar cuando el sitio tiene valores tanto para 3G como para 4G/5G? → A: Usar el parámetro opcional `technology`, con 4G por defecto; se espera que todos los sitios tengan mapeo 4G.
- Q: ¿La funcionalidad debe resolver un solo sitio por solicitud o también admitir consultas por lotes? → A: Un sitio por solicitud; quitar de la spec los requisitos de lotes.
- Q: ¿Qué debe responder `/alarms/{site-name}` si no puede consultar la base del directorio de sitios? → A: HTTP 503 y no llamar a Huawei, como establece el contrato de resolución de nombres de la spec 002.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar alarmas del sitio por nemónico (Priority: P1)



Un usuario de soporte consulta alarmas de un sitio ingresando solo el nemónico (ej. "AN0069") en el endpoint `/alarms/AN0069`. El sistema busca el sitio en la tabla `public.cellreference`, obtiene el nombre completo del nodo (ej. "MBTS-AN0069" para 4G/5G o "UAN0069" para 3G) y ejecuta la consulta de alarmas con el nombre canónico.

**Why this priority**: Es el flujo diario; actualmente el usuario debe recordar el prefijo correto de cada nodo para consultar alarmas.

**Independent Test**: Consultar `/alarms/AN0069` y verificar que, por defecto, se resuelve usando `nodo`; consultar `/alarms/AN0069?technology=3G` y verificar que se usa `nodeb`.

**Acceptance Scenarios**:

1. **Given** el sitio "AN0069" existe en la tabla con nodo "MBTS-AN0069", **When** el usuario consulta `/alarms/AN0069`, **Then** el sistema resuelve y obtiene alarmas del nodo "MBTS-AN0069".
2. **Given** el sitio "AN4689" tiene nodo "MicroBTS-AN4689", **When** el usuario consulta `/alarms/AN4689`, **Then** se usa "MicroBTS-AN4689".
3. **Given** el usuario ingresa un nombre de nodo completo (ej. "MBTS-AN0069"), **When** consulta, **Then** se verifica contra el directorio y se envía el valor canónico almacenado.

---

### User Story 2 - Sugerencias cuando el sitio/nodo no existe (Priority: P2)


Si el valor ingresado no corresponde a ningún sitio ni nodo conocido, el usuario recibe un error claro con sugerencias de sitios de nombre similar.

**Independent Test**: Consultar `/alarms/AN0096` (inexistente) y verificar que se informa "no encontrado" con sitios similares sugeridos (ej. "AN0069", "AN0086").

**Acceptance Scenarios**:

1. **Given** el valor no existe y el directorio contiene sitios, **When** el usuario consulta, **Then** recibe error HTTP 404 con lista de hasta 5 sitios de mayor similitud, ordenados de mayor a menor porcentaje.
2. **Given** dos sitios tienen el mismo porcentaje de similitud, **When** se generan las sugerencias, **Then** aparecen en orden alfabético ascendente por nemónico.
3. **Given** el directorio no contiene sitios, **When** el usuario consulta un valor inexistente, **Then** recibe el error sin sugerencias.
4. **Given** el sitio existe pero no tiene la columna requerida (ej. sin `nodo` en 4G/5G), **When** consulta, **Then** recibe error específico indicando la ausencia del mapeo, no "no encontrado".

---

### Edge Cases

- Entrada en minúsculas o con espacios al inicio/fin: se normaliza antes de buscar.
- Sitio sin `nodo` (para 4G/5G) o sin `nodeb` (para 3G): error específico diferenciado.
- Sitio con varios valores distintos en la columna destino: se informa como mapeo ambiguo.
- Entrada que ya identifica un nombre completo pero difiere en espacios o mayúsculas: se envía el valor canónico almacenado.
- Directorio de sitios no disponible: se responde HTTP 503 y no se intenta una llamada a Huawei.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El endpoint `/alarms/{site-name}` DEBE aceptar un nemónico de sitio (ej. "AN0069") sin prefijo.
- **FR-002**: El sistema DEBE consultar la tabla `public.cellreference` accesible mediante `SITE_DIRECTORY_DATABASE_URL` para resolver el nemónico al nombre de nodo completo.
- **FR-003**: El endpoint DEBE aceptar un parámetro opcional `technology` con valores `3G`, `4G` o `5G`; si se omite, DEBE usar `4G`. Para 4G/5G, el sistema DEBE usar la columna `nodo` de la tabla de resolución.
- **FR-004**: Para consultas `technology=3G`, el sistema DEBE usar la columna `nodeb` de la tabla de resolución.
- **FR-005**: Si el entrada identifica un nombre de nodo conocido, el sistema DEBE verificar que sea canónico antes de usarlo.
- **FR-006**: Si el valor no se resuelve, el sistema DEBE devolver un error HTTP 404 con un listado de hasta 5 sitios de mayor similitud (basado en distancia de Levenshtein u otro algoritmo comparable).
- **FR-007**: Las sugerencias DEBEN ordenarse por similitud decreciente; en caso de empate, alfabéticamente por nemónico (sin distinguir mayúsculas).
- **FR-008**: El error DEBE indicar explícitamente si el sitio existe pero carece del mapeo requerido para la tecnología (3G/4G/5G).
- **FR-009**: La entrada DEBE normalizarse (trim, conversión a mayúsculas según reglas del directorio) antes de buscar.
- **FR-010**: El sistema DEBE registrar en los metadatos de la respuesta qué entrada fue proporcionada y cuál fue su resolución.
- **FR-011**: Si el directorio de sitios no está disponible, el sistema DEBE responder HTTP 503 y no DEBE invocar la API de Huawei.

### Key Entities *(include if feature involves data)*

- **Site (Sitio)**: Representación de un sitio de red, identificado por un nemónico (ej. "AN0069"). Contiene mapeos a nodos 4G/5G (`nodo`) y 3G (`nodeb`).
- **Node (Nodo)**: Nombre completo de un nodo de red (ej. "MBTS-AN0069", "MicroBTS-AN4689", "UAN0069"). Identificador que utiliza la API de Huawei.
- **Name Resolution Record**: Registro que contiene la entrada del usuario, el sitio identificado, el nodo canónico resuelto y (si aplica) sugerencias en caso de error.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% de los sitios con mapeo requerido (según tecnología) se resuelven correctamente a su nodo canónico en consultas contra el directorio.
- **SC-002**: El sitio esperado aparece entre las 5 sugerencias en al menos el 90% de los casos de error tipográfico de un carácter.
- **SC-003**: La latencia adicional de la etapa de resolución es inferior a 0.5 segundos (p95) para búsquedas exactas y fallidas con sugerencias en consultas de un solo sitio.
- **SC-004**: Las sugerencias se presentan ordenadas correctamente (similitud decreciente, luego alfabético) en el 100% de los casos.
- **SC-005**: Los mensajes de error distinguen entre "sitio no encontrado", "sitio existe pero sin mapeo para la tecnología" y "entrada normalizada no coincide" en el 100% de los casos.

## Assumptions

- El directorio de sitios se mantiene en una tabla PostgreSQL accesible mediante la variable de entorno `SITE_DIRECTORY_DATABASE_URL` (mismo mecanismo que en spec 002).
- La columna de similitud utiliza un algoritmo estándar (Levenshtein, Jaro-Winkler u otro comparablemente confiable) que ya está disponible o es introducido como dependencia mínima.
- Las tecnologías soportadas en el contexto del endpoint `/alarms` son 3G, 4G y 5G; el parámetro opcional `technology` selecciona la tecnología y, si se omite, se usa 4G.
- La entrada del usuario se normaliza con reglas consistentes con spec 002 (trim, conversión de caso según el directorio).
- El error HTTP 404 es la respuesta estándar para sitios/nodos no encontrados; otros códigos (400, 500) se reservan para errores de validación e internos.
- El cambio es independiente de la resolución de nombres en otros endpoints; cada endpoint aplica su propia lógica según sea necesario.
- La tabla `public.cellreference` contiene las columnas: `sitio`, `nodo`, `enodeb`, `nodeb`, `gnodeb`; no se requieren cambios en el esquema.
- Se espera que todos los sitios tengan mapeo 4G (`nodo`); si falta, se aplica el error específico de FR-008.
