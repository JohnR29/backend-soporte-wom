# Feature Specification: API de Operaciones lista para Telebot Operaciones

**Feature Branch**: `003-telebot-operaciones-api`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Preparar la API de Operaciones para la integración con Telebot Operaciones. En esta fase se define y documenta el contrato y los criterios de aceptación; no se implementan cambios de código."

## Clarifications

### Session 2026-11-05

- Q: Si el identificador no existe en el directorio, ¿cómo responde `/mml/cell-summary-umts` (hoy HTTP 404)? → A: HTTP 200 con `errors[].code = NODE_NOT_FOUND`, igual que 4G/5G.
- Q: ¿Cuándo se emite `TECHNOLOGY_UNAVAILABLE`? → A: Cuando el nodo existe pero el directorio no tiene mapeo para esa tecnología, o cuando está conectado y no devuelve celdas/NE de esa tecnología. No se emite si el nodo está desconectado.
- Q: ¿De dónde salen las cinco alarmas clareadas más recientes? → A: Solo de la consulta actual (`dataType=CURRENT`) ya existente; si no incluye clareadas, el bot no muestra ninguna. No se añade consulta histórica.
- Q: Si el sitio existe en el directorio con `nodeb` pero ninguna RNC devuelve celdas del NodeB, ¿qué código se emite en 3G? → A: `NODE_NOT_FOUND` (todas las RNC informan que el NodeB no está configurado).
- Q: Si el identificador se resuelve a un nodo válido pero `/mml/kpis` no devuelve mediciones, ¿qué responde la API? → A: `records: []` y `errors: []`, sin código de nodo.

### Session 2026-11-08

- Q: ¿3G acepta una lista de nodos? → A: No; 3G consulta un NodeB por solicitud. Los lotes aplican a 4G/5G y KPIs.
- Q: ¿Cómo se observa un NodeB 3G desconectado? → A: La RNC responde con las celdas y su estado; la regla de clasificación quedó definida el 2026-11-09.

### Session 2026-11-09

- Q: ¿Qué valor de estado identifica una celda 3G indisponible? → A: `Operation state = "Unavailable"`.
- Q: ¿Cuándo se clasifica como desconectado un NodeB 3G? → A: Cuando todas las celdas devueltas tienen `Operation state = "Unavailable"`; si solo algunas tienen ese estado, no se emite `NODE_DISCONNECTED`.
- Q: ¿Se conservan los registros cuando todas las celdas 3G están indisponibles? → A: Sí. Se devuelven las celdas en `records` y además un error `NODE_DISCONNECTED`.

## Consumidores y alcance

- **Consumidor**: Telebot Operaciones (bot), autenticado con el token existente de la API. 3G acepta un NodeB por solicitud; 4G/5G y KPIs aceptan uno o varios identificadores. Actualmente el bot usa comandos separados por tecnología y no consulta las tres automáticamente.
- **Dentro de alcance**: contrato de `POST /mml/cell-summary-umts`, `POST /mml/cell-summary-lte`, `POST /mml/cell-summary-nr`, `GET /alarms/{site_name}` y `POST /mml/kpis`.
- **Fuera de alcance**: cálculo de estado global entre tecnologías (lo hace el bot, que muestra 3G/4G/5G por separado), formato de mensajes del bot, alarmas históricas, cambios en la tabla de sitios, otros endpoints (`/mml/command`, `/mml/scripts`, `/alarms/hermes`, `/alarms/license-trial`).
- **Naturaleza de los datos**: tiempo real. La API no entrega un timestamp de origen para el estado de celdas; el bot muestra la hora en que inició su consulta.

## Estado verificado contra el repositorio

