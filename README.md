# backend-soporte

Backend intermediario para consultas a la API de Huawei. Desarrollo en Windows, despliegue en VM Ubuntu (con proxy corporativo).

## Instalacion

```powershell
conda create -n backend-soporte python=3.11
conda activate backend-soporte
pip install -r requirements.txt
copy .env.example .env
```

## Ejecucion en desarrollo

```powershell
uvicorn app.main:app --reload
```

Visita `http://127.0.0.1:8000/health` para comprobar el estado del servicio y
`http://127.0.0.1:8000/docs` para consultar la documentacion interactiva.

## Configuracion

Consulta `.env.example` (entorno local, sin proxy) y
`.env.production.example` (VM, proxy habilitado). Variables principales:

- `USE_PROXY` / `PROXY_URL` — habilitar solamente en la VM. El proxy se usa para construir la imagen (`pip`) y para las llamadas a WOM Portal; la API de Huawei siempre se consulta sin proxy. En local deja `USE_PROXY=false` y `PROXY_URL` vacío.
- `HUAWEI_VERIFY_SSL` — en producción se configura como `false` para Huawei; la conexión sigue cifrada, pero no se valida el certificado del servidor.
- `HUAWEI_API_BASE_URL` — URL base de la API de Huawei.
- `HUAWEI_USERNAME` / `HUAWEI_PASSWORD` — cuenta tecnica de Huawei, utilizada solamente por el backend.
- `BACKEND_STATIC_TOKEN` — token fijo que los clientes envian en cada solicitud.
- `DATABASE_URL` — conexión a Postgres para la auditoría (`postgresql+asyncpg://usuario:clave@host:5432/base`). Vacío desactiva la auditoría.
- `AUDIT_MAX_BODY_BYTES` — tamaño máximo del cuerpo de request que se guarda (8192 por defecto); si lo supera solo se registra el tamaño.

## Autenticacion

Envia el token fijo configurado en `BACKEND_STATIC_TOKEN` como
`Authorization: Bearer <token>` en cada ruta protegida. Los valores de sesion
de Huawei `accessSession` y `roaRand` nunca salen del backend.

Este mecanismo temporal de token fijo sera reemplazado posteriormente por un
sistema real de emision de tokens. No existe un endpoint de inicio de sesion:
el token no se obtiene del backend, sino que es un secreto compartido
configurado fuera de la aplicacion.


## Comandos MML

Todos los endpoints MML requieren el token del backend en la cabecera
`Authorization`. La lista de nodos (`ne_names`) debe contener entre 1 y 100
nombres.

### Ejecutar un comando

Envia un comando MML autenticado a `POST /mml/command`:

```json
{
	"command": "display version;",
	"ne_names": ["NE-001", "NE-002"]
}
```

El backend envia el comando a Huawei como un unico lote. Cada reporte de
Huawei se procesa e incluye su codigo de retorno, fecha y hora, y registros.
Un nodo fallido se conserva en `results` en lugar de descartarse:

```json
{
	"name": "NE-OFFLINE",
	"report": {"error": "Ne is not connected."},
	"result": "Failed.",
	"retCode": -1
}
```

Si Huawei rechaza el lote completo porque uno o mas nodos no existen, el
backend elimina esos nombres, reintenta el lote restante y agrega un resultado
fallido por cada nodo desconocido:

```json
{
	"name": "NE-UNKNOWN",
	"report": {"error": "NE no existe o el nombre está mal escrito."},
	"result": "Failed.",
	"retCode": -1
}
```

Los resultados se devuelven en el mismo orden de `ne_names`. Que un nodo este
desconectado o no exista no impide que los demas nodos devuelvan sus datos.

### Resumen de celdas LTE

`POST /mml/cell-summary-lte` ejecuta `DSP CELL:;` y `LST CELL:;` para el lote
solicitado y combina los resultados usando `ne_name` y `Local Cell ID`.

```json
{
	"ne_names": ["NE-001", "NE-OFFLINE", "NE-UNKNOWN"]
}
```

La respuesta contiene los datos de celdas en `records`, la cantidad de
registros de celdas en `count` y los errores por nodo en `errors`:

