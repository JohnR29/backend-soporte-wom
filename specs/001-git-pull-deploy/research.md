# Research: Despliegue de cambios con git pull

## Decision 1: Share the checked-out application source with the existing container

**Decision**: Add read-only bind mounts from the repository's `app/`, `alembic/`,
and `alembic.ini` to their corresponding paths in the existing Compose service.

**Rationale**: The image currently copies `app/` during build, so a host-side
`git pull` cannot change the code already copied into a running container. Docker
bind mounts expose host files to the container and are the direct mechanism for
sharing source code. Marking the mounts read-only avoids allowing the process to
modify the host checkout. Mounting only application and migration inputs avoids
exposing `.env`, `.git`, and other repository files to the API process. The
migration mount also makes revisions introduced by a pull available to the
documented manual migration command.

**Alternatives considered**:

- Rebuild the image after each pull: rejected because it directly contradicts the
  feature's primary requirement.
- Mount the whole repository: rejected because it exposes files not needed by the
  running application, including repository metadata and local environment files.
- Add another watcher or synchronization service: rejected because it duplicates
  existing Uvicorn functionality and adds container/dependency complexity.

## Decision 2: Use Uvicorn automatic reload for application Python files

**Decision**: Start the existing single-worker Uvicorn process with reload enabled
and explicitly watch `/app/app` (equivalent repository path: `app/`).

**Rationale**: Uvicorn is already the production ASGI server and the project
declares `uvicorn[standard]`, which provides its optional file-watching support.
Watching only the application source limits restarts to code changes and excludes
`.env` updates and Alembic migration files. Reload is explicitly required by the
feature, including on the Ubuntu server; the same Compose path will be used
regardless of host operating system. Local development already uses Uvicorn's
`--reload` option, so this matches its existing code-reload behavior.

**Alternatives considered**:

- Manually restart the container after each pull: rejected because the spec requires
  no post-pull command.
- Watch the entire repository: rejected because configuration, migrations, and
  unrelated files should not trigger a restart.
- Add a separate polling/watching package or process: rejected because the project
  already has the required Uvicorn extra.

## Decision 3: Keep runtime dependencies, configuration, and database schema separate from code reload

**Decision**: Treat the image as the dependency/runtime environment; retain a manual
image rebuild for dependency changes. Do not mount or reload `.env`; require a
container restart for environment changes. Do not run Alembic automatically on
reload; migrations remain an explicit, documented operator step.

**Rationale**: A source bind mount updates Python application files, not installed
packages or process environment. Automatic schema changes could be unsafe and are
explicitly excluded by the spec. The current service already includes Alembic and
uses an environment file for runtime configuration.

**Alternatives considered**:

- Reinstall dependencies at container start: rejected because it makes startup
  dependent on package availability/network and blurs the code/image boundary.
- Run migrations on every startup/reload: rejected because schema updates must
  remain an explicit manual operation.
- Watch and reload on `.env` changes: rejected because settings are read at process
  startup and the spec requires a documented manual restart.

The current Compose service reads `.env`; the production setup guide should
populate that configured file from `.env.production.example` so the documented
file and the file consumed by Compose are consistent.

## Decision 4: Preserve current runtime security and external behavior

**Decision**: Keep the existing non-root user, dropped capabilities,
`no-new-privileges`, health endpoint, port mapping, proxy environment settings, and
Huawei CA handling. Restrict changes to deployment configuration and its runbook.

**Rationale**: The feature changes how code reaches the process, not the API,
networking, authentication, or Huawei integration. A read-only source mount is
compatible with the process's need to import application modules and aligns with
the existing no-unnecessary-write constraint.

**Alternatives considered**:

- Run as root to make host file permissions easier: rejected because it weakens an
  existing security property.
- Add platform-specific watch paths or proxy behavior: rejected because behavior
  must remain environment-driven and consistent across supported hosts.

## Sources

- Repository runtime configuration: `Dockerfile`, `compose.yaml`,
  `requirements.txt`, and `app/`.
- Docker Engine documentation, [Bind mounts](https://docs.docker.com/engine/storage/bind-mounts/):
  bind mounts share host files with containers, and read-only mounts prevent
  container processes from writing through the mount.
- Uvicorn configuration is already used by the project (`uvicorn[standard]` and the
  existing local `--reload` command in `README.md`); a live documentation fetch was
  unavailable during planning.