| Afirmación del contexto | Estado | Evidencia |
|---|---|---|
| 3G recibe `nodeb_name`; 4G/5G reciben `ne_names` | Confirmado | `UmtsCellSummaryRequest`, `CellSummaryRequest` en `app/api/routes/huawei.py` |
| El mismo identificador se resuelve distinto en 3G y 4G/5G | Confirmado, y es por diseño de la spec 002 | 3G resuelve contra la columna `nodeb`; 4G/5G y KPIs contra `nodo` de `public.cellreference` |
| No hay reglas de prefijos en el código | Confirmado | Spec 002: "no se prueban prefijos por intentos contra Huawei" |
| Respuestas con `records`, `count`, `errors`, `name_resolution` | Confirmado en 3G/4G/5G; `/mml/kpis` solo devuelve `records` y `name_resolution` (sin `count` ni `errors`) | Código de las rutas |
| `errors` es `[{ne_name, error}]` con texto libre de Huawei | Confirmado; no existen los códigos `NODE_NOT_FOUND`, `NODE_DISCONNECTED`, `TECHNOLOGY_UNAVAILABLE` | `grep` en `app/` sin resultados |
| Nodo desconectado: Huawei devuelve "Ne is not connected." | Confirmado (pruebas y README) | `tests/test_huawei_route.py`, README |
| Un solo nodo fallido en 4G/5G responde 200 con `errors` | Confirmado (bug corregido) | `.specify/bugs/cell-summary-single-node-error/` |
| 3G con identificador inexistente responde HTTP 404 con `detail` | Confirmado; este contrato lo cambia (ver FR-007) | `create_cell_summary_umts` |
| 4G/5G con identificador inexistente | Hoy: 200, `records: []`, `errors: []` y el fallo solo aparece en `name_resolution[].status = "not_found"` | `_resolve_node_names` + `create_cell_summary` |
| `/alarms/{site}?limit=500` solo consulta `dataType=CURRENT` | Confirmado; `limit` 1–1000, por defecto 500 | `alarms.py` |
| `cleared` es "Activa"/"Limpia"; `alarmClearedTime` es `null` si es 0 o falta | Confirmado, pero ambos campos se derivan por separado y pueden contradecirse | `_simplify_alarm`, `_epoch_ms_to_iso` |
| `/mml/kpis` devuelve las últimas 24 h sin `period_start`/`period_end` y cada fila trae `startTime` | Confirmado; ventana horaria cerrada con desfase de 15 min; `startTime` en hora de Chile sin zona explícita; solo contadores de eNodeB (4G) | `_last_24h_window`, `_flatten_measurement_results` |
| NodeB 3G desconectado | Confirmado por el responsable de dominio: si todas las celdas devueltas tienen `Operation state = "Unavailable"`, se conserva `records` y se añade `NODE_DISCONNECTED`; disponibilidad mixta no produce ese error | Aclaración 2026-11-09 |
| Si `CURRENT` incluye alarmas clareadas | **Pendiente**: no confirmado contra el MAE real | Ver Pendientes |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar estado por tecnología con un mismo identificador (Priority: P1)

El bot envía el identificador escrito por el usuario (p. ej. `AIS_3G_001`) a los tres endpoints de estado y obtiene, por separado, el resultado 3G, 4G y 5G.

**Why this priority**: Es la consulta principal del bot.

**Independent Test**: Enviar el mismo identificador a los tres endpoints con directorio y Huawei simulados y comprobar que cada uno lo resuelve con la regla de su tecnología y devuelve `name_resolution` con entrada original y valor resuelto.

**Acceptance Scenarios**:

1. **Given** `AIS_3G_001` está en el directorio con `nodo = MBTS-AIS_3G_001` y `nodeb = AIS_3G_001`, **When** el bot lo envía a 3G (`nodeb_name`) y a 4G/5G (`ne_names`), **Then** 3G usa `AIS_3G_001`, 4G/5G usan `MBTS-AIS_3G_001`, y cada respuesta lo indica en `name_resolution`.
2. **Given** un identificador válido, **When** se consulta una tecnología, **Then** la respuesta trae `records`, `count`, `errors` y `name_resolution`.
3. **Given** el bot consulta solo un nodo, **When** el nodo falla, **Then** la respuesta sigue siendo HTTP 200 con `records: []`, `count: 0` y el error por nodo.

---

### User Story 2 - Errores por nodo con códigos estables (Priority: P1)

Para cada nodo con problemas, la API informa un código estable y un mensaje legible, distinguible de los errores HTTP.

**Why this priority**: El bot debe mostrar "Nodo desconectado" u otros textos sin interpretar texto libre de Huawei.

**Independent Test**: Simular nodo inexistente, nodo desconectado y nodo sin la tecnología; verificar HTTP 200 y el `code` esperado en `errors`.

**Acceptance Scenarios**:

1. **Given** un identificador que no existe en el directorio, **When** se consulta 3G, 4G o 5G, **Then** HTTP 200, `records: []` y un error `NODE_NOT_FOUND` con `suggestions` si las hay.
2. **Given** un nodo 4G/5G que Huawei reporta como no conectado, o un NodeB 3G cuyas celdas tienen todas `Operation state = "Unavailable"`, **When** se consulta, **Then** HTTP 200 y un error `NODE_DISCONNECTED`; para el caso 3G también se conservan las celdas en `records`.
3. **Given** un nodo que existe pero sin mapeo para la tecnología, o conectado sin celdas de esa tecnología, **When** se consulta esa tecnología, **Then** HTTP 200 y un error `TECHNOLOGY_UNAVAILABLE`.
4. **Given** Huawei no responde, el token es inválido o el cuerpo no cumple el esquema, **When** se consulta, **Then** la respuesta es 502/401/422 según corresponda y **no** contiene `errors[].code` de nodo.