```json
{
	"commands": ["DSP CELL:;", "LST CELL:;"],
	"records": [
		{
			"ne_name": "NE-001",
			"Local Cell ID": "1",
			"Cell Name": "cell-a",
			"Cell instance state": "ACTIVE",
			"Maximum transmit power(0.1dBm)": "430",
			"Frequency band": "LTE",
			"Downlink EARFCN": "1800"
		}
	],
	"count": 1,
	"errors": [
		{"ne_name": "NE-OFFLINE", "error": "Ne is not connected."},
		{"ne_name": "NE-UNKNOWN", "error": "NE no existe o el nombre está mal escrito."}
	]
}
```

### Resumen de celdas NR

`POST /mml/cell-summary-nr` ejecuta `DSP NRCELL:;`, `LST NRDUCELL:;` y
`LST NRDUCELLTRP:;` para el lote solicitado. Los resultados se combinan por
nodo e identificador de celda. La respuesta utiliza la misma estructura
`records`, `count` y `errors` del endpoint LTE.

Los endpoints de resumen realizan una solicitud a Huawei por cada comando MML,
no una solicitud por nodo. Si Huawei rechaza un lote por un nodo desconocido,
ese comando se reintenta con los nodos restantes; los nodos desconectados
permanecen en el lote y se informan en `errors`.

### Consultar KPIs de performance

`POST /mml/kpis` consulta contadores de performance fijos (`ERAB Success
Rate`, `User Max`, `Traffic`, `Throughput`) para los eNodeB indicados, en la
ventana de 24 horas mas reciente ya publicada por Huawei. El unico dato que
se recibe es `ne_names`; el resto de los parametros de la consulta
(`counterIds`, `period`, `neTypeName`, `timeFormat`) son fijos.

```json
{
	"ne_names": ["MBTS-RM3644"]
}
```

La ventana de tiempo se calcula automaticamente en UTC (formato requerido
por Huawei), terminando en la ultima hora completa ya publicada: Huawei
demora unos 15 minutos en publicar el dato de cada hora, por lo que si aun
no transcurrieron esos 15 minutos se usa la hora anterior. Si Huawei procesa
la consulta de forma asincrona (`202 Accepted`), el backend hace polling
automatico contra Huawei hasta consolidar el resultado completo (paginando
por `marker`).

La respuesta viene aplanada (una fila por celda y hora) para poder
convertirla directamente a un DataFrame, y `startTime` se devuelve en hora
de Chile continental (no UTC), para evitar confusiones con el cambio de dia:

```json
{
	"records": [
		{
			"startTime": "2026-08-31T21:00:00",
			"neName": "MBTS-RM3644",
			"Cell Name": "L4RM3644_1",
			"Local Cell ID": "0",
			"ERAB Success Rate": "100",
			"User Max": "50",
			"Traffic": "25.2",
			"Throughput": "10"
		}
	]
}
```

### Manejo de errores

- Los nodos desconocidos se informan como `NE no existe o el nombre está mal escrito.`.
- Los nodos desconectados utilizan el mensaje de Huawei, por ejemplo
	`Ne is not connected.`.
- `records` contiene solamente datos de celdas procesados correctamente; los
	errores por nodo se listan en `errors`.
- Los errores de transporte, proxy y los errores HTTP inesperados de Huawei
	devuelven `502 Bad Gateway`.
- Los errores de validacion de Huawei que no corresponden a un nodo desconocido
	devuelven `400 Bad Request` junto con el `retMessage` de Huawei.

## Alarmas

`GET /alarms/{site_name}` requiere el token del backend en la cabecera
`Authorization` y consulta las alarmas activas (`dataType=CURRENT`) del sitio
indicado en `baseObjectInstance`. Acepta los parametros de consulta opcionales
`limit` (1-1000, por defecto 500) y `marker` (cursor de paginacion; se
reenvia el `marker` de la respuesta anterior para pedir la siguiente pagina).

```
GET /alarms/MBTS-OH8315
GET /alarms/MBTS-OH8315?limit=100&marker=<marker-de-la-respuesta-anterior>
```

La respuesta contiene una lista simplificada pensada para soporte, con
severidad/estado traducidos a texto y fechas en hora de Chile continental
(ISO 8601). `alarmClearedTime` es `null` en alarmas activas (aun no
limpiadas):

