# Contrato: API de Operaciones para Telebot Operaciones

Todos los ejemplos son ilustrativos y no incluyen credenciales ni tokens. Los endpoints requieren la autenticación ya existente (cabecera de autorización, no mostrada).

## Peticiones

| Tecnología | Endpoint | Cuerpo |
|---|---|---|
| 3G | `POST /mml/cell-summary-umts` | `{"nodeb_name": "AIS_3G_001"}` |
| 4G | `POST /mml/cell-summary-lte` | `{"ne_names": ["AIS_3G_001"]}` |
| 5G | `POST /mml/cell-summary-nr` | `{"ne_names": ["AIS_3G_001"]}` |
| KPIs | `POST /mml/kpis` | `{"ne_names": ["AIS_3G_001"]}` (sin `period_start`/`period_end`) |
| Alarmas | `GET /alarms/AIS_3G_001?limit=500` | n/a |

## Esquema de `errors[]`

```json
{
  "code": "NODE_NOT_FOUND | NODE_DISCONNECTED | TECHNOLOGY_UNAVAILABLE | null",
  "message": "Texto legible en español",
  "input": "valor enviado por el usuario",
  "ne_name": "valor resuelto o null",
  "error": "texto original de Huawei si existe (compatibilidad)",
  "suggestions": ["solo en NODE_NOT_FOUND, hasta 5"]
}
```

Reglas de precedencia por nodo: `NODE_NOT_FOUND` > `NODE_DISCONNECTED` > `TECHNOLOGY_UNAVAILABLE`. Si hay `records`, no se emite error de nodo.

## Ejemplos de respuesta

### 4G con resultado (200)

```json
{
  "commands": ["DSP CELL:;", "LST CELL:;"],
  "records": [
    {
      "ne_name": "MBTS-AIS_3G_001",
      "Local Cell ID": "0",
      "Cell Name": "AIS_3G_001_A",
      "Cell instance state": "Normal",
      "Maximum transmit power(0.1dBm)": "400",
      "Frequency band": "3",
      "Downlink EARFCN": "1650"
    }
  ],
  "count": 1,
  "errors": [],
  "name_resolution": [
    {"input": "AIS_3G_001", "resolved": "MBTS-AIS_3G_001", "status": "resolved"}
  ]
}
```

### 3G con resultado parcial (200)

```json
{
  "nodeb_name": "AIS_3G_001",
  "rnc_names_matched": ["STG03"],
  "pattern": "AIS_3G_001",
  "commands": ["DSP UCELL:DSPT=BYNODEB,NODEBNAME=\"AIS_3G_001\";", "LST UCELL:LSTTYPE=ByCellName,CELLNAME=\"AIS_3G_001\";"],
  "records": [
    {"ne_name": "STG03", "Cell ID": "101", "Cell name": "AIS_3G_001_1", "Operation state": "Enabled"}
  ],
  "count": 1,
  "errors": [
    {"code": null, "message": "Error en otro controlador.", "input": "AIS_3G_001", "ne_name": "STG04", "error": "NodeB is not configured"}
  ],
  "name_resolution": [
    {"input": "AIS_3G_001", "resolved": "AIS_3G_001", "status": "resolved"}
  ]
}
```

### Nodo no encontrado, cualquier tecnología (200)

```json
{
  "records": [],
  "count": 0,
  "errors": [
    {
      "code": "NODE_NOT_FOUND",
      "message": "No se encontró el nodo AIS_3G_00.",
      "input": "AIS_3G_00",
      "ne_name": null,
      "suggestions": ["AIS_3G_001"]
    }
  ],
  "name_resolution": [
    {"input": "AIS_3G_00", "resolved": null, "status": "not_found", "error": "No se encontró el sitio.", "suggestions": ["AIS_3G_001"]}
  ]
}
```

### Nodo desconectado (200)

```json
{
  "records": [],
  "count": 0,
  "errors": [
    {
      "code": "NODE_DISCONNECTED",
      "message": "Nodo desconectado.",
      "input": "AIS_3G_001",
      "ne_name": "MBTS-AIS_3G_001",
      "error": "Ne is not connected."
    }
  ],
  "name_resolution": [
    {"input": "AIS_3G_001", "resolved": "MBTS-AIS_3G_001", "status": "resolved"}
  ]
}
```