---

### User Story 3 - Resultados parciales preservados (Priority: P1)

Si algunos controladores o comandos fallan pero el nodo consultado devolvió celdas, esas celdas se entregan.

**Why this priority**: Un fallo ajeno no debe ocultar datos válidos.

**Independent Test**: 3G con un controlador que devuelve celdas y otros que devuelven error; verificar `records` completo y errores de los otros controladores sin invalidar el resultado.

**Acceptance Scenarios**:

1. **Given** el NodeB devuelve al menos una celda cuyo `Operation state` no es `Unavailable` y otras RNC devuelven error, **When** se consulta 3G, **Then** se conservan las celdas y no se emite `NODE_DISCONNECTED` ni `NODE_NOT_FOUND` para el nodo.
2. **Given** una consulta 4G/5G con varios nodos donde uno falla, **When** se ejecuta, **Then** los demás aportan `records` y el fallido aparece en `errors`.
3. **Given** un NodeB 3G devuelve celdas con disponibilidad mixta, **When** se consulta, **Then** todas las celdas se conservan y no se emite `NODE_DISCONNECTED`; si todas son `Unavailable`, se conservan y se emite `NODE_DISCONNECTED`.

---

### User Story 4 - Alarmas vigentes y clareadas consistentes (Priority: P2)

El bot filtra las vigentes y muestra aparte las cinco clareadas más recientes sin reinterpretar campos contradictorios.

**Why this priority**: Mejora el diagnóstico, pero depende de la consulta de estado.

**Independent Test**: Alarmas simuladas con distintas combinaciones de `cleared`/`alarmClearedTime`; verificar que nunca se contradicen.

**Acceptance Scenarios**:

1. **Given** una alarma sin fecha de clareo, **When** se consulta, **Then** `alarmClearedTime: null` y `cleared: "Activa"`.
2. **Given** una alarma con fecha de clareo, **When** se consulta, **Then** `alarmClearedTime` es ISO 8601 y `cleared: "Limpia"`.
3. **Given** el origen reporta `cleared` y la fecha en conflicto, **When** se consulta, **Then** prevalece la fecha (FR-014).

---

### User Story 5 - KPIs de las últimas 24 horas (Priority: P2)

El bot consulta KPIs enviando solo el nodo; la API devuelve las últimas 24 horas con `startTime` en cada medición.

**Independent Test**: `POST /mml/kpis` con `ne_names` y sin fechas; verificar filas con `startTime` dentro de las últimas 24 h y errores por nodo para identificadores no resueltos.

**Acceptance Scenarios**:

1. **Given** un nodo válido, **When** se consulta sin `period_start`/`period_end`, **Then** se devuelven mediciones horarias con `startTime`.
2. **Given** un identificador inexistente, **When** se consulta, **Then** `records: []` y un error `NODE_NOT_FOUND`.

---

### Edge Cases

- Entrada en minúsculas o con espacios externos: se normaliza (spec 002); `name_resolution[].input` conserva el valor original.
- Identificador que en el directorio tiene mapeo ambiguo (`ambiguous_mapping`): error de nodo con `TECHNOLOGY_UNAVAILABLE` y no se llama a Huawei (ver FR-006).
- El bot envía a 3G el nombre 4G/5G (p. ej. `MBTS-AIS_3G_001`) y ese valor no está en `nodeb` ni es un sitio: `NODE_NOT_FOUND`. No se infieren ni se quitan prefijos.
- Directorio de sitios no disponible: error HTTP 503 (error de servidor, no resultado por nodo).
- Nodo 4G/5G desconectado: `records: []`; si además otros controladores fallan, solo se informa el error del nodo consultado en el código estable. En 3G, todas las celdas con `Operation state = "Unavailable"` producen `NODE_DISCONNECTED` conservando registros; disponibilidad mixta no produce ese error.
- Nodo conectado pero con `records` vacíos en una tecnología de estado (3G/4G/5G): `TECHNOLOGY_UNAVAILABLE`; en KPIs no se emite error.
- Alarmas del sitio inexistentes o sin alarmas: `alarms: []`, `count: 0` (no se distingue sitio inexistente de sitio sin alarmas).
- Más de 500 alarmas: se respeta `limit`/`marker` existentes; el bot usa los 500 solicitados.
- Orden de `alarms`: no garantizado; el bot ordena clareadas por `alarmClearedTime` descendente.

