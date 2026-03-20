# Fase 2 - Cierre del Nuevo Modelo Base

Este documento marca el cierre de la Fase 2 del rediseño del panel admin escolar.

La meta de esta fase fue dejar listo el modelo base sobre el que ya puede construirse migracion, compatibilidad, frontend y reglas operativas.

## 1. Objetivo alcanzado

El sistema ya no depende solo de `User` y `Grade` para representar operacion escolar.

La base actual queda organizada asi:

- `Group` = grupo real reutilizable
- `StudentEnrollment` = expediente del alumno por ciclo
- `StudyPlan` = plan de estudios
- `StudyPlanSubject` = materias incluidas en el plan
- `CourseEnrollment` = carga academica del alumno en materias concretas
- `Grade` = resultado evaluativo final de una carga academica

## 2. Decisiones tecnicas de Fase 2

### 2.1 Grupo

- `Group` ya existe como entidad propia.
- Puede tener modalidad y tutor opcional.
- El grupo no queda amarrado fisicamente al ciclo; la pertenencia real del alumno se resuelve por `StudentEnrollment`.

### 2.2 Inscripcion escolar

- `StudentEnrollment` concentra carrera, modalidad, semestre, grupo y estatus por ciclo.
- La regla vigente es una sola inscripcion activa por alumno y por ciclo.

### 2.3 Oferta academica

- `StudyPlan` y `StudyPlanSubject` ya permiten organizar materias por plan formal.
- Esto separa el catalogo academico de la operacion diaria.

### 2.4 Carga academica

- `CourseEnrollment` representa que el alumno cursa una asignacion concreta.
- La carga academica ya no depende de `Grade` para existir.

### 2.5 Calificacion

- `Grade` queda definido como resultado evaluativo final.
- `Grade` ya no es la pieza principal de inscripcion academica.
- `Grade` se relaciona con `CourseEnrollment` mediante `course_enrollment_id`.
- `teacher_locked` y `recorded_at` refuerzan la regla de captura unica docente y correccion solo por admin.

## 3. Resultado operativo

Con esta fase cerrada, el sistema ya cuenta con un modelo base suficientemente claro para:

- migrar datos legacy hacia inscripciones por ciclo
- consumir grupos reales desde frontend
- operar carga academica separada de calificaciones
- construir reportes sobre entidades mas estables

## 4. Pendientes que ya no pertenecen a Fase 2

Lo siguiente se considera trabajo posterior:

- backfill completo desde `User` hacia `StudentEnrollment`
- conversion masiva de grupos legacy en texto
- compatibilidad temporal de todo el frontend admin
- rediseño de finanzas por inscripcion/cargos
- limpieza final del puente legacy

## 5. Criterio de cierre

Fase 2 se considera terminada porque:

- todas las entidades base ya existen
- las migraciones base ya existen
- la carga academica ya se separo de la calificacion
- `Grade` ya funciona como resultado evaluativo final
