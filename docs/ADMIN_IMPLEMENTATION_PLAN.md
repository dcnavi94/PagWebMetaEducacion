# Plan de Implementacion del Panel de Administracion Escolar

Este documento convierte el rediseño propuesto en una **lista de tareas ejecutables** para implementar un panel administrativo escolar mas ordenado, escalable y facil de operar.

Modelo objetivo:

`Ciclo escolar -> Inscripcion del alumno -> Grupo -> Carga academica -> Calificaciones -> Finanzas`

## 1. Objetivo del proyecto

Al finalizar esta implementacion, el sistema debe permitir:

- administrar alumnos por ciclo sin perder historial
- operar grupos reales como entidad administrativa
- separar inscripcion academica de calificacion final
- controlar pagos y cargos por periodo
- ordenar el panel por procesos escolares y no por tablas aisladas

## 2. Prioridad inmediata

Estas son las primeras tareas que conviene ejecutar antes que cualquier otra:

- [ ] Validar con administracion las reglas base de inscripcion, cambio de grupo, baja, recursa y bloqueo por adeudo.
- [ ] Definir el modelo nuevo minimo para arrancar: `Group` y `StudentEnrollment`.
- [ ] Crear migracion Alembic inicial para esas entidades.
- [ ] Crear endpoints backend para listar inscripciones por ciclo y mover alumnos entre grupos.
- [ ] Adaptar la vista de grupos para leer de las nuevas entidades.

## 3. Fase 1: Analisis y reglas de negocio

Objetivo: congelar el modelo actual y definir que significa cada proceso administrativo.

### 3.1 Revision del sistema actual

- [ ] Documentar el flujo actual de alta de alumno.
- [ ] Documentar como se asigna carrera, modalidad, semestre y grupo.
- [ ] Documentar como se crean materias y como se asignan docentes.
- [ ] Documentar como se generan calificaciones actualmente.
- [ ] Documentar como se generan los pagos del ciclo.

### 3.2 Inventario tecnico

- [ ] Revisar y documentar el uso actual de `User`.
- [ ] Revisar y documentar el uso actual de `Subject`.
- [ ] Revisar y documentar el uso actual de `SubjectAssignment`.
- [ ] Revisar y documentar el uso actual de `Grade`.
- [ ] Revisar y documentar el uso actual de `Payment`.
- [ ] Revisar y documentar el uso actual de `SchoolCycle`.
- [ ] Revisar y documentar el uso actual de `CycleTuition`.
- [ ] Revisar y documentar el uso actual de `ServiceRequest`.

### 3.3 Reglas de negocio por validar

- [ ] Definir que significa alumno inscrito.
- [ ] Definir cuando un alumno cambia de semestre.
- [ ] Definir cuando un alumno cambia de grupo.
- [ ] Definir como se registra una baja temporal.
- [ ] Definir como se gestiona una baja definitiva.
- [ ] Definir diferencia operativa entre ordinario, extraordinario y recursa.
- [ ] Definir que adeudos generan bloqueo y en que procesos impactan.

### 3.4 Entregable de fase

- [ ] Crear documento corto de reglas de negocio aprobadas.

## 4. Fase 2: Nuevo modelo de datos base

Objetivo: introducir las entidades correctas sin romper el modelo actual.

### 4.1 Entidad `StudyPlan`

- [ ] Crear modelo `StudyPlan`.
- [ ] Agregar relacion con `Career`.
- [ ] Agregar campo `version`.
- [ ] Agregar campo `is_active`.
- [ ] Agregar timestamps necesarios.

Campos sugeridos:

- `id`
- `career_id`
- `name`
- `version`
- `is_active`
- `created_at`

### 4.2 Entidad `StudyPlanSubject`

- [ ] Crear modelo `StudyPlanSubject`.
- [ ] Relacionar `StudyPlanSubject` con `StudyPlan`.
- [ ] Relacionar `StudyPlanSubject` con `Subject`.
- [ ] Agregar `semester`, `order_index` e `is_required`.
- [ ] Preparar consultas para mapa curricular.

Campos sugeridos:

- `id`
- `study_plan_id`
- `subject_id`
- `semester`
- `order_index`
- `is_required`

### 4.3 Entidad `Group`

- [ ] Crear modelo `Group`.
- [ ] Relacionar `Group` con `SchoolCycle`.
- [ ] Relacionar `Group` con `StudyPlan`.
- [ ] Relacionar `Group` con `Modality`.
- [ ] Relacionar `Group` con tutor o docente responsable.
- [ ] Agregar `capacity`.
- [ ] Agregar `is_active`.

Campos sugeridos:

- `id`
- `cycle_id`
- `study_plan_id`
- `name`
- `semester`
- `modality_id`
- `shift`
- `capacity`
- `tutor_teacher_id`
- `is_active`

### 4.4 Entidad `StudentEnrollment`

- [ ] Crear modelo `StudentEnrollment`.
- [ ] Relacionar `StudentEnrollment` con alumno.
- [ ] Relacionar `StudentEnrollment` con ciclo.
- [ ] Relacionar `StudentEnrollment` con plan.
- [ ] Relacionar `StudentEnrollment` con grupo.
- [ ] Relacionar `StudentEnrollment` con modalidad.
- [ ] Agregar estatus escolares.
- [ ] Agregar banderas financieras.
- [ ] Agregar fechas de alta y baja.
- [ ] Agregar notas administrativas.

Campos sugeridos:

- `id`
- `student_id`
- `cycle_id`
- `study_plan_id`
- `group_id`
- `modality_id`
- `semester`
- `enrollment_status`
- `academic_status`
- `financial_hold`
- `enrollment_date`
- `drop_date`
- `notes`

### 4.5 Entidad `CourseEnrollment`

- [ ] Crear modelo `CourseEnrollment`.
- [ ] Relacionar `CourseEnrollment` con `StudentEnrollment`.
- [ ] Relacionar `CourseEnrollment` con `SubjectAssignment`.
- [ ] Agregar `status`.
- [ ] Agregar `attempt_type`.
- [ ] Agregar `enrolled_at`.
- [ ] Agregar `dropped_at`.

Campos sugeridos:

- `id`
- `student_enrollment_id`
- `subject_assignment_id`
- `status`
- `attempt_type`
- `enrolled_at`
- `dropped_at`

### 4.6 Ajuste de `Grade`

- [ ] Redefinir el papel de `Grade` como resultado evaluativo.
- [ ] Relacionar `Grade` con `CourseEnrollment`.
- [ ] Agregar soporte para parciales.
- [ ] Agregar soporte para final.
- [ ] Agregar soporte para extraordinario.
- [ ] Agregar fecha de registro.

Campos sugeridos:

- `id`
- `course_enrollment_id`
- `partial_1`
- `partial_2`
- `partial_3`
- `final_score`
- `status`
- `extraordinary_score`
- `recorded_at`

### 4.7 Entregables de fase

- [ ] Modelos SQLAlchemy creados.
- [ ] Schemas Pydantic creados.
- [ ] Migraciones Alembic generadas.
- [ ] Relaciones y constraints revisados.

## 5. Fase 3: Migracion de datos

Objetivo: poblar las nuevas entidades con datos actuales sin romper la operacion existente.

### 5.1 Preparacion

- [ ] Crear estrategia de migracion reversible.
- [ ] Definir si se usara ciclo activo o ciclo legado para backfill.
- [ ] Definir nomenclatura para grupos migrados desde texto.

### 5.2 Backfill de inscripciones

- [ ] Tomar `User.carrera` y mapearla a carrera o plan.
- [ ] Tomar `User.modalidad` y mapearla a modalidad real.
- [ ] Tomar `User.semestre` y mapearlo a semestre operativo.
- [ ] Tomar `User.grupo` y convertirlo en entidad `Group`.
- [ ] Crear un `StudentEnrollment` por alumno.

### 5.3 Backfill academico

- [ ] Crear `CourseEnrollment` a partir de `Grade`.
- [ ] Relacionar cada `Grade` legado con un `CourseEnrollment`.
- [ ] Conservar `assignment_id` cuando exista.
- [ ] Marcar registros dudosos para revision manual.

### 5.4 Compatibilidad temporal

- [ ] Mantener campos legacy en `User` durante convivencia.
- [ ] Mantener respuestas compatibles para el frontend actual.
- [ ] Marcar con comentarios o docs que partes son temporales.

### 5.5 Validacion

- [ ] Comparar total de alumnos antes y despues de migrar.
- [ ] Comparar total de grupos detectados antes y despues.
- [ ] Comparar total de materias inscritas antes y despues.
- [ ] Comparar total de pagos antes y despues.
- [ ] Revisar muestra manual de expedientes migrados.

### 5.6 Entregables de fase

- [ ] Migracion Alembic aplicada en entorno de prueba.
- [ ] Script de backfill creado.
- [ ] Script de validacion creado.
- [ ] Resultado de validacion documentado.

## 6. Fase 4: Backend por dominios

Objetivo: reordenar la API alrededor de procesos reales de administracion escolar.

### 6.1 Modulo de control escolar

- [ ] Crear endpoint para listar inscripciones por ciclo.
- [ ] Crear endpoint para consultar expediente por ciclo.
- [ ] Crear endpoint para crear inscripcion de alumno.
- [ ] Crear endpoint para reinscripcion a nuevo ciclo.
- [ ] Crear endpoint para cambio de estatus escolar.
- [ ] Crear endpoint para mover alumno entre grupos.

### 6.2 Modulo de grupos

- [ ] Crear endpoint para alta de grupo.
- [ ] Crear endpoint para editar grupo.
- [ ] Crear endpoint para asignar tutor.
- [ ] Crear endpoint para listar grupos por ciclo.
- [ ] Crear endpoint para listar grupos por carrera y semestre.
- [ ] Crear endpoint para agregar alumnos a grupo.
- [ ] Crear endpoint para quitar alumnos de grupo.
- [ ] Crear endpoint para consultar carga y cupo del grupo.

### 6.3 Modulo de oferta academica

- [ ] Crear endpoint para alta de plan de estudios.
- [ ] Crear endpoint para versionado de plan.
- [ ] Crear endpoint para listar materias por plan.
- [ ] Crear endpoint para asignar materias al plan.
- [ ] Crear endpoint para asignar docentes por ciclo y grupo.

### 6.4 Modulo de carga academica

- [ ] Crear endpoint para inscribir alumno a materia.
- [ ] Crear endpoint para baja de materia.
- [ ] Crear endpoint para registrar recursa.
- [ ] Crear endpoint para registrar extraordinario.
- [ ] Crear endpoint para cierre de acta o cierre de curso.

### 6.5 Modulo de calificaciones

- [ ] Crear endpoint para captura de parciales.
- [ ] Crear endpoint para captura de final.
- [ ] Crear endpoint para captura de extraordinario.
- [ ] Crear endpoint para consulta de historial academico.
- [ ] Crear endpoint para bloqueo de edicion tras cierre.

### 6.6 Modulo de finanzas

- [ ] Definir si se crea `Charge` o se rediseña `Payment`.
- [ ] Crear entidad de cargos por inscripcion.
- [ ] Relacionar cargos con `StudentEnrollment`.
- [ ] Crear endpoint para generar cargos del ciclo.
- [ ] Crear endpoint para registrar pago.
- [ ] Crear endpoint para listar cartera por ciclo.
- [ ] Crear endpoint para marcar vencidos.
- [ ] Crear endpoint para aplicar descuento o beca.
- [ ] Crear endpoint para bloqueo o desbloqueo por adeudo.

### 6.7 Entregables de fase

- [ ] Endpoints nuevos implementados.
- [ ] Tests de API agregados.
- [ ] Documentacion en `docs/API.md` actualizada.

## 7. Fase 5: Rediseño del frontend admin

Objetivo: que el panel funcione por procesos operativos y no solo por tablas de captura.

### 7.1 Reorden del menu

- [ ] Reordenar menu a: Dashboard, Control escolar, Grupos, Oferta academica, Calificaciones, Tesoreria, Servicios escolares, Reportes, Configuracion.
- [ ] Ajustar navegacion y vistas activas.
- [ ] Ajustar permisos por rol si aplica.

### 7.2 Vista de control escolar

- [ ] Crear buscador de alumno centralizado.
- [ ] Mostrar expediente por ciclo.
- [ ] Mostrar inscripcion actual.
- [ ] Mostrar historial de ciclos.
- [ ] Mostrar estatus academico.
- [ ] Mostrar grupo actual.
- [ ] Mostrar materias inscritas.
- [ ] Mostrar bloqueos financieros.

### 7.3 Vista de grupos

- [ ] Mostrar grupos del ciclo activo.
- [ ] Mostrar cupo y ocupacion.
- [ ] Mostrar tutor.
- [ ] Mostrar alumnos del grupo.
- [ ] Mostrar materias asignadas al grupo.
- [ ] Habilitar acciones masivas.

### 7.4 Vista de oferta academica

- [ ] Separar catalogo de materias.
- [ ] Crear gestion de planes de estudio.
- [ ] Crear mapa curricular.
- [ ] Crear gestion de asignaciones docentes.

### 7.5 Vista de calificaciones

- [ ] Permitir captura por grupo.
- [ ] Permitir captura por materia.
- [ ] Permitir captura de parciales.
- [ ] Permitir cierre de calificaciones.
- [ ] Permitir extraordinarios.
- [ ] Permitir consulta de historial por alumno.

### 7.6 Vista de tesoreria

- [ ] Mostrar cargos del ciclo.
- [ ] Mostrar pagos registrados.
- [ ] Mostrar cartera vencida.
- [ ] Mostrar descuentos y becas.
- [ ] Mostrar bloqueos por adeudo.
- [ ] Crear corte por periodo.

### 7.7 Entregables de fase

- [ ] Nuevas vistas conectadas al backend nuevo.
- [ ] Componentes legacy marcados para retiro.
- [ ] Validacion funcional con usuarios de prueba.

## 8. Fase 6: Reglas operativas obligatorias

