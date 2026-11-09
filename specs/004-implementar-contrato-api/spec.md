# Feature Specification: Implementar el contrato de API Operaciones

**Feature Branch**: `004-implementar-contrato-api`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "debemos implementar el contrato de la feature 003 en el backend, añadir pruebas de aceptación y que no incluye cambios en el repositorio del bot."

## Clarifications

### Session 2026-11-09

- Q: Si una solicitud de KPIs incluye `period_start` o `period_end`, ¿qué debe hacer la API? → A: Ignorar esos campos y devolver siempre la ventana fija de 24 horas.
- Q: Si un nodo KPI existe en el directorio pero no devuelve mediciones porque está desconectado, ¿qué debe informar la API? → A: No clasificar conectividad; no emitir error por nodo sin mediciones y mantener los fallos de consulta Huawei como errores HTTP.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar estado por tecnología con errores consistentes (Priority: P1)

El consumidor de la API consulta el estado de un sitio en 3G, 4G o 5G usando el identificador original. El backend resuelve el nombre según el directorio, conserva resultados útiles y comunica condiciones por nodo mediante códigos estables.

**Why this priority**: Es el flujo principal del contrato y permite distinguir los resultados operacionales de los errores de transporte o solicitud.

**Independent Test**: Ejecutar los escenarios AT-01 a AT-08 del contrato de la feature 003 con respuestas controladas del directorio y de Huawei; verificar estado HTTP, registros, errores y resolución de nombres.

**Acceptance Scenarios**:

1. **Given** el mismo identificador tiene valores distintos en las columnas de 3G y 4G/5G, **When** se consulta cada tecnología, **Then** cada respuesta refleja la resolución de su tecnología en `name_resolution` (AT-01).
2. **Given** un identificador no existe en el directorio, **When** se consulta 3G, 4G, 5G o KPIs, **Then** la API responde HTTP 200 con `NODE_NOT_FOUND`, registros vacíos y sugerencias cuando existan (AT-02).
3. **Given** Huawei informa que un NE 4G/5G no está conectado, **When** se consulta el nodo, **Then** la API responde HTTP 200 con `NODE_DISCONNECTED` y sin registros (AT-03).
4. **Given** un sitio tiene NodeB en el directorio pero todas las RNC informan que no está configurado, **When** se consulta 3G, **Then** la API responde HTTP 200 con `NODE_NOT_FOUND` y registros vacíos (AT-04a).
5. **Given** un NodeB 3G devuelve celdas, **When** todas tienen `Operation state = "Unavailable"`, **Then** la API conserva las celdas y agrega `NODE_DISCONNECTED`; si la disponibilidad es mixta, conserva las celdas sin ese código (AT-04b).
6. **Given** un nodo existe pero carece de mapeo para la tecnología, o está conectado y no devuelve celdas de ella, **When** se consulta esa tecnología, **Then** la API responde HTTP 200 con `TECHNOLOGY_UNAVAILABLE` (AT-05).
7. **Given** una RNC devuelve celdas y otras fallan, o una solicitud 4G/5G contiene nodos con resultados mixtos, **When** se completa la consulta, **Then** se preservan todos los registros válidos y los fallos se informan sin atribuirlos erróneamente a un nodo con datos (AT-06, AT-07).
8. **Given** ocurre un error HTTP por solicitud inválida, autenticación, Huawei o directorio, **When** la API responde con 400, 401, 422, 502, 503 o 504, **Then** no devuelve códigos de error por nodo en `errors[].code` (AT-08).

### User Story 2 - Consultar alarmas y KPIs con semántica definida (Priority: P2)

El consumidor recibe alarmas cuyos campos de clareo son coherentes y mediciones KPI del periodo predeterminado, sin que resultados vacíos se interpreten como desconexión.

**Why this priority**: Completa el contrato operacional sin añadir consultas históricas ni inferencias que el origen no garantiza.

**Independent Test**: Ejecutar AT-09, AT-10, AT-12 y AT-13 con respuestas de alarma y medición controladas.

**Acceptance Scenarios**:

1. **Given** alarmas con fecha de clareo nula, presente o contradictoria en el origen, **When** se consultan, **Then** `cleared` se deriva consistentemente de `alarmClearedTime` (AT-09).
2. **Given** se solicitan KPIs sin un periodo o con `period_start`/`period_end`, **When** el nodo tiene mediciones, **Then** la API ignora los campos de fecha y la respuesta contiene mediciones de las últimas 24 horas con `startTime` (AT-10).
3. **Given** una consulta KPI contiene nodos no resueltos y un nodo resuelto sin mediciones, **When** se completa, **Then** se preservan mediciones de nodos resueltos, los no resueltos reciben `NODE_NOT_FOUND`, y el nodo sin mediciones no recibe error de nodo ni se clasifica por conectividad; los fallos de consulta Huawei se mantienen como errores HTTP (AT-12).
4. **Given** se consulta alarmas, **When** la API construye la respuesta, **Then** conserva los campos y paginación actuales y usa únicamente la consulta `CURRENT`, sin consulta histórica (AT-13).

### User Story 3 - Mantener compatibilidad y verificar el contrato del backend (Priority: P1)

El equipo puede comprobar automáticamente que la implementación respeta el contrato acordado y no expone secretos, manteniendo compatibles los campos existentes salvo el cambio explícito de 404 a 200 para un nodo 3G no encontrado.

**Why this priority**: Sin pruebas de aceptación y regresión, los consumidores no pueden depender de los códigos y formatos estables del contrato.

**Independent Test**: Ejecutar AT-11 y AT-14 junto con los escenarios anteriores; revisar que las pruebas y cambios se limitan al repositorio backend.

**Acceptance Scenarios**:

1. **Given** una respuesta de éxito de cada ruta cubierta, **When** se compara con el contrato, **Then** se mantienen los nombres y tipos de campos existentes, excepto el cambio 3G acordado (AT-11).
2. **Given** ejemplos, respuestas y registros de ejecución cubiertos por las pruebas, **When** se revisan, **Then** no contienen credenciales ni tokens (AT-14).
3. **Given** se implementa esta feature, **When** se revisan los archivos cambiados, **Then** no hay cambios en el repositorio del bot ni requisitos de pruebas que dependan de modificarlo.

### Edge Cases

- Un identificador no encontrado en 3G devuelve HTTP 200 y `NODE_NOT_FOUND`, no el 404 existente.
- En 3G, disponibilidad mixta de celdas no equivale a desconexión; si todas están `Unavailable`, se conservan los registros y se agrega `NODE_DISCONNECTED`.
- Errores de controladores que no alojan el NodeB no anulan registros de otra RNC.
- Un nodo KPI resuelto sin mediciones devuelve `records: []` y `errors: []`; no se infiere su conectividad.
- Un mapeo tecnológico ausente o ambiguo no debe provocar una consulta Huawei con un nombre inferido.
- Las alarmas clareadas solo se incluyen si la consulta actual `CURRENT` las devuelve; no se consulta historial.
- Los fallos HTTP y los errores por nodo permanecen distinguibles.
- Ningún ejemplo o salida de prueba debe revelar credenciales o tokens.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: La API MUST implementar el contrato y las reglas de resolución documentadas en `specs/003-telebot-operaciones-api/spec.md` y `specs/003-telebot-operaciones-api/contracts/telebot-operaciones.md` para los endpoints 3G, 4G, 5G, alarmas y KPIs.
- **FR-002**: La API MUST resolver identificadores exclusivamente con el directorio existente, usando `nodeb` para 3G y `nodo` para 4G/5G y KPIs; MUST incluir `name_resolution` con `input`, `resolved` y `status` por identificador.
- **FR-003**: Los errores por nodo MUST incluir un código estable cuando corresponda (`NODE_NOT_FOUND`, `NODE_DISCONNECTED`, `TECHNOLOGY_UNAVAILABLE`), mensaje legible en español, entrada original y nodo resuelto o `null`; MUST conservar el texto de origen en `error` cuando exista.
- **FR-004**: Los errores por nodo MUST responder HTTP 200. Los errores HTTP 400, 401, 422, 502, 503 y 504 MUST permanecer diferenciados y no usar códigos de error por nodo.
- **FR-005**: La API MUST preservar los registros válidos aunque fallen otros nodos, controladores o comandos; en 3G, todas las celdas `Unavailable` producen `NODE_DISCONNECTED` además de conservar los registros.
- **FR-006**: La respuesta de alarmas MUST conservar los campos y paginación actuales y mantener la equivalencia `alarmClearedTime` nulo con `cleared = "Activa"`, y no nulo con `cleared = "Limpia"`; la consulta MUST seguir limitada a `CURRENT`.
- **FR-007**: La consulta KPI MUST devolver las últimas 24 horas con `startTime`, ignorando cualquier campo `period_start` o `period_end` enviado; MUST informar identificadores no resueltos con `NODE_NOT_FOUND`, preservar registros de los resueltos y no emitir error por nodo ni inferir conectividad para un nodo resuelto sin mediciones. Los fallos de consulta Huawei MUST permanecer como errores HTTP según FR-004.
- **FR-008**: Las pruebas de aceptación del backend MUST cubrir todos los escenarios AT-01 a AT-14 definidos en el contrato de la feature 003, incluidos errores, resultados parciales, alarmas, KPIs y regresión.
- **FR-009**: La implementación y sus pruebas MUST limitarse al repositorio backend; no MUST requerir ni introducir cambios en el repositorio del bot.
- **FR-010**: Los ejemplos, respuestas y registros producidos o mantenidos por la feature MUST excluir credenciales y tokens.

