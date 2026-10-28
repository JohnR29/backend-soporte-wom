# Quickstart: Validar el despliegue con git pull

## Requisitos

- Docker Engine and the Docker Compose plugin on the Ubuntu VM (or Docker Desktop
  for local container validation).
- The repository checkout and a configured runtime `.env` file (the file consumed
  by the current Compose service). On a new server, use
  `.env.production.example` as the source for `.env` and provide real values
  outside version control.
- Any required Huawei CA certificate provisioned at the path configured in the
  environment.

## Initial startup

From the repository root:

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
docker compose logs --tail=100 backend
```

Expected: Compose configuration succeeds, the backend becomes healthy, and the
health endpoint returns success. The image build is needed for initial setup and
runtime dependencies, not for code-only pulls.

## Validate automatic reload after a code-only pull

1. Record the current image ID and verify the service is healthy:

   ```bash
   docker compose images backend
   docker compose ps
   ```

2. Bring a code-only commit into the checked-out repository:

   ```bash
   git pull
   ```

3. Do not run `docker compose build`, `docker compose restart`, or any other
   follow-up command. Check service logs and health:

   ```bash
   docker compose logs --since=2m backend
   docker compose ps
   curl --fail http://127.0.0.1:8000/health
   ```

Expected: Uvicorn logs its reload, the service returns to healthy within 30 seconds,
and the updated endpoint behavior is active within 60 seconds. The image ID remains
unchanged.

## Validate failure visibility

In a disposable test checkout, introduce a deliberate syntax/startup error under
`app/` and observe the container:

```bash
docker compose logs --since=2m backend
docker compose ps
curl --fail --max-time 5 http://127.0.0.1:8000/health
```

Expected: logs expose the startup error and the health check/request does not
report a healthy API. Revert the test-only error and confirm Uvicorn reloads and
health returns. Do not run this test against a production checkout.

## Changes that still need action

- **Dependencies**: rebuild the image and recreate the backend service after a pull
  that changes `requirements.txt` or the runtime base.
- **Database migration**: run the release's documented Alembic migration manually;
  for the current migration mechanism, the command is:

  ```bash
  docker compose run --rm backend alembic upgrade head
  ```

  Follow any release-specific ordering or backup instructions. Reload does not
  apply migrations.
- **Environment**: after changing `.env`, restart/recreate the backend container
  so the process reads the new values. The application source watcher does not
  reload settings from `.env`.
- **Pull conflicts**: resolve merge conflicts and inspect local changes before
  relying on the checkout as the running source.

## Automated regression checks

Run the focused Python tests and validate the resolved Compose configuration:

```bash
pytest
docker compose config
```

Expected: tests pass and Compose configuration is valid. For the container-level
reload scenario, use the manual steps above because it depends on an actual Docker
daemon and host bind-mount notifications.
