# backend-soporte

Backend intermediario para consultas a la API de Huawei. Desarrollo en Windows, despliegue en VM Ubuntu (con proxy corporativo).

## Setup

```powershell
conda create -n backend-soporte python=3.11
conda activate backend-soporte
pip install -r requirements.txt
copy .env.example .env
```

## Run (dev)

```powershell
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs`.

## Configuration

See `.env.example` (local, no proxy) and `.env.production.example` (VM, proxy enabled). Key variables:

- `USE_PROXY` / `PROXY_URL` — enable only on the VM.
- `HUAWEI_CA_CERT_PATH` — path to the CA certificate used to validate the Huawei API's TLS chain.
- `HUAWEI_API_BASE_URL` — base URL of the Huawei API.
- `HUAWEI_USERNAME` / `HUAWEI_PASSWORD` — single technical Huawei account, kept only by the backend.
- `BACKEND_STATIC_TOKEN` — fixed token that clients send on every request.

## Authentication

Send the fixed token configured in `BACKEND_STATIC_TOKEN` as `Authorization: Bearer <token>` on every protected route. The Huawei `accessSession` and `roaRand` values never leave the backend.

This is a temporary, hardcoded-token scheme meant to be replaced by a real token issuing system later. There is no login endpoint: the token is not obtained from the backend, it's a shared secret configured out-of-band.


## MML commands

All MML endpoints require the backend token in the `Authorization` header. The
list of network elements (`ne_names`) must contain between 1 and 100 names.

### Execute a command

Send an authenticated MML command to `POST /mml/command`:

```json
{
	"command": "display version;",
	"ne_names": ["NE-001", "NE-002"]
}
```

The backend sends the command to Huawei as one batch. Each Huawei report is
parsed and includes its return code, timestamp, and records. A failed node is
kept in `results` instead of being discarded:

```json
{
	"name": "NE-OFFLINE",
	"report": {"error": "Ne is not connected."},
	"result": "Failed.",
	"retCode": -1
}
```

If Huawei rejects a complete batch because one or more node names do not
exist, the backend removes those names, retries the remaining batch, and adds
one failed result per unknown node:

```json
{
	"name": "NE-UNKNOWN",
	"report": {"error": "NE no existe o el nombre está mal escrito."},
	"result": "Failed.",
	"retCode": -1
}
```

Results are returned in the same order as the requested `ne_names`. A node
being offline or unknown does not prevent the other nodes from returning data.

### LTE cell summary

`POST /mml/cell-summary-lte` executes `DSP CELL:;` and `LST CELL:;` for the
requested batch, then joins the results by `ne_name` and `Local Cell ID`.

```json
{
	"ne_names": ["NE-001", "NE-OFFLINE", "NE-UNKNOWN"]
}
```

The response contains cell data in `records`, the number of cell records in
`count`, and node-level failures in `errors`:

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

### NR cell summary

`POST /mml/cell-summary-nr` executes `DSP NRCELL:;`, `LST NRDUCELL:;`, and
`LST NRDUCELLTRP:;` for the requested batch. The results are joined by node
and cell identifier. Its response uses the same `records`, `count`, and
`errors` structure as the LTE endpoint.

The summary endpoints perform one Huawei request per MML command, not one
request per node. If Huawei rejects a batch because of an unknown node, that
command can be retried with the remaining nodes; offline nodes remain part of
the batch and are reported in `errors`.

### Error handling

- Unknown nodes are reported as `NE no existe o el nombre está mal escrito.`.
- Offline nodes are reported using Huawei's message, for example
	`Ne is not connected.`.
- Summary `records` contains only successfully parsed cell data; node failures
	are listed in `errors`.
- Transport, proxy, and unexpected Huawei HTTP failures return `502 Bad Gateway`.
- Huawei validation failures that are not an unknown-node response return
	`400 Bad Request` with Huawei's `retMessage`.

## Deployment (Ubuntu VM)

1. Copy `.env.production.example` to `.env` and fill in real `PROXY_URL` and `HUAWEI_CA_CERT_PATH`.
2. Place the CA certificate file at the path referenced by `HUAWEI_CA_CERT_PATH`.
3. Run with `uvicorn app.main:app --host 0.0.0.0 --port 8000` (behind systemd/nginx as needed).
