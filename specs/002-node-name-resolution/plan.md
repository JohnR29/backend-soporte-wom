# Implementation Plan: Resolución de nombres de nodo a partir del sitio

**Branch**: `002-node-name-resolution` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

**Input**: `/specs/002-node-name-resolution/spec.md`

## Summary

Resolver cada valor recibido en las consultas MML contra el directorio externo de sitios: `sitio` a `nodo` para 4G/5G y `sitio` a `nodeb` para 3G. Mantener intactos los campos de entrada y las llamadas a Huawei existentes, agregar metadatos de resolución por elemento y sugerencias de hasta cinco sitios cuando una entrada no exista, ordenadas por porcentaje de similitud descendente y con desempate alfabético. El acceso al directorio será de solo lectura, PostgreSQL, separado de la conexión opcional de auditoría.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, asyncpg; `difflib` de la biblioteca estándar para sugerencias

**Storage**: Tabla de sitios existente y administrada externamente en PostgreSQL; sin migración ni escrituras. PostgreSQL de auditoría sigue siendo opcional e independiente.

**Testing**: pytest con servicios de directorio y llamadas Huawei simulados; prueba de integración opcional contra una tabla de sitios de prueba.

**Target Platform**: Servicio FastAPI en contenedor Docker sobre Ubuntu; desarrollo Windows.

**Project Type**: Servicio web backend.

**Performance Goals**: El p95 del tiempo añadido por la etapa de resolución será <0,5 s (sin incluir Huawei) en cada escenario: búsqueda exacta y búsqueda fallida con sugerencias, tanto en solicitudes escalares como en lotes de hasta 100 nombres. Medir al menos 30 repeticiones por escenario sobre una copia representativa del directorio; registrar el número de filas y el entorno. Consultar por lote y calcular sugerencias solo tras fallos exactos.

**Constraints**: Ninguna escritura ni migración en el directorio externo. Usar `SITE_DIRECTORY_DATABASE_URL` con un usuario de solo lectura limitado a `public.cellreference`, independiente de `DATABASE_URL` (auditoría). La tabla existente contiene `sitio`, `nodo`, `enodeb`, `nodeb` y `gnodeb`, todos `varchar(50) NULL`; `sitio` es único según la fuente de datos. No agregar dependencias.

**Scale/Scope**: Cinco endpoints MML; lotes de hasta 100 nombres en cuatro de ellos y un nombre en la consulta UMTS. Sin cambios en alarmas, tickets ni scripts MML cargados como archivos.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / constraint | Result | Rationale |
|---|---|---|
| I. Arquitectura Conservadora | PASS | Añade un servicio pequeño en `app/services/` y configuración/lifecycle usando la estructura FastAPI existente; no crea servicios ni contenedores. |
| II. Simplicidad | PASS | Consulta por lote, coincidencia normalizada y `difflib`; no introduce ORM/modelo de escritura, caché ni patrón de repositorio adicional. |
| III. Dependencias y Contenedor Livianos | PASS | Reutiliza SQLAlchemy/asyncpg existentes y biblioteca estándar; no añade paquetes. |
| Additional Constraints | PASS | `public.cellreference` permanece externa e inmutable; se usa credencial PostgreSQL de solo lectura independiente de auditoría. |
| Development Workflow | PASS | Quickstart contempla pruebas focalizadas y validación de integración con una relación real de prueba. |

No se detectan violaciones constitucionales ni aclaraciones de diseño pendientes. La ubicación y relación están confirmadas; el despliegue proporciona `SITE_DIRECTORY_DATABASE_URL` y `DATABASE_URL` sigue reservado para auditoría.

## Project Structure

### Documentation (this feature)

```text
specs/002-node-name-resolution/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── node-resolution.md
└── tasks.md              # Phase 2; tareas generadas con /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── api/
│   ├── audit_middleware.py
│   └── routes/
│       └── huawei.py
├── core/
│   └── config.py
├── services/
│   └── node_resolution.py  # nuevo servicio de lectura y normalización
└── main.py                 # inicialización/cierre del servicio
tests/
├── test_huawei_route.py
└── test_node_resolution.py # pruebas focalizadas del resolver
```

**Structure Decision**: Mantener el servicio FastAPI único y añadir el resolver en `app/services/`; los endpoints MML lo invocan antes de las llamadas Huawei. El engine de lectura se configura con `SITE_DIRECTORY_DATABASE_URL` y tiene lifecycle propio, independiente de la conexión opcional de auditoría `DATABASE_URL`. Se consulta `public.cellreference`; no se agrega tabla propia ni migración Alembic.

## Phase 0: Outline & Research

Las decisiones, alternativas y evidencia del repositorio están en [research.md](./research.md). Se identificaron las rutas, la conexión independiente de solo lectura y la relación `public.cellreference`; no quedan decisiones de configuración de base de datos pendientes.

## Phase 1: Design & Contracts

- [data-model.md](./data-model.md) define el registro externo, el resultado efímero de resolución y el uso de los campos de auditoría existentes.
- [contracts/node-resolution.md](./contracts/node-resolution.md) describe rutas afectadas, compatibilidad de solicitudes, metadatos aditivos y errores.
- [quickstart.md](./quickstart.md) define pruebas focalizadas y un escenario de integración contra una tabla de prueba.

### Post-design Constitution Check

| Principle / constraint | Result | Rationale |
|---|---|---|
| I. Arquitectura Conservadora | PASS | Un servicio interno nuevo y wiring en lifecycle/rutas existentes; sin reestructuración. |
| II. Simplicidad | PASS | No se agrega caché, dependencia ni migración; la búsqueda se hace por lote y las sugerencias solo al fallar. |
| III. Dependencias y Contenedor Livianos | PASS | Se reutiliza el stack PostgreSQL ya instalado. |
| Additional Constraints | PASS | Credencial separada de solo lectura; no se modifica ni administra el directorio externo. |
| Development Workflow | PASS | Los escenarios del quickstart cubren compatibilidad, errores parciales y medición de latencia. |

No hay fallos de gate. El despliegue ya tiene provisionada y confirmada `SITE_DIRECTORY_DATABASE_URL` para acceder a `public.cellreference`; no se requiere configuración adicional en la aplicación.

## Complexity Tracking

No hay violaciones constitucionales; no se requiere excepción de complejidad.