# Acta de Validacion Administrativa

Este documento resume las decisiones que administracion debe validar antes de comenzar el rediseño del panel escolar.

Su objetivo es aprobar reglas operativas, no detalles tecnicos.

## 1. Decision principal

Se propone que la base del sistema sea la **inscripcion del alumno por ciclo escolar**.

Esto significa que:

- un alumno puede existir como usuario del sistema
- pero su situacion escolar debe registrarse por ciclo
- los cambios de grupo, semestre o estatus no deben borrar el historial anterior

## 2. Decisiones que se deben aprobar

### 2.1 Alumno e inscripcion

- [ ] Confirmar si un alumno puede existir sin estar inscrito en un ciclo activo.
- [ ] Confirmar que un alumno no debe tener mas de una inscripcion activa en el mismo ciclo.
- [ ] Confirmar que el semestre debe pertenecer a la inscripcion del ciclo y no solo al alumno.
- [ ] Confirmar que carrera, modalidad y grupo deben quedar guardados por ciclo.

### 2.2 Estatus escolares

- [ ] Confirmar uso de estos estatus: `Inscrito`, `No Inscrito`, `Baja Temporal`, `Baja Definitiva`, `Graduado`.
- [ ] Confirmar que `Baja Temporal` permite reingreso posterior.
- [ ] Confirmar que `Baja Definitiva` cierra la trayectoria de ese ciclo.
- [ ] Confirmar que `Graduado` se usa solo cuando el alumno concluye su plan.

### 2.3 Grupos

- [ ] Confirmar que el grupo debe existir como entidad propia, no solo como letra o texto.
- [ ] Confirmar que cada grupo pertenece a un ciclo.
- [ ] Confirmar que cada grupo pertenece a una carrera o plan.
- [ ] Confirmar que cada grupo pertenece a una modalidad.
- [ ] Confirmar si cada grupo debe tener tutor o responsable academico.
- [ ] Confirmar si debe existir cupo maximo por grupo.

### 2.4 Cambios de grupo

- [ ] Confirmar que un alumno no puede estar en dos grupos activos del mismo ciclo.
- [ ] Confirmar que un cambio de grupo no debe borrar historial previo.
- [ ] Confirmar si se desea guardar motivo y fecha de cambio de grupo.

### 2.5 Materias y plan de estudios

- [ ] Confirmar que las materias deben depender de un plan de estudios.
- [ ] Confirmar si una carrera puede tener varias versiones de plan.
- [ ] Confirmar si generaciones distintas pueden conservar planes distintos.

### 2.6 Calificaciones

- [ ] Confirmar si el sistema debe manejar parciales.
- [ ] Confirmar si la calificacion aprobatoria base es `6`.
- [ ] Confirmar si una calificacion cerrada ya no debe poder editarse libremente.
- [ ] Confirmar quien puede reabrir o corregir una calificacion cerrada.

### 2.7 Extraordinario y recursa

- [ ] Confirmar que `Extraordinario` y `Recursa` no son lo mismo.
- [ ] Confirmar si el extraordinario ocurre dentro del mismo ciclo o al cierre del mismo.
- [ ] Confirmar que recursa significa volver a cursar la materia en un ciclo posterior.

### 2.8 Pagos y adeudos

- [ ] Confirmar que los pagos deben quedar asociados a la inscripcion del ciclo.
- [ ] Confirmar si se requiere distinguir colegiatura, reinscripcion, tramite, recargo y descuento.
- [ ] Confirmar si se desean becas o descuentos recurrentes.
- [ ] Confirmar si se desea llevar cartera vencida por ciclo.

### 2.9 Bloqueo por adeudo

- [ ] Confirmar cuantas mensualidades vencidas provocan bloqueo.
- [ ] Confirmar si el bloqueo impide inicio de sesion o solo ciertos procesos.
- [ ] Confirmar si el bloqueo afecta reinscripcion.
- [ ] Confirmar si el bloqueo afecta tramites.
- [ ] Confirmar quien puede desbloquear manualmente.

## 3. Propuesta de reglas base

Si administracion no tiene cambios mayores, se propone aprobar estas reglas iniciales:

- [ ] Un alumno puede existir sin ciclo activo, pero no operar academicamente sin inscripcion.
- [ ] Solo puede existir una inscripcion activa por alumno y por ciclo.
- [ ] Grupo, semestre, modalidad y carrera deben guardarse por ciclo.
- [ ] El grupo sera una entidad real del sistema.
- [ ] Extraordinario y recursa se manejaran como procesos distintos.
- [ ] Una calificacion cerrada no se podra editar sin permiso especial.
- [ ] Los cargos y pagos se asociaran a la inscripcion del alumno en el ciclo.
- [ ] El bloqueo por adeudo se definira por politica institucional y no por decision manual aislada.

## 4. Resultado esperado de esta validacion

Si este documento queda aprobado, el proyecto puede pasar a la Fase 2 con estas prioridades:

1. Crear `Group`.
2. Crear `StudentEnrollment`.
3. Crear migracion inicial.
4. Construir endpoints de inscripcion por ciclo.
5. Rediseñar la vista de grupos.

## 5. Espacio para acuerdos

Fecha de validacion: __________________

Responsable administrativo: __________________

Responsable tecnico: __________________

Observaciones:

__________________________________________________________________

__________________________________________________________________

__________________________________________________________________
