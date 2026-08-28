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

- `USE_PROXY` / `PROXY_URL` — habilitar solamente en la VM.
- `HUAWEI_CA_CERT_PATH` — ruta al certificado CA usado para validar la cadena TLS de la API de Huawei.
- `HUAWEI_API_BASE_URL` — URL base de la API de Huawei.
- `HUAWEI_USERNAME` / `HUAWEI_PASSWORD` — cuenta tecnica de Huawei, utilizada solamente por el backend.
- `BACKEND_STATIC_TOKEN` — token fijo que los clientes envian en cada solicitud.

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

## Despliegue en VM Ubuntu

1. Copia `.env.production.example` a `.env` y completa los valores reales de `PROXY_URL` y `HUAWEI_CA_CERT_PATH`.
2. Coloca el certificado CA en la ruta indicada por `HUAWEI_CA_CERT_PATH`.
3. Ejecuta `uvicorn app.main:app --host 0.0.0.0 --port 8000` (detras de systemd/nginx si es necesario).
