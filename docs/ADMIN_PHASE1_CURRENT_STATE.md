# Fase 1 - Estado Actual del Panel Admin

Este documento describe como funciona hoy el panel administrativo con base en el codigo actual del frontend y backend.

Su objetivo es servir como fotografia operativa antes del rediseño.

## 1. Resumen ejecutivo

El panel actual ya cubre operaciones reales de administracion escolar:

- alta y edicion de alumnos
- alta y edicion de docentes
- catalogo de materias
- asignacion de docentes a materias por ciclo
- gestion por grupos
- captura y edicion de calificaciones
- generacion de pagos por ciclo
- tramites escolares

Sin embargo, la operacion todavia depende fuertemente de:

- campos sueltos en `User`
- texto libre para `grupo`
- `Grade` como mezcla de inscripcion y calificacion
- `Payment` basado en `concept`

## 2. Entidades actuales y su papel

### 2.1 `User`

Hoy `User` concentra tanto identidad del usuario como estado escolar actual.

Campos operativos principales:

- `username`
- `role`
- `user_status`
- `enrollment_status`
- `career_id` y `carrera`
- `modality_id` y `modalidad`
- `semestre`
- `grupo`

Conclusion:

- `User` funciona al mismo tiempo como cuenta, expediente actual y ficha administrativa.

### 2.2 `Subject`

Representa una materia catalogo.

Campos relevantes:

- `name`
- `credits`
- `semester`
- `career`

Conclusion:

- la materia esta ligada a carrera por texto, no a un plan de estudios versionado

### 2.3 `SubjectAssignment`

Representa una asignacion docente para una materia dentro de un ciclo escolar.

Campos relevantes:

- `subject_id`
- `teacher_id`
- `cycle_id`

Conclusion:

- es la entidad mas cercana a una oferta academica real
- aun no distingue grupo o seccion de manera formal

### 2.4 `Grade`

Hoy `Grade` mezcla tres funciones:

- inscripcion del alumno a una materia
- vinculo con docente/ciclo cuando existe `assignment_id`
- resultado academico final

Campos relevantes:

- `student_id`
- `subject_id`
- `assignment_id`
- `attempt_type`
- `score`
- `status`

Conclusion:

- `Grade` esta haciendo demasiado trabajo y eso complica historial, recursas y cambios de grupo

### 2.5 `Payment`

Representa cargos o pagos por alumno.

Campos relevantes:

- `student_id`
- `concept`
- `amount`
- `due_date`
- `status`

Conclusion:

- el sistema depende del texto de `concept` para interpretar el cargo
- eso vuelve fragiles la cartera y los reportes

### 2.6 `SchoolCycle` y `CycleTuition`

`SchoolCycle` guarda el ciclo activo y `CycleTuition` guarda costos por carrera y modalidad.

Conclusion:

- esta parte ya tiene una buena base para evolucionar
- falta enlazar el ciclo con la inscripcion formal del alumno

## 3. Flujo actual de alumnos

### 3.1 Alta de alumno

Flujo backend actual:

1. Se valida que la matricula no exista.
2. Se busca o crea carrera.
3. Se busca o crea modalidad.
4. Se crea `User` con rol `student`.
5. Se guardan dentro del usuario:
   - carrera
   - modalidad
   - semestre
   - grupo
6. Se ejecuta `_assign_curriculum_to_student(...)`.
7. El sistema crea registros en `Grade` para materias de la carrera.

Implicacion:

- desde el alta del alumno se precargan materias en `Grade`
- no existe una inscripcion por ciclo separada del usuario

### 3.2 Edicion de alumno

Actualmente se puede editar:

- nombre
- email
- password
- `user_status`
- `enrollment_status`
- carrera
- modalidad
- semestre
- grupo

Si cambia la carrera, se vuelven a asignar materias.

Implicacion:

- el estado escolar se sobrescribe en el mismo `User`
- no hay historial por ciclo ni por cambio de grupo

### 3.3 Perfil completo del alumno

La vista detalle del alumno junta:

- datos personales
- carrera
- modalidad
- semestre
- grupo
- calificaciones
- pagos
- tramites

Implicacion:

- el expediente actual se arma desde relaciones directas del usuario
- no existe vista por ciclo

## 4. Flujo actual de grupos

### 4.1 Como se construyen los grupos

Hoy no existe una tabla `Group`.

Los grupos se obtienen agrupando alumnos por:

- `User.grupo`
- `User.carrera`

Implicacion:

- el grupo es solo un texto dentro del usuario
- no tiene ciclo, cupo, tutor, modalidad, turno ni identidad propia