```json
{
	"site_name": "MBTS-OH8315",
	"alarms": [
		{
			"alarmId": "29841",
			"alarmName": "NR Cell Unavailable",
			"meName": "MBTS-OH8315",
			"objectInstance": "gNodeB Function Name=NOH8315, NR Cell ID=1, ...",
			"perceivedSeverity": "Mayor",
			"alarmRaisedTime": "2026-08-12T12:33:59-04:00",
			"alarmClearedTime": null,
			"cleared": "Activa",
			"ackState": "Reconocida",
			"comments": "",
			"additionalInformation": "RAT_INFO=U-L-N, AFFECTED_RAT=N"
		}
	],
	"count": 1,
	"marker": null
}
```

Las traducciones de `perceivedSeverity`, `ackState` y `cleared` siguen la
convencion estandar Huawei/ITU X.733 y no estan confirmadas contra datos
reales del MAE; si Huawei devuelve un codigo no mapeado, se conserva el
codigo original sin traducir.

## Auditoria de requests (Postgres)

Cada request a la API se registra en la tabla `api_audit_log` de Postgres. Si
`DATABASE_URL` esta vacio la auditoria queda desactivada y la API funciona igual.

### Que se registra

| Grupo | Columnas |
|---|---|
| Tiempo | `ts`, `duration_ms` |
| Origen | `client_ip`, `x_forwarded_for` |
| Request | `request_id`, `method`, `path`, `route_template`, `query_params`, `request_body`, `request_size` |
| Resultado | `status_code`, `error_type`, `error_detail`, `response_size` |
| Upstream | `upstream_service` (`huawei`/`womportal`), `upstream_status`, `upstream_duration_ms`, `upstream_calls` |
| Negocio | `ne_names`, `mml_command` |

No se guardan el token, su hash, el `User-Agent` ni un identificador de usuario:
existe un unico token y los consumidores se identifican por IP. En `request_body`
se enmascaran como `***` las claves `password`, `passwd`, `token`,
`authorization`, `hash` y `secret`. Las respuestas de Huawei no se guardan, solo
su tamaño. `error_detail` contiene el `detail` de la respuesta cuando el codigo
es 4xx/5xx.

Se omiten `/`, `/health`, `/docs`, `/openapi.json` y `/favicon.ico`
(`_EXCLUDED_PATHS` en `app/api/audit_middleware.py`). Cada respuesta incluye el
header `X-Request-ID`, igual al `request_id` guardado.

### Como funciona

- `app/api/audit_middleware.py`: middleware ASGI que captura el request y la respuesta.
- `app/services/audit.py`: cola en memoria y tarea que inserta en Postgres. La
  escritura es asincrona: si Postgres falla o la cola se llena (10 000), el
  registro se pierde y se deja un warning en el log, pero la API no se ve afectada.
  Al apagar la app se espera hasta 5 s para vaciar la cola.
- `app/db/`: capa ORM (SQLAlchemy 2.0 async + asyncpg). `models.py` define `ApiAuditLog`.
- Los hooks de httpx en `huawei_client.py` y `womportal_client.py` acumulan estado
  y duracion de las llamadas upstream de cada request.

`client_ip` es la IP de la conexion TCP. Si hay un proxy inverso delante de la
app (como en la VM), sera la IP del proxy; en ese caso usa `x_forwarded_for`
(puede ser falsificado por el cliente) o ejecuta uvicorn con `--proxy-headers
--forwarded-allow-ips=<ip-del-proxy>`.

### Base de datos por entorno

Usa una instancia/base distinta por entorno; el codigo es el mismo y solo cambia
`DATABASE_URL`:

| Entorno | Base sugerida |
|---|---|
| Desarrollo (VM dev) | `soporte_audit_dev` |
| Produccion (VM prod) | `soporte_audit` |

Crea la base y un rol dueño, conectado como administrador (PostgreSQL 15+ no
otorga `CREATE` en `public` por defecto):

```sql
CREATE ROLE audit_app LOGIN PASSWORD '...';
CREATE DATABASE soporte_audit_dev OWNER audit_app;
\c soporte_audit_dev
ALTER SCHEMA public OWNER TO audit_app;
```

