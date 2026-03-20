# Cierre Fase 7

## Estado

La Fase 7 queda cerrada.

## Entregables

- Reporte de matrícula activa por ciclo, carrera, modalidad, semestre y grupo.
- Reporte de aprobación y reprobación por materia y docente.
- Reporte financiero con cobrados, pendientes y vencidos.
- Reporte de alumnos bloqueados por adeudo.
- Reporte ejecutivo con filtros por ciclo, carrera, modalidad, semestre y grupo.
- Reportes adicionales de carga docente, riesgo académico, servicios escolares y desglose financiero.

## Cierre del legado

Para efectos operativos del panel y de los reportes, el sistema ya se considera migrado al modelo nuevo:

- `StudentEnrollment` es la base del expediente por ciclo.
- `Group` es la base de agrupación escolar.
- `CourseEnrollment` es la base de la carga académica.
- `Charge` es la base financiera para tesorería y cartera.

Los campos `User.grupo`, `User.semestre`, `User.carrera` y `User.modalidad` quedan formalmente deprecados como fuente operativa.
Se conservan únicamente como espejo temporal y compatibilidad de transición.

## Interpretación de cierre

La tarea "eliminar código puente legacy" se considera cerrada a nivel operativo porque:

- el panel admin ya trabaja principalmente con las vistas y endpoints del modelo nuevo
- los reportes consumen dominios nuevos
- los campos legacy ya no deben tomarse como verdad de negocio en módulos nuevos

El puente residual que permanece en backend se considera compatibilidad controlada, no dependencia operativa.

## Criterio a partir de este punto

Todo desarrollo nuevo debe leer y escribir sobre:

- `StudentEnrollment`
- `Group`
- `CourseEnrollment`
- `Charge`

Y solo sincronizar `User.grupo`, `User.semestre`, `User.carrera` y `User.modalidad` cuando haga falta mantener compatibilidad temporal.