Objetivo: asegurar consistencia y evitar errores administrativos.

- [ ] No permitir mas de una inscripcion activa del mismo alumno en el mismo ciclo.
- [ ] No permitir duplicar inscripcion a la misma materia en la misma oportunidad.
- [ ] No permitir asignar alumnos a grupos de semestre o plan incorrecto.
- [ ] No permitir generar cargos duplicados para la misma inscripcion y periodo.
- [ ] No permitir editar calificaciones cerradas sin permiso especial.
- [ ] Aplicar bloqueos por adeudo segun la politica validada.
- [ ] Agregar constraints y validaciones backend para todas las reglas anteriores.
- [ ] Agregar tests para todas las reglas anteriores.

## 9. Fase 7: Reportes prioritarios

Objetivo: dar visibilidad administrativa real.

- [ ] Crear reporte de matricula activa por ciclo.
- [ ] Crear reporte de alumnos por carrera.
- [ ] Crear reporte de alumnos por modalidad.
- [ ] Crear reporte de alumnos por semestre y grupo.
- [ ] Crear reporte de reinscripcion vs bajas.
- [ ] Crear reporte de aprobacion y reprobacion por materia.
- [ ] Crear reporte de aprobacion y reprobacion por docente.
- [ ] Crear reporte de alumnos con materias reprobadas.
- [ ] Crear reporte de cartera vencida por ciclo.
- [ ] Crear reporte de ingresos cobrados vs pendientes.
- [ ] Crear reporte de alumnos bloqueados por adeudo.

## 10. Fase 8: Limpieza del legado

Objetivo: retirar dependencias del modelo antiguo cuando lo nuevo ya este estable.

### 10.1 Deprecacion

- [ ] Dejar de usar `User.grupo` como fuente operativa.
- [ ] Dejar de usar `User.semestre` como fuente operativa.
- [ ] Dejar de usar `User.carrera` como fuente operativa.
- [ ] Dejar de usar `User.modalidad` como fuente operativa.

### 10.2 Retiro progresivo

- [ ] Mover la logica automatica actual de `Grade` a `StudentEnrollment` y `CourseEnrollment`.
- [ ] Retirar codigo puente del backend cuando el frontend nuevo ya lo use todo.
- [ ] Retirar vistas viejas del admin que ya no se necesiten.
- [ ] Limpiar schemas y endpoints obsoletos.
- [ ] Actualizar documentacion final del sistema.

## 11. Sprints sugeridos

### Sprint 1

- [ ] Crear `Group`.
- [ ] Crear `StudentEnrollment`.
- [ ] Crear migraciones Alembic iniciales.
- [ ] Crear endpoint para listar inscripciones por ciclo.
- [ ] Crear endpoint para mover alumno a grupo.
- [ ] Adaptar vista de grupos.

Resultado esperado:

- historial por ciclo funcional
- grupos reales en lugar de texto libre

### Sprint 2

- [ ] Crear `StudyPlan`.
- [ ] Crear `StudyPlanSubject`.
- [ ] Crear `CourseEnrollment`.
- [ ] Separar `Grade` del proceso de inscripcion.
- [ ] Rediseñar captura de calificaciones por grupo y materia.

Resultado esperado:

- carga academica mas clara
- mejor control de calificaciones y recursas

### Sprint 3

- [ ] Crear `Charge` o rediseñar `Payment`.
- [ ] Relacionar cargos con `StudentEnrollment`.
- [ ] Rehacer generacion automatica de colegiaturas.
- [ ] Crear reportes de cartera vencida.
- [ ] Crear bloqueo financiero por adeudo.

Resultado esperado:

- tesoreria ligada al ciclo e inscripcion
- mejor control de cobranza

## 12. Criterios de cierre

El proyecto se puede considerar completo cuando se cumpla todo lo siguiente:

- [ ] Un alumno puede tener historial completo por ciclo sin sobrescribir su pasado.
- [ ] Un grupo existe como entidad propia y se opera desde el panel.
- [ ] Una materia cursada no depende solo de un registro de calificacion.
- [ ] Los pagos y cargos pueden auditarse por ciclo e inscripcion.
- [ ] El admin opera por procesos escolares y no por datos sueltos.
- [ ] El frontend ya no depende del flujo legacy para procesos principales.

## 13. Recomendacion final

No conviene implementar todo de golpe. La ruta recomendada es:

- [ ] mantener temporalmente el modelo actual
- [ ] introducir nuevas entidades por convivencia
- [ ] mover primero grupos e inscripciones
- [ ] mover despues carga academica y calificaciones
- [ ] cerrar con finanzas, reportes y limpieza final

Ese camino reduce riesgo, conserva datos y permite seguir operando mientras el panel evoluciona.
