<!--
Sync Impact Report
- Version change: unversioned scaffold -> 1.0.0 (initial constitution)
- Modified principles: scaffold principles 1-3 -> I. Arquitectura Conservadora; II. Simplicidad; III. Dependencias y Contenedor Livianos
- Added sections: Additional Constraints; Development Workflow
- Removed sections: none
- Follow-up TODO: confirm the original ratification date
-->
# Backend Soporte Constitution

## Core Principles

### I. Arquitectura Conservadora
El backend DEBE conservar su arquitectura sencilla y contenerizada con Docker, así como la
estructura existente de archivos y contenedores. Los cambios estructurales DEBEN ser incrementales;
crear servicios, contenedores o capas nuevas, o reorganizar ampliamente el proyecto, requiere una
necesidad concreta y aprobación explícita.

### II. Simplicidad
Las soluciones DEBEN ser directas y minimalistas. No se DEBEN introducir patrones de diseño,
abstracciones o mecanismos adicionales si una solución más simple satisface los requisitos; toda
complejidad adicional DEBE responder a una necesidad técnica concreta.

### III. Dependencias y Contenedor Livianos
El contenedor DEBE incluir únicamente dependencias y componentes necesarios para ejecutar el
backend. Cada dependencia nueva DEBE justificarse por un requisito concreto y no debe duplicar
capacidades ya disponibles en el proyecto; los cambios no deben aumentar innecesariamente el tamaño
de la imagen.

## Additional Constraints

La estructura actual del proyecto y la configuración de Docker son la referencia para todo cambio.
Una modificación que altere de forma sustancial archivos, servicios o contenedores DEBE explicar
por qué es necesaria y obtener aprobación antes de implementarse.

## Development Workflow

Las revisiones DEBEN comprobar el cumplimiento de estos principios. Antes de incorporar una
dependencia, se DEBE evaluar si las capacidades existentes bastan. Los cambios que afecten el
contenedor DEBEN validar que este pueda construirse; los cambios de comportamiento DEBEN ejecutar
las pruebas focalizadas disponibles.

## Governance
Esta constitución prevalece sobre prácticas incompatibles del proyecto. Las enmiendas requieren
documentar el motivo, revisar su impacto sobre los principios y aprobar el cambio. La versión sigue
SemVer: MAJOR para cambios incompatibles en principios o gobernanza; MINOR para principios o
secciones nuevas o materialmente ampliadas; PATCH para aclaraciones sin cambio de sentido. En cada
revisión de código se DEBE evaluar el cumplimiento y justificar cualquier excepción antes de
aprobarla.

**Version**: 1.0.0