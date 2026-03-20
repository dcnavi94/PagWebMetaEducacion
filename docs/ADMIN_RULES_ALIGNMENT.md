# Alineacion Tecnica de Reglas Aprobadas

Este documento traduce las reglas aprobadas en Fase 1 a decisiones tecnicas concretas para continuar la implementacion sin ambiguedad.

Su objetivo no es volver a validar negocio, sino fijar **como se implementaran hoy** las reglas ya aprobadas y donde siguen existiendo excepciones o pendientes.

## 1. Decision tecnica marco

Mientras no exista una nueva validacion administrativa que cambie el modelo, el sistema trabajara con esta estructura:

- `StudentEnrollment` = inscripcion del alumno por ciclo
- `Group` = entidad reutilizable y no amarrada fisicamente al ciclo
- `group_id` vive dentro de `StudentEnrollment`, por lo tanto cada inscripcion queda ligada a un solo grupo
- `CourseEnrollment` = carga academica del alumno en materias concretas
- `Grade` = resultado evaluativo final

## 2. Reglas ya alineadas e implementadas

### 2.1 Alumno e inscripcion

- Regla aprobada: el alumno puede existir sin ciclo activo.
  Implementacion: `User` puede existir sin `StudentEnrollment`.

- Regla aprobada: solo una inscripcion activa por alumno y por ciclo.
  Implementacion: se refuerza con validacion en backend y con la restriccion unica `student_id + cycle_id`.
  Referencia: `backend/app/main.py`, helper `_ensure_single_active_enrollment_per_cycle(...)`.

- Regla aprobada: semestre, carrera, modalidad y grupo se guardan por ciclo.
  Implementacion: esos datos viven en `StudentEnrollment`, aunque todavia existe compatibilidad temporal con campos legacy en `User`.

### 2.2 Grupos

- Regla aprobada: el grupo es una entidad propia.
  Implementacion: `Group` ya existe y tiene endpoints de alta, edicion, detalle y alumnos.

- Regla aprobada: el grupo no necesita tutor obligatorio.
  Implementacion: `tutor_id` existe, pero es opcional.

- Regla aprobada: el grupo no requiere cupo obligatorio.
  Implementacion: por ahora no se fuerza cupo maximo.

- Regla aprobada: el cambio de grupo debe guardar motivo.
  Implementacion: `StudentEnrollment.change_reason` ya se actualiza en movimientos de grupo.

### 2.3 Plan y materias

- Regla aprobada: las materias dependen de un plan de estudios formal.
  Implementacion: ya existen `StudyPlan` y `StudyPlanSubject`.

- Regla aprobada: no se manejan varias versiones activas de plan como regla normal.
  Implementacion: hoy el sistema soporta un plan funcional por carrera; no existe aun versionado historico fuerte por generacion.

### 2.4 Calificaciones

- Regla aprobada: solo se captura calificacion final.
  Implementacion: `Grade.score` representa la nota final; no hay parciales.

- Regla aprobada: el docente solo puede capturar una vez.
  Implementacion: `teacher_locked` y `recorded_at` ya lo refuerzan.

- Regla aprobada: solo admin puede corregir una calificacion cerrada.
  Implementacion: el endpoint docente bloquea una segunda captura y el admin conserva la correccion.

### 2.5 Extraordinario y recursa

- Regla aprobada: extraordinario y recursa son distintos.
  Implementacion: ambos ya tienen endpoints separados.

- Regla aprobada: recursa significa volver a cursar en ciclo posterior.
  Implementacion: el endpoint de recursa exige antecedente reprobado y crea nueva carga academica.

### 2.6 Auditoria y migracion

- Regla aprobada: la migracion debe poder validarse.
  Implementacion: ya existe auditoria en `/admin/migration-audit` para comparar legacy vs modelo nuevo.

## 3. Reglas alineadas con interpretacion tecnica provisional

Estas reglas ya tienen una interpretacion para poder seguir implementando, aunque su redaccion original admite variantes.

### 3.1 Grupo no amarrado al ciclo

- Interpretacion tecnica adoptada:
  `Group` no esta ligado fisicamente al ciclo.
  La operacion por ciclo vive en `StudentEnrollment`.

- Consecuencia:
  el mismo grupo puede reutilizarse en distintos ciclos, pero la pertenencia real del alumno siempre se consulta por `StudentEnrollment`.

### 3.2 Pagos por inscripcion del ciclo

- Interpretacion tecnica adoptada:
  el objetivo ya esta aprobado, pero aun no esta redisenado en modelo.
  Mientras tanto `Payment` sigue siendo legacy y todavia cuelga de `User`.

- Consecuencia:
  todavia falta decidir si se crea `Charge` o se refactoriza `Payment`.

### 3.3 Extraordinario con impacto en otro ciclo

- Interpretacion tecnica adoptada:
  por ahora el extraordinario se registra como oportunidad adicional sobre una asignacion concreta.
  Si una escuela necesita que el extraordinario “caiga” en otro ciclo, eso requerira una regla mas fina de reporte y corte administrativo.

## 4. Regla que sigue en conflicto y decision operativa actual

### Alumno en dos grupos activos del mismo ciclo

- Respuesta capturada en reunion: `SI`.
- Estado real del sistema: **NO soportado**.
- Decision operativa vigente para continuar:
  el sistema seguira con **una sola inscripcion activa por ciclo y un solo grupo por inscripcion**.

### Motivo de esta decision

- coincide con la estructura actual de `StudentEnrollment`
- simplifica control escolar, carga academica y reportes
- evita duplicidad de grupo, materias y pagos en la misma inscripcion

### Si administracion insiste en soportarlo

Ese cambio ya no seria ajuste menor. Requeriria como minimo:

- separar `StudentEnrollment` de una entidad adicional de pertenencia a grupos
- permitir multiples memberships activas por ciclo
- redefinir reportes de matricula, carga academica y pagos
- revisar reglas de UI y procesos administrativos

## 5. Decision tecnica recomendada para continuar

Hasta nuevo aviso, el proyecto debe continuar con estas premisas:

- una inscripcion activa por alumno y ciclo
- un solo grupo por inscripcion
- grupo reutilizable entre ciclos
- solo calificacion final
- docente captura una vez, admin corrige
- extraordinario y recursa se mantienen separados
- pagos del ciclo todavia pendientes de redisenar

## 6. Impacto en las siguientes fases

Con esta alineacion, las siguientes fases pueden avanzar asi:

- Fase 3: migracion y compatibilidad sobre `StudentEnrollment`, `Group` y `CourseEnrollment`
- Fase 4/5: frontend admin consumiendo los endpoints nuevos
- Fase 6: reglas adicionales de cargos por periodo y pruebas
- Fase 7: reportes consolidados sobre el modelo nuevo
