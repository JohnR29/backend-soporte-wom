# AGENTS.md

Backend intermediario (proxy funcional) hacia la API de Huawei. FastAPI, desplegado en VM Ubuntu; desarrollado en Windows.

## Architecture

- `app/main.py` — FastAPI app + lifespan (closes the shared HTTP client on shutdown).
- `app/core/config.py` — `Settings` (pydantic-settings), loaded from `.env`. All env-driven behavior goes through here, never `os.environ` directly.
- `app/services/huawei_client.py` — **the only place** proxy and CA certificate logic lives. All calls to the Huawei API must go through `get_client()` here, not a new `httpx`/`requests` client elsewhere.
- `app/api/routes/` — FastAPI routers; one file per Huawei API area.

## Critical convention: proxy is environment-driven, not OS-detected

- Local Windows dev: `.env` has `USE_PROXY=false` (see `.env.example`).
- Ubuntu VM: `.env` has `USE_PROXY=true` + `PROXY_URL=...` (see `.env.production.example`).
- Never branch on `platform.system()` or hardcode proxy behavior — always gate through `settings.use_proxy`/`settings.proxy_url` so both environments run the same code path.

## Critical convention: CA certificate

- `HUAWEI_CA_CERT_PATH` env var points to a `.pem`/`.crt` file, passed as `verify=` to the httpx client in `huawei_client.py`.
- Missing/invalid path raises `RuntimeError` at first request (fail loud, not a generic TLS error).
- Certs live under `certs/` locally (gitignored); on the VM the path is set to wherever the cert is provisioned (see `.env.production.example`).

## Run / build

```powershell
conda activate backend-soporte
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

See [README.md](README.md) for full setup and deployment steps.

## Adding a new Huawei endpoint

1. Add the route in `app/api/routes/` using `get_client()` from `huawei_client.py`.
2. Register the router in `app/main.py` if it's a new file.
3. Do not construct new `httpx`/`requests` clients — reuse the shared one so proxy/CA settings stay consistent.

For auth flow, endpoint shapes, pagination, error codes, and rate limits of the Huawei MAE-Access API itself, see the [huawei-api skill](.github/skills/huawei-api/SKILL.md).
