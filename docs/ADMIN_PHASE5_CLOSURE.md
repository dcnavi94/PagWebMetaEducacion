# Cierre Fase 5

## Estado

La Fase 5 del rediseño del panel admin queda cerrada a nivel de frontend.

## Alcance implementado

- Reordenamiento del menú del panel por dominios operativos.
- Nueva vista de `Control Escolar` centrada en `StudentEnrollment`.
- Adaptación de `Grupos` para trabajar con grupos formales y detalle por grupo.
- Reencuadre de `Oferta Académica` para separar catálogo y operación escolar.
- Nueva vista de `Calificaciones` para captura final por asignación.
- Rediseño de `Tesorería` para operar con `Charge`, bloqueos por adeudo y pagos legacy como compatibilidad temporal.

## Pantallas impactadas

- `Control Escolar`: expediente por ciclo, filtros y auditoría de migración.
- `Grupos`: resumen de grupos activos, alumnos asignados y tutores.
- `Oferta Académica`: resumen de materias, docentes y asignaciones.
- `Calificaciones`: selector de asignación y captura de calificación final.
- `Tesorería`: resumen financiero, bloqueos, cargos y pagos espejo legacy.

## Dependencias backend utilizadas

- `/admin/student-enrollments`
- `/admin/migration-audit`
- `/admin/groups`
- `/admin/groups/{group_id}`
- `/admin/groups/{group_id}/students`
- `/admin/subject-assignments`
- `/teacher/students/{assignment_id}`
- `/admin/grades/{grade_id}`
- `/admin/charges`
- `/admin/reports/finance-summary`
- `/admin/reports/blocked-students`

## Resultado

El panel administrativo ya no depende solo de vistas legacy de alumnos, materias y pagos.
La operación principal del admin ahora se apoya en los dominios nuevos de control escolar, grupos, carga académica y tesorería.
