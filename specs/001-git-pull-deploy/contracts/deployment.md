# Deployment Contract

## Scope

This contract covers the operator-facing runtime behavior of the existing
`backend` service in `compose.yaml`. Public HTTP endpoints and response schemas do
not change.

## Runtime source and reload

- The Compose project is run from the checked-out repository directory.
- The repository's `app/` directory is mounted read-only at `/app/app` in the
  backend container.
- The repository's `alembic/` directory and `alembic.ini` are mounted read-only at
  their existing paths so explicit migration commands use revisions from the
  checkout.
- Uvicorn watches the application source directory and reloads when application
  Python files change. A code-only `git pull` does not require an image rebuild or
  a separate restart command.
- A failed reload/startup must remain observable through `docker compose logs
  backend` and a failing health check; the deployment must not report the service
  healthy until `/health` responds successfully.
- Existing container identity and hardening are retained: UID 10001,
  `no-new-privileges`, and all Linux capabilities dropped.
- The health-check interval is 5 seconds with 3 retries so recovery is observed
  within the 30-second service-health objective.

## Changes requiring operator action

| Change in pull | Required action |
|---|---|
| Application code under `app/` only | No action beyond `git pull`; reload is automatic. |
| `requirements.txt` or runtime/base-image dependency | Rebuild and recreate the backend image/service. |
| Alembic migration or schema change | Run the documented migration manually; reload never applies it. |
| `.env` or deployment environment values | Restart/recreate the container to load the new values. |
| Git conflict or local server changes | Resolve the checkout conflict before expecting a complete/reliable update. |

## Preserved behavior

- Proxy configuration remains controlled by `USE_PROXY` and `PROXY_URL`.
- Huawei CA certificate configuration and its existing fail-loud validation remain
  unchanged.
- Existing API routes, authentication, port publishing, and database behavior
  remain unchanged except for explicit manual migration operations.