## Requirements *(mandatory)*

### Functional Requirements

**Identificadores**

- **FR-001**: Los tres endpoints de estado MUST aceptar el mismo identificador escrito por el usuario (en `nodeb_name` para 3G, en `ne_names` para 4G/5G).
- **FR-002**: La resolución MUST hacerse solo mediante el directorio de sitios (spec 002): coincidencia por `sitio` o por valor canónico de la columna de la tecnología (`nodeb` para 3G, `nodo` para 4G/5G y KPIs), sin distinguir mayúsculas ni espacios externos.
- **FR-003**: El sistema MUST NOT agregar, quitar ni inferir prefijos fuera de lo que indique el directorio. Que `AIS_3G_001` se resuelva como `MBTS-AIS_3G_001` en 4G/5G y como `AIS_3G_001` en 3G es consecuencia de los valores almacenados en el directorio.
- **FR-004**: Toda respuesta de estado y KPIs MUST incluir `name_resolution` con `input`, `resolved` y `status` por identificador.

**Errores por nodo**

- **FR-005**: `errors` MUST ser una lista de objetos con, como mínimo: `code`, `message` (legible, en español), `input` y `ne_name` (valor resuelto o `null`; nombre del controlador para errores de controlador). El campo existente `error` (texto original de Huawei) se conserva por compatibilidad.
- **FR-006**: Los códigos estables son:
  - `NODE_NOT_FOUND`: el identificador no existe en el directorio, o Huawei informa que el NE no existe; en 3G, también cuando el sitio tiene `nodeb` en el directorio pero todas las RNC informan que el NodeB no está configurado. Incluye `suggestions` cuando las hay.
  - `NODE_DISCONNECTED`: en 4G/5G, el nodo existe y Huawei informa que el NE no está conectado sin entregar datos; en 3G, todas las celdas devueltas tienen `Operation state = "Unavailable"`. En este caso 3G se conservan los `records` junto con el error.
  - `TECHNOLOGY_UNAVAILABLE`: el nodo existe pero el directorio no tiene mapeo para esa tecnología (`missing_mapping`, `ambiguous_mapping`), o está conectado y no devolvió celdas/NE de esa tecnología (en 3G, solo si una RNC lo reconoce y no devuelve celdas). No se emite si el nodo está desconectado.
- **FR-007**: Un error por nodo MUST responder HTTP 200. `/mml/cell-summary-umts` deja de responder 404 para identificador inexistente y usa `NODE_NOT_FOUND`.
- **FR-008**: Los errores HTTP MUST seguir distinguibles: 401 (token), 422 (esquema), 502/504 (Huawei no completó la comunicación), 503 (directorio no disponible), 400 (solicitud rechazada por Huawei). Estos NO usan los códigos de FR-006.
- **FR-009**: Otros fallos por nodo no cubiertos por FR-006 MUST seguir apareciendo en `errors` con su `error` original y `code: null`, sin ocultarlos.
- **FR-010**: Los fallos por nodo MUST funcionar igual para una consulta de un solo nodo y de varios en los endpoints que aceptan listas (4G/5G y KPIs); 3G acepta un NodeB por solicitud.

**Resultados parciales**

- **FR-011**: Los `records` obtenidos MUST conservarse aunque otros controladores, comandos o nodos fallen. Los errores de otros controladores no invalidan los `records` del nodo consultado. Excepción: para 3G, si todas las celdas devueltas tienen `Operation state = "Unavailable"`, se conservan los `records` y se añade `NODE_DISCONNECTED`; `NODE_NOT_FOUND` no se emite si el nodo entregó datos.
- **FR-012**: Cada tecnología MUST responder de forma independiente; la API no calcula un estado global entre tecnologías ni mezcla registros de tecnologías distintas.

**Alarmas**

- **FR-013**: `GET /alarms/{site_name}?limit=500` MUST seguir devolviendo `alarms`, `count`, `marker` y los campos actuales.
- **FR-014**: `alarmClearedTime` y `cleared` MUST ser consistentes: `alarmClearedTime` no nulo ⇔ `cleared = "Limpia"`; `alarmClearedTime` nulo ⇔ `cleared = "Activa"`. Ante contradicción en el origen, prevalece `alarmClearedTime`.
- **FR-015**: Una alarma está vigente si `alarmClearedTime` es `null`; está clareada si tiene fecha de clareo. El bot decide qué mostrar; la API no filtra ni limita.
- **FR-016**: Las clareadas provienen únicamente de la consulta `CURRENT`; la API no añade consulta histórica.

**KPIs**

- **FR-017**: `POST /mml/kpis` con `ne_names` MUST devolver automáticamente las últimas 24 horas sin aceptar ni requerir `period_start`/`period_end`; cada fila lleva `startTime`.
- **FR-018**: `/mml/kpis` MUST informar identificadores no resueltos con `errors` según FR-005/FR-006 y conservar `records` de los resueltos. Un nodo resuelto sin mediciones devuelve `records: []` y `errors: []`; el resto de campos actuales no cambia.

**Compatibilidad**

- **FR-019**: Los cambios MUST ser aditivos salvo el cambio de 404 a 200 en 3G (FR-007); `records`, `count`, `commands`, `name_resolution` y los campos de celdas existentes no cambian de nombre ni de tipo.
- **FR-020**: Ningún ejemplo, log ni respuesta de este contrato incluye credenciales o tokens.

### Key Entities

- **Resultado por tecnología**: `records`, `count`, `errors`, `name_resolution` de una consulta 3G, 4G o 5G.
- **Error por nodo**: `code`, `message`, `input`, `ne_name`, `error` (original), `suggestions` opcional.
- **Resolución de nombre**: `input`, `resolved`, `status` por identificador.
- **Alarma**: `alarmId`, `alarmName`, `perceivedSeverity`, `alarmRaisedTime`, `alarmClearedTime`, `cleared`, etc.
- **Medición KPI**: `startTime`, `neName`, `Cell Name`, `Local Cell ID` y un valor por KPI.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los escenarios de fallo por nodo (inexistente, desconectado, sin tecnología) de las tres tecnologías devuelve HTTP 200 con el código esperado: un NodeB por solicitud en 3G y uno o varios nodos en 4G/5G. En 3G, todas las celdas `Unavailable` producen `NODE_DISCONNECTED` conservando sus registros; disponibilidad mixta no produce ese código.
- **SC-002**: En el 100% de los casos de error HTTP (401, 422, 502, 503) la respuesta no contiene un código de nodo de FR-006.
- **SC-003**: En todas las pruebas con resultados mixtos, el 100% de los `records` válidos se conserva.
- **SC-004**: En el 100% de las alarmas de prueba, `cleared` y `alarmClearedTime` son coherentes (FR-014).
- **SC-005**: El bot puede mostrar "Nodo desconectado" usando únicamente `code = NODE_DISCONNECTED`, sin interpretar texto libre.
- **SC-006**: Las pruebas existentes de las rutas siguen pasando; solo cambia la prueba de 404 en 3G.

## Assumptions

- El directorio de sitios (spec 002) es la fuente de verdad del identificador; el bot no aplica reglas propias de prefijos.
- La detección de `NODE_DISCONNECTED` en 4G/5G se basa en el texto "Ne is not connected." de Huawei (confirmado en pruebas y README); se aísla en un único punto de mapeo.
- En 3G, el estado `Operation state = "Unavailable"` en todas las celdas devueltas identifica `NODE_DISCONNECTED`; disponibilidad mixta conserva las celdas sin error de desconexión.
- Los errores de las RNC que no alojan el NodeB (p. ej. "NodeB is not configured") en 3G no se consideran fallo del nodo si otra RNC devuelve celdas.
- Todo contrato nuevo es aditivo; los consumidores actuales que ignoren campos desconocidos no se rompen.
- `startTime` de KPIs se mantiene en hora de Chile sin zona explícita, y las horas de alarmas en ISO 8601 con zona de Chile.

## Pendientes de confirmación

1. **Alarmas clareadas en `CURRENT`**: no está confirmado que Huawei las devuelva; si no, el bot no mostrará clareadas (decisión ya aceptada).
2. **Fallo por nodo en KPIs**: el contrato solo cubre identificadores no resueltos; el comportamiento ante un nodo desconectado en KPIs no está especificado porque la consulta de rendimiento no informa conexión.

## Integración con el bot

Según el análisis del repositorio del bot proporcionado por su agente, actualmente existen comandos separados por tecnología: 3G envía un `nodeb_name` y 4G/5G envían listas `ne_names`. El bot muestra `records` y solo cuenta los elementos de `errors`; todavía no interpreta sus códigos ni `name_resolution`. Tampoco clasifica alarmas por fecha de clareo ni interpreta el estado de las celdas. Estos son comportamientos actuales del consumidor, no garantías del contrato objetivo. La implementación y pruebas del bot corresponden a su propio repositorio.