### Key Entities *(include if feature involves data)*

- **Resultado de estado**: Registros, cantidad, errores y resolución de nombres de una consulta 3G, 4G o 5G.
- **Error por nodo**: Código estable opcional, mensaje, identificador enviado, nombre resuelto, texto original opcional y sugerencias cuando correspondan.
- **Resolución de nombre**: Identificador recibido, valor canónico resuelto y estado de resolución.
- **Alarma**: Alarma del sitio con sus tiempos de activación y clareo, estado de clareo y datos actuales de paginación.
- **Medición KPI**: Medición identificada por nodo y celda, con su hora de inicio y valores asociados.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Los 14 escenarios de aceptación AT-01 a AT-14 del contrato de la feature 003 pasan contra el backend con dependencias externas controladas.
- **SC-002**: El 100% de los escenarios por nodo distinguen `NODE_NOT_FOUND`, `NODE_DISCONNECTED` y `TECHNOLOGY_UNAVAILABLE` de los errores HTTP definidos en el contrato.
- **SC-003**: El 100% de los escenarios con resultados parciales conserva todos los registros válidos y cumple la excepción definida para celdas 3G `Unavailable`.
- **SC-004**: El 100% de las alarmas de prueba cumple la equivalencia entre `alarmClearedTime` y `cleared`, y las pruebas confirman que no se solicita historial.
- **SC-005**: Las pruebas de regresión de las rutas cubiertas pasan, con el único cambio de compatibilidad acordado para el not-found 3G.
- **SC-006**: Ningún archivo del repositorio del bot se modifica y ninguna prueba de aceptación requiere cambios allí.
- **SC-007**: Ningún ejemplo, respuesta ni registro de ejecución revisado por las pruebas contiene credenciales o tokens.

## Assumptions

- El contrato de `specs/003-telebot-operaciones-api/` es la fuente de verdad; esta feature lo implementa y no lo redefine.
- La resolución de sitios definida por la feature 002 y la autenticación existente permanecen disponibles.
- Las respuestas de Huawei y del directorio se pueden controlar en pruebas para cubrir los casos de éxito y error sin depender de servicios externos en la ejecución de aceptación.
- Las pruebas y cambios pertenecen al backend de este repositorio. La adaptación del consumidor y sus pruebas pertenecen al repositorio del bot y están fuera de alcance.
- No se requieren cambios de dependencias, contenedores ni almacenamiento para satisfacer el contrato, salvo que el diseño posterior identifique una necesidad concreta y autorizada.