### 4.2 Operacion por grupo

Desde el panel se puede:

- listar grupos
- ver alumnos filtrados por grupo y carrera
- cambiar `enrollment_status` en bloque
- asignar una materia a todo el grupo

Implicacion:

- el grupo sirve como filtro operativo, no como entidad administrativa

## 5. Flujo actual de materias y asignaciones

### 5.1 Materias

Las materias se crean como catalogo simple con:

- nombre
- carrera
- semestre
- creditos

### 5.2 Asignacion de docente

Una asignacion une:

- materia
- docente
- ciclo

Reglas actuales:

- no se puede duplicar la misma combinacion `subject + teacher + cycle`
- cuando se crea una asignacion, se autovinculan `Grade` sin docente para esa materia

Implicacion:

- el sistema ya entiende que la materia ofrecida depende del ciclo
- pero no diferencia grupos o secciones reales

## 6. Flujo actual de calificaciones

### 6.1 Como nacen las calificaciones

Las calificaciones nacen por dos caminos:

1. al crear alumno y asignar curriculum
2. al inscribir manualmente a un alumno o grupo en una asignacion

### 6.2 Inscripcion manual a materia

Al inscribir un alumno a una asignacion:

- si ya existe `Grade` para la misma asignacion, se rechaza
- si existe `Grade` para la misma materia, se reasigna al nuevo docente
- si no existe, se crea un `Grade` nuevo

Implicacion:

- el sistema usa `Grade` como si fuera inscripcion academica

### 6.3 Captura de calificacion

La calificacion puede editarse por admin o docente.

Regla actual:

- si se captura `score >= 6`, el estatus pasa a `Aprobada`
- si se captura `score < 6`, el estatus pasa a `Reprobada`
- tambien se puede cambiar estatus manualmente

Implicacion:

- no hay cierre de acta
- no hay parciales
- no hay control formal de extraordinario aparte de `attempt_type`

## 7. Flujo actual de pagos

### 7.1 Configuracion de ciclo

Desde configuracion se puede:

- guardar periodo
- guardar fecha de inicio y fin
- guardar colegiaturas por carrera y modalidad

### 7.2 Generacion automatica

El sistema genera pagos mensuales:

- toma el ciclo activo
- recorre meses entre inicio y fin
- genera fecha limite por mes
- busca alumnos con `enrollment_status = Inscrito`
- usa costo por carrera/modalidad o fallback del ciclo
- crea `Payment` con `concept = Colegiatura <mes>`

Implicacion:

- el pago esta ligado al alumno, no a una inscripcion por ciclo
- el sistema depende del `concept` para identificar el cargo

### 7.3 Operacion financiera actual

Actualmente se puede:

- listar pagos
- crear cargos manuales
- editar estatus de pago

No existe hoy:

- relacion formal con inscripcion
- descuento o beca estructurada
- recargos
- conciliacion
- cartera por cohorte o grupo

## 8. Flujo actual de tramites

El modulo de tramites permite:

- crear tramite para alumno
- actualizar estatus
- listar tramites

Estatus actuales:

- En Proceso
- Listo
- Entregado

Conclusion:

- este modulo ya esta relativamente separado del resto

## 9. Hallazgos principales

### 9.1 Fortalezas actuales

- ya existe separacion entre catalogo de materia y asignacion docente
- ya existe ciclo escolar activo
- ya existe generacion automatica de pagos
- ya existe gestion por roles
- ya existe panel admin con secciones funcionales

### 9.2 Debilidades estructurales

- no existe inscripcion del alumno por ciclo
- no existe grupo como entidad real
- no existe plan de estudios versionado
- `Grade` mezcla inscripcion y resultado academico
- `User` concentra demasiado estado operativo
- `Payment` no tiene una capa formal de cargos

## 10. Campos legacy candidatos

Estos campos deben considerarse candidatos a legacy en el rediseño:

### 10.1 En `User`

- `carrera`
- `career_id` como estado operativo unico
- `modalidad`
- `modality_id` como estado operativo unico
- `semestre`
- `grupo`
- `enrollment_status` como unica fuente de estado escolar

### 10.2 En `Grade`

- uso de `Grade` como inscripcion academica
- uso de `assignment_id` como sustituto de carga academica

### 10.3 En `Payment`

- interpretacion del cargo via `concept`
- asociacion directa solo a `student_id`

## 11. Recomendacion para la siguiente fase

El siguiente paso correcto es crear primero:

- `Group`
- `StudentEnrollment`

Eso permite resolver el mayor problema actual:

- el sistema no tiene una entidad que represente la situacion administrativa del alumno en un ciclo especifico
