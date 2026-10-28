# Feature Specification: Despliegue de cambios con git pull

**Feature Branch**: `001-git-pull-deploy`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "necesito que los cambios realizados en la API se apliquen con solo hacer git pull, que no tenga que reconstruir la imagen docker para que los cambios se hagan efectivos"

## Clarifications

### Session 2026-10-28

- Q: Después de `git pull`, ¿cómo debe pasar la API a ejecutar el código nuevo? → A: Recarga automática al detectar cambios en los archivos, sin ningún comando.
- Q: Cuando un `git pull` incluye una migración de base de datos nueva, ¿cómo debe aplicarse? → A: Paso manual y documentado; la recarga automática no modifica el esquema.
- Q: Cuando cambie el archivo `.env` en el servidor, ¿la API debe aplicarlo sin intervención? → A: No; requiere reinicio manual del contenedor, documentado.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Aplicar cambios de código tras git pull (Priority: P1)

Como operador del servidor, después de traer cambios del repositorio con `git pull`, quiero que la API ejecute el código nuevo sin reconstruir la imagen del contenedor.

**Why this priority**: Es el objetivo central; elimina el paso de reconstrucción en cada actualización.

**Independent Test**: Modificar una respuesta de un endpoint, hacer `git pull` en el servidor y verificar que la API responde con el nuevo comportamiento sin ejecutar ninguna reconstrucción de imagen.

**Acceptance Scenarios**:

1. **Given** la API en ejecución con una versión del código, **When** se hace `git pull` con cambios en el código de la API, **Then** la API pasa a servir el código nuevo sin reconstruir la imagen.
2. **Given** un cambio que rompe el arranque de la API, **When** se aplica el pull, **Then** el fallo es visible para el operador (estado del servicio/logs) y no queda oculto.

---

### User Story 2 - Recarga automática sin intervención (Priority: P2)

Como operador, quiero que la API detecte por sí sola los archivos modificados por `git pull` y se recargue, sin ejecutar ningún comando adicional.

**Why this priority**: Elimina cualquier paso manual posterior al pull.

**Independent Test**: Tras `git pull`, sin ejecutar otro comando, verificar que el servicio vuelve a estar saludable en pocos segundos y sirve el código nuevo.

**Acceptance Scenarios**:

1. **Given** cambios traídos por `git pull`, **When** se modifican los archivos de la API, **Then** el servicio se recarga automáticamente, vuelve a estado saludable y sirve el código nuevo.

---

### User Story 3 - Cambios de base de datos y dependencias (Priority: P3)

Como operador, quiero saber de forma clara qué cambios sí siguen requiriendo una acción adicional (nuevas dependencias, migraciones de base de datos) para no dejar el sistema inconsistente.

**Why this priority**: Casos menos frecuentes que el cambio de código, pero que pueden romper el servicio si no se documentan.

**Independent Test**: Introducir un cambio con una migración nueva y verificar que el procedimiento documentado la aplica correctamente.

**Acceptance Scenarios**:

1. **Given** un pull que incluye una migración de base de datos, **When** se sigue el procedimiento de actualización, **Then** el esquema queda actualizado y la API funciona.
2. **Given** un pull que modifica las dependencias, **When** se sigue el procedimiento documentado, **Then** el operador sabe si necesita una acción extra y cuál.

### Edge Cases

- Cambios en la configuración de entorno (`.env`): no se recargan automáticamente; requieren reinicio manual del contenedor, documentado.
- Cambio que introduce nuevas dependencias que no existen en el entorno en ejecución.
- `git pull` con conflictos o cambios locales en el servidor.
- Pull ejecutado mientras hay solicitudes en curso.
- El código nuevo contiene un error de arranque: el servicio no debe quedar caído sin que se note.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST ejecutar el código de la API tal como está en el directorio del repositorio del servidor, de modo que `git pull` actualice lo que se ejecuta.
- **FR-002**: Los cambios de código de la API MUST NOT requerir reconstruir la imagen del contenedor para ser efectivos.
- **FR-003**: El sistema MUST recargar automáticamente la API al detectar cambios en los archivos de código, sin que el operador ejecute ningún comando.
- **FR-004**: Si el código nuevo falla al iniciar, el sistema MUST exponer el error al operador mediante logs y estado del servicio.
- **FR-009**: La recarga automática MUST NOT aplicar migraciones de base de datos; estas MUST ejecutarse como paso manual documentado cuando el pull las incluya.
- **FR-005**: El procedimiento MUST documentar qué cambios (dependencias, migraciones, configuración) siguen requiriendo una acción adicional.
- **FR-006**: El comportamiento MUST ser equivalente en entorno local de desarrollo y en el servidor de producción, sin ramas específicas por sistema operativo.
- **FR-007**: El sistema MUST seguir cumpliendo las restricciones de seguridad actuales (usuario sin privilegios, sin escritura innecesaria sobre el código ejecutado).
- **FR-008**: La configuración de proxy y certificados CA MUST seguir funcionando sin cambios.

### Key Entities

- **Código de la API**: archivos de aplicación, migraciones y configuración que cambian con cada `git pull`.
- **Entorno de ejecución**: dependencias y runtime que cambian con poca frecuencia.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tras un cambio de código, el operador lo ve activo en menos de 1 minuto desde `git pull`, sin reconstruir la imagen.
- **SC-002**: El 100% de los cambios de solo código se aplican sin reconstrucción.
- **SC-003**: El servicio vuelve a estar saludable en menos de 30 segundos tras la recarga automática.
- **SC-004**: Un operador nuevo puede completar una actualización siguiendo la documentación en un solo intento.

## Assumptions

- El servidor tiene el repositorio clonado y el operador ejecuta `git pull` en él.
- Una interrupción breve durante la recarga automática es aceptable; no se requiere cero tiempo de inactividad.
- Cambios de dependencias seguirán requiriendo una acción explícita (documentada), ya que forman parte del entorno y no del código.
- Las migraciones de base de datos se aplican manualmente como paso explícito del procedimiento de actualización.
- Los cambios en `.env` no se recargan automáticamente y requieren reinicio manual del contenedor.