### Tecnología no disponible (200)

```json
{
  "records": [],
  "count": 0,
  "errors": [
    {
      "code": "TECHNOLOGY_UNAVAILABLE",
      "message": "El nodo no tiene la tecnología 5G disponible.",
      "input": "AIS_3G_001",
      "ne_name": null
    }
  ],
  "name_resolution": [
    {"input": "AIS_3G_001", "resolved": null, "status": "missing_mapping", "error": "El sitio no tiene mapeo para nodo."}
  ]
}
```

### Errores HTTP (sin código de nodo)

| Situación | Estado | Cuerpo |
|---|---|---|
| Token ausente o inválido | 401 | `{"detail": "..."}` |
| Cuerpo inválido | 422 | `{"detail": [...]}` |
| Huawei no completó la comunicación | 502 | `{"detail": "Huawei MML request could not be completed"}` |
| Directorio de sitios no disponible | 503 | `{"detail": "El directorio de sitios no está configurado o disponible."}` |

## Alarmas

```json
{
  "site_name": "AIS_3G_001",
  "alarms": [
    {
      "alarmId": "301",
      "alarmName": "Enlace caído",
      "meName": "MBTS-AIS_3G_001",
      "perceivedSeverity": "Mayor",
      "alarmRaisedTime": "2026-11-05T08:10:00-03:00",
      "alarmClearedTime": null,
      "cleared": "Activa"
    },
    {
      "alarmId": "22214",
      "alarmName": "Fallo de celda",
      "meName": "MBTS-AIS_3G_001",
      "perceivedSeverity": "Crítica",
      "alarmRaisedTime": "2026-11-05T06:00:00-03:00",
      "alarmClearedTime": "2026-11-05T07:30:00-03:00",
      "cleared": "Limpia"
    }
  ],
  "count": 2,
  "marker": null
}
```

Invariante: `alarmClearedTime == null` ⇔ `cleared == "Activa"`.

## KPIs

```json
{
  "records": [
    {
      "startTime": "2026-11-05T09:00:00",
      "neName": "MBTS-AIS_3G_001",
      "Cell Name": "AIS_3G_001_A",
      "Local Cell ID": "0",
      "ERAB Success Rate": "99.5",
      "User Max": "42",
      "Traffic": "1250",
      "Throughput": "8800"
    }
  ],
  "errors": [],
  "name_resolution": [
    {"input": "AIS_3G_001", "resolved": "MBTS-AIS_3G_001", "status": "resolved"}
  ]
}
```

`errors` es un campo nuevo (aditivo). `startTime` en hora de Chile sin zona explícita (comportamiento actual). Ventana: últimas 24 h ya publicadas.

## Pruebas de aceptación

| ID | Escenario | Resultado esperado |
|---|---|---|
| AT-01 | Mismo identificador en 3G/4G/5G con directorio simulado | Cada tecnología resuelve con su columna; `name_resolution` correcto |
| AT-02 | Identificador inexistente, uno y varios nodos, en 3G/4G/5G/KPIs | 200, `NODE_NOT_FOUND`, `suggestions` |
| AT-03 | NE devuelve "Ne is not connected." (4G/5G) | 200, `NODE_DISCONNECTED`, `records: []` |
| AT-04 | NodeB 3G desconectado | Pendiente de fixture real (Pendiente 1) |
| AT-05 | Sitio sin mapeo / conectado sin celdas de la tecnología | 200, `TECHNOLOGY_UNAVAILABLE` |
| AT-06 | 3G: una RNC con celdas y otras con error | `records` completos; sin código de nodo |
| AT-07 | 4G/5G: lote mixto | `records` de los buenos y `errors` del fallido |
| AT-08 | 401, 422, 502, 503 | Sin `errors[].code` de FR-006 |
| AT-09 | Alarmas: sin fecha / con fecha / contradictoria | Invariante de consistencia siempre se cumple |
| AT-10 | KPIs sin periodo | Mediciones de 24 h con `startTime`; sin parámetros de periodo |
| AT-11 | Regresión: nombres completos y esquemas actuales | Sin cambios salvo FR-007 |
