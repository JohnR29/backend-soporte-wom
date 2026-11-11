# HTTP Contracts: Name Resolution & Alarms Endpoint

**Endpoint**: `GET /alarms/{site-name}`  
**Branch**: `005-alarms-node-resolution`

---

## Request

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `site-name` | `string` | Yes | Nemónico del sitio (ej. "AN0069"). Normalizado por el servidor (trim, mayúsculas). |

### Query Parameters
| Parameter | Type | Required | Default | Values | Description |
|-----------|------|----------|---------|--------|-------------|
| `technology` | `string` | No | `4G` | `3G`, `4G`, `5G` | Tecnología del nodo a consultar. Determina qué mapeo de la tabla cellreference usar. |

### Request Headers
```
Accept: application/json
Authorization: [Bearer token, if auth is required]
```

### Example Request
```http
GET /alarms/AN0069?technology=4G HTTP/1.1
Host: backend.example.com
Accept: application/json
```

---

## Responses

### 200 OK — Alarmas obtenidas exitosamente

**Description**: El sitio fue resuelto, el nodo fue encontrado, y las alarmas fueron obtenidas de la API de Huawei.

**Content-Type**: `application/json`

#### Response Schema (Pydantic Model)
```python
class AlarmData(BaseModel):
    """Alarm from Huawei API"""
    id: str
    node: str
    severity: str
    description: str
    timestamp: datetime
    # ... (rest of Huawei alarm fields)

class SuccessResponse(BaseModel):
    """200 OK response for alarms query"""
    error: None = None
    resolved_site: str  # nemonica
    resolved_node: str  # canonical node name
    technology: str  # 3G, 4G, or 5G
    user_input: str  # what user provided
    alarms: List[AlarmData]
    alarm_count: int
    timestamp: datetime
```

#### Example Response
```json
{
  "error": null,
  "resolved_site": "AN0069",
  "resolved_node": "MBTS-AN0069",
  "technology": "4G",
  "user_input": "AN0069",
  "alarms": [
    {
      "id": "alarm_001",
      "node": "MBTS-AN0069",
      "severity": "CRITICAL",
      "description": "CPU utilization > 95%",
      "timestamp": "2026-11-09T19:50:00Z"
    },
    {
      "id": "alarm_002",
      "node": "MBTS-AN0069",
      "severity": "WARNING",
      "description": "Temperature > 60°C",
      "timestamp": "2026-11-09T19:45:00Z"
    }
  ],
  "alarm_count": 2,
  "timestamp": "2026-11-09T19:58:00Z"
}
```

---

### 404 Not Found — Sitio/Nodo no encontrado

**Description**: El sitio no existe en la tabla cellreference, O el sitio existe pero carece del mapeo requerido para la tecnología solicitada. Incluye sugerencias basadas en similitud.

**Content-Type**: `application/json`

#### Response Schema (Pydantic Model)
```python
class SiteSuggestion(BaseModel):
    """Suggested site for typo correction"""
    nemonica: str
    nodo: Optional[str] = None  # 4G/5G node
    nodeb: Optional[str] = None  # 3G node
    similarity: float  # 0.0 to 1.0

class NotFoundResponse(BaseModel):
    """404 response when site/node not found"""
    error: str = "not_found"  # or "missing_mapping"
    message: str  # Descriptive error message in Spanish
    user_input: str
    technology: str
    resolved_node: None = None
    resolved_site: Optional[str] = None  # Set if error="missing_mapping"
    suggestions: List[SiteSuggestion] = []  # Max 5, sorted by similarity desc, then alphabetically
    available_technologies: Optional[List[str]] = None  # Only if error="missing_mapping"
    timestamp: datetime
```

#### Example Response — Site Not Found
```json
{
  "error": "not_found",
  "message": "El sitio 'AN0096' no fue encontrado en el directorio",
  "user_input": "AN0096",
  "technology": "4G",
  "resolved_node": null,
  "resolved_site": null,
  "suggestions": [
    {
      "nemonica": "AN0069",
      "nodo": "MBTS-AN0069",
      "nodeb": null,
      "similarity": 0.85
    },
    {
      "nemonica": "AN0086",
      "nodo": "MBTS-AN0086",
      "nodeb": null,
      "similarity": 0.80
    }
  ],
  "available_technologies": null,
  "timestamp": "2026-11-09T19:58:00Z"
}
```

