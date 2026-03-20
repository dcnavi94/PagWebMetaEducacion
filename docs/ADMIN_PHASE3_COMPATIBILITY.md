# Fase 3 - Compatibilidad Temporal

Este documento describe como conviven temporalmente el frontend admin actual y el nuevo modelo escolar mientras termina la migracion.

## 1. Objetivo

Permitir que la operacion siga funcionando aunque parte del frontend todavia use campos legacy en `User` y parte del backend ya opere con `StudentEnrollment`, `Group` y `CourseEnrollment`.

## 2. Estrategia aplicada

La compatibilidad temporal se sostiene con estas reglas:

- `User.carrera`, `User.modalidad`, `User.semestre` y `User.grupo` siguen existiendo como puente temporal.
- los movimientos operativos importantes ya sincronizan hacia `StudentEnrollment`
- los listados de cursos, grupos e historial ya priorizan el modelo nuevo y solo hacen fallback a datos legacy cuando falta enlace

## 3. Endpoints puente que ya sostienen esta convivencia

- `GET /admin/groups`
- `PUT /admin/student-enrollments/move-group`
- `PUT /admin/groups/bulk-enrollment`
- `POST /admin/groups/bulk-assign`
- `GET /users/me/courses`
- `GET /users/me/academic-history`
- `GET /teacher/students/{assignment_id}`

## 4. Compatibilidad actual del frontend admin

Hoy el frontend sigue pudiendo operar porque:

- la vista de grupos ya usa `GET /admin/groups` y `PUT /admin/student-enrollments/move-group`
- la ficha general de alumnos sigue leyendo propiedades legacy como `grupo`, `semestre`, `carrera` y `modalidad`
- el backend mantiene sincronizados esos campos mientras conviven ambos modelos

## 5. Script de backfill recomendado

Para reconciliar datos legacy con el modelo nuevo se agrega:

```bash
cd backend
python -m app.backfill_school_data --apply
```

Opciones utiles:

```bash
python -m app.backfill_school_data
python -m app.backfill_school_data --only-missing
python -m app.backfill_school_data --cycle-id 1 --apply
```

Sin `--apply`, el comando corre en modo dry-run y solo devuelve resumen.

## 6. Criterio para retirar compatibilidad legacy

La compatibilidad temporal podra retirarse cuando:

- el frontend admin ya trabaje principalmente con `StudentEnrollment`, `Group` y `CourseEnrollment`
- tesoreria deje de depender de relaciones directas solo con `User`
- las vistas de alumno ya no necesiten `User.grupo`, `User.semestre`, `User.carrera` y `User.modalidad` como fuente operativa
