# Limpieza del puente legacy

## Estado actual

Se retiró el uso operativo directo de `User.grupo` y `User.carrera` en procesos masivos de grupos.

## Ajustes realizados

- `GET /admin/groups` ya construye el resumen desde `Group` + `StudentEnrollment`.
- `PUT /admin/groups/bulk-enrollment` ya opera sobre membresías reales del grupo en el ciclo activo.
- `POST /admin/groups/bulk-assign` ya toma sus alumnos desde `StudentEnrollment`, no desde `User.grupo`.
- La vista de alumnos en `admin.html` ya prioriza la inscripción activa del ciclo para carrera, modalidad, semestre y grupo.

## Qué permanece

Los campos:

- `User.grupo`
- `User.semestre`
- `User.carrera`
- `User.modalidad`

siguen existiendo como espejo de compatibilidad y sincronización temporal.

## Regla de desarrollo

Toda lógica nueva de operación escolar debe leer desde:

- `StudentEnrollment`
- `Group`
- `CourseEnrollment`
- `Charge`

No debe abrir nuevas dependencias funcionales sobre los campos legacy de `User`.