#### Example Response — Site Exists but Missing Mapping for Technology
```json
{
  "error": "missing_mapping",
  "message": "El sitio 'AN0069' existe pero no tiene mapeo para la tecnología '3G'",
  "user_input": "AN0069",
  "technology": "3G",
  "resolved_node": null,
  "resolved_site": "AN0069",
  "suggestions": [],
  "available_technologies": ["4G", "5G"],
  "timestamp": "2026-11-09T19:58:00Z"
}
```

---

### 503 Service Unavailable — Directorio de sitios no disponible

**Description**: La base de datos del directorio de sitios (`SITE_DIRECTORY_DATABASE_URL`) no es accesible. No se intenta consultar la API de Huawei.

**Content-Type**: `application/json`

#### Response Schema (Pydantic Model)
```python
class ServiceUnavailableResponse(BaseModel):
    """503 response when site directory unreachable"""
    error: str = "service_unavailable"
    message: str  # Descriptive message
    details: str  # "site_directory_unreachable"
    timestamp: datetime
```

#### Example Response
```json
{
  "error": "service_unavailable",
  "message": "El directorio de sitios no está disponible",
  "details": "site_directory_unreachable",
  "timestamp": "2026-11-09T19:58:00Z"
}
```

---

### 422 Unprocessable Entity — Validación de entrada fallida

**Description**: El parámetro `technology` contiene un valor no reconocido, o `site-name` está vacío.

**Content-Type**: `application/json`

#### Response Schema (FastAPI/Pydantic default)
```json
{
  "detail": [
    {
      "type": "string_type",
      "loc": ["query", "technology"],
      "msg": "Input should be a valid string",
      "input": "invalid_tech"
    }
  ]
}
```

---

### 500 Internal Server Error

**Description**: Error inesperado en el servidor (no es error de disponibilidad del directorio; ej. bug en resolución).

**Content-Type**: `application/json`

#### Response Schema (Pydantic Model)
```python
class InternalErrorResponse(BaseModel):
    """500 response for unexpected errors"""
    error: str = "internal_error"
    message: str
    request_id: str  # For correlation with logs
    timestamp: datetime
```

#### Example Response
```json
{
  "error": "internal_error",
  "message": "Error interno procesando la solicitud",
  "request_id": "req_abc123def456",
  "timestamp": "2026-11-09T19:58:00Z"
}
```

---

## Error Codes & Mapping

| HTTP Status | `error` field | Condition |
|-------------|---------------|-----------|
| 200 | `null` | Sitio resuelto exitosamente; alarmas obtenidas. |
| 404 | `"not_found"` | Sitio/nodo no existe. |
| 404 | `"missing_mapping"` | Sitio existe pero sin mapeo para la tecnología solicitada. |
| 503 | `"service_unavailable"` | Directorio (DB) no accesible; Huawei no fue consultado. |
| 422 | (FastAPI validation) | Parámetro malformado (ej. `technology` inválido). |
| 500 | `"internal_error"` | Error no capturado en la lógica de resolución. |

---

## Behavioral Specs

### Name Resolution Logic
1. Recibe `user_input` (path param) y `technology` (query param, default 4G).
2. Normaliza `user_input` → `normalized_input` (trim, uppercase).
3. Consulta DB: `SELECT nodo, nodeb FROM public.cellreference WHERE nemonica = normalized_input AND status = 'active'`.
4. **If found**:
   - Selecciona columna según `technology` (nodo para 4G/5G, nodeb para 3G).
   - If columna es NULL → error `"missing_mapping"` (404).
   - If columna tiene valor → ✅ (200 OK, proceed to Huawei API call).
5. **If not found**:
   - Computa similitud de `normalized_input` con todos los nemonica activos usando `difflib.SequenceMatcher`.
   - Filtra sitios con similitud ≥ 0.6.
   - Ordena por similitud desc, luego alfabético por nemonica.
   - Toma top 5.
   - Retorna error `"not_found"` (404) con sugerencias.
6. **If DB unreachable** → error `"service_unavailable"` (503); no llamar Huawei.

### Metadata & Logging
- Incluir en respuesta: `user_input`, `resolved_site`, `resolved_node`, `technology`, `timestamp`.
- Log internamente: tiempo de DB query, número de sugerencias, latencia total.
- Redactar: no exponerse credenciales ni stack trace completo en respuesta de error.

### Performance Requirements
- Name resolution (DB lookup + similarity search) ≤ 300ms p95.
- Huawei API call (existing) ≤ 200ms p95 (no change).
- Total latency ≤ 500ms p95.

---

## Testing Contracts (Happy & Sad Paths)

See [../quickstart.md](../quickstart.md) for runnable validation scenarios.

