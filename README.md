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

Send authenticated MML commands to `POST /mml/command`:

```json
{
	"command": "display version;",
	"ne_names": ["NE-001"]
}
```

Each Huawei report includes a parsed result with its detected format, metadata, return code, timestamp, and records.

## Deployment (Ubuntu VM)

1. Copy `.env.production.example` to `.env` and fill in real `PROXY_URL` and `HUAWEI_CA_CERT_PATH`.
2. Place the CA certificate file at the path referenced by `HUAWEI_CA_CERT_PATH`.
3. Run with `uvicorn app.main:app --host 0.0.0.0 --port 8000` (behind systemd/nginx as needed).
