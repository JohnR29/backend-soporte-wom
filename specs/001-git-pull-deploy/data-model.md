# Data Model: Despliegue de cambios con git pull

This feature does not add persistent application records or alter the HTTP API
schema. It changes how the existing service obtains code and documents the
operator-managed release inputs.

## Runtime Source

| Field | Description | Validation / invariant |
|---|---|---|
| Repository checkout | Files on the server updated by `git pull` | Must be the checkout used as the Compose project directory. |
| Application source directory | `app/` mounted to `/app/app` in the backend container | Read-only; contains the Python modules watched by Uvicorn. |
| Migration source | `alembic/` and `alembic.ini` mounted read-only at their existing paths under `/app` | Manual migration commands use migration revisions from the checked-out repository. |
| Reload scope | Application Python source beneath `/app/app` | A source change causes a process reload; configuration and migration files are outside the watch scope. |

## Dependency Image

| Field | Description | Validation / invariant |
|---|---|---|
| Runtime base | Existing Python 3.11 image and system runtime | Changes follow the existing Docker build process. |
| Installed dependencies | Packages from `requirements.txt` | A changed dependency is not installed by source reload and requires rebuilding/recreating the service image. |
| Application image | Existing backend image | Remains necessary for runtime and dependencies; application source at runtime comes from the mounted checkout. |

## Runtime Configuration

| Field | Description | Validation / invariant |
|---|---|---|
| Environment variables | Values loaded for the backend container from its configured env file | Values are fixed when the container is created; changing the file requires a container restart/recreation. |
| Proxy configuration | `USE_PROXY` and `PROXY_URL` | Remains environment-driven; no operating-system detection or hardcoded proxy behavior. |
| Huawei CA configuration | `HUAWEI_CA_CERT_PATH` and provisioned certificate | Existing path and validation behavior remain unchanged; source mounting must not shadow the certificate path. |

## Database Migration

| Field | Description | Validation / invariant |
|---|---|---|
| Alembic configuration | Read-only mounted `alembic.ini` and migration scripts from the checkout | A migration is not executed by Uvicorn reload. |
| Database schema version | Schema reached by explicit Alembic operation | Operator applies required migrations manually as described in the deployment procedure. |

## State Transitions

1. **Code-only pull**: checkout updated → mounted source changes → Uvicorn detects
   an application change → process reloads → health check returns healthy.
2. **Invalid code pull**: checkout updated → reload/startup fails → error remains
   visible in container logs and the health check does not pass.
3. **Dependency change**: checkout updated → operator rebuilds and recreates the
   image → service starts with the newly installed dependency set.
4. **Migration change**: checkout updated → operator runs the documented Alembic
   command → schema is updated; reload itself never changes the schema.
5. **Environment change**: env file updated → operator restarts/recreates the
   container → the new values are loaded by the process.