Si la base ya existe, alcanza con `GRANT ALL ON SCHEMA public TO audit_app;`
ejecutado conectado a esa base. Luego define `DATABASE_URL` en el `.env`.

### Migraciones con Alembic

El esquema se versiona en `alembic/versions/`. Alembic lee `DATABASE_URL` de la
configuracion de la app. Ejecuta los comandos desde la raiz del proyecto:

```powershell
alembic upgrade head       # aplica todas las migraciones pendientes
alembic current            # version aplicada (debe mostrar 0001 (head))
alembic history            # lista de migraciones
alembic downgrade -1       # revierte la ultima migracion
```

Para cambiar el esquema:

1. Edita `app/db/models.py`.
2. Genera la migracion: `alembic revision --autogenerate -m "descripcion"`.
3. Revisa el archivo creado en `alembic/versions/` (autogenerate no detecta todo).
4. Aplica con `alembic upgrade head` en desarrollo y, despues de probar, en produccion.

Aplica siempre las migraciones antes de iniciar la version de la app que las necesita.
La tabla `alembic_version` guarda la version aplicada; no la modifiques a mano.

### Rol de solo escritura (produccion)

Para que la API no pueda modificar ni borrar registros, migra con el rol dueño
(`audit_app`) y usa otro rol en el `DATABASE_URL` de la API:

```sql
CREATE ROLE audit_writer LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE soporte_audit TO audit_writer;
GRANT USAGE ON SCHEMA public TO audit_writer;
GRANT INSERT ON api_audit_log TO audit_writer;
```

`id` es `IDENTITY`, por lo que no requiere permisos sobre secuencias.

### Consultas utiles

```sql
-- Ultimos requests
SELECT ts, client_ip, method, path, status_code, duration_ms
FROM api_audit_log ORDER BY ts DESC LIMIT 20;

-- Errores de las ultimas 24 h
SELECT ts, client_ip, path, status_code, error_detail
FROM api_audit_log
WHERE status_code >= 400 AND ts > now() - interval '24 hours'
ORDER BY ts DESC;

-- Actividad por IP
SELECT client_ip, count(*) FROM api_audit_log GROUP BY client_ip ORDER BY 2 DESC;

-- Comandos MML ejecutados sobre un nodo
SELECT ts, client_ip, mml_command FROM api_audit_log
WHERE 'NE-001' = ANY(ne_names) ORDER BY ts DESC;
```

### Retencion

La tabla crece sin limite. Define una politica de retencion, por ejemplo:

```sql
DELETE FROM api_audit_log WHERE ts < now() - interval '12 months';
```

### Pruebas

`tests/conftest.py` fuerza `DATABASE_URL` vacio para que los tests nunca escriban
en la base real. Los tests de auditoria estan en `tests/test_audit.py`.

## Despliegue en VM Ubuntu

Requiere Docker Engine y el plugin Docker Compose instalados en la VM. El despliegue asume que el proxy inverso existente corre en la misma VM.

1. Copia `.env.production.example` a `.env.production` y completa los valores reales, incluidos `PROXY_URL`, `HUAWEI_USERNAME`, `HUAWEI_PASSWORD`, `BACKEND_STATIC_TOKEN` y `WOMPORTAL_HASH`. Conserva `HUAWEI_VERIFY_SSL=false` según la autorización de producción.
2. Construye y valida la configuración, luego inicia el servicio:

	```bash
	docker compose config
	docker compose build
	docker compose up -d
	```

3. Aplica las migraciones de base de datos (ver [Migraciones con Alembic](#migraciones-con-alembic)). La imagen incluye `alembic.ini` y `alembic/`:

	```bash
	docker compose run --rm backend alembic upgrade head
	```

4. Comprueba que el contenedor esté saludable y que responda localmente:

	```bash
	docker compose ps
	curl --fail http://127.0.0.1:8000/health
	docker compose logs --tail=100 backend
	```

El puerto se publica únicamente en `127.0.0.1:8000`, para que el proxy inverso local siga atendiendo las solicitudes. Para actualizar, ejecuta `docker compose build` y `docker compose up -d`; para volver a la versión anterior, reconstruye desde el código/imagen previamente desplegados y vuelve a ejecutar `docker compose up -d`. No guardes `.env.production` ni secretos dentro de la imagen o en el repositorio.