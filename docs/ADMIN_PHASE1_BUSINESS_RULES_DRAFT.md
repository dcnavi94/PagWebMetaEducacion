# Fase 1 - Borrador de Reglas de Negocio para Validacion

Este documento propone reglas de negocio iniciales para validar con administracion antes de rediseñar base de datos y flujos.

No todas deben considerarse cerradas todavia. La idea es usarlas como base de trabajo.

## 1. Principio rector

La unidad operativa principal debe ser la **inscripcion del alumno por ciclo**.

Eso significa:

- un usuario puede existir en el sistema
- pero su situacion escolar debe definirse por ciclo
- ningun cambio de grupo, semestre o estatus debe sobrescribir el historial de ciclos previos

## 2. Reglas propuestas sobre alumnos

### 2.1 Alta de alumno

- [ ] Un alumno puede existir como usuario sin estar inscrito en un ciclo.
- [ ] La matricula debe ser unica en todo el sistema.
- [ ] El correo puede ser opcional, pero si existe debe ser unico.
- [ ] El alta del alumno no debe crear por si sola un historial academico irreversible.

### 2.2 Estatus de cuenta

- [ ] `Activo` significa que puede usar el sistema conforme a su rol.
- [ ] `Baja` significa que la cuenta ya no debe operar academicamente.
- [ ] `Bloqueado` significa que mantiene historial pero tiene restricciones temporales.

### 2.3 Estatus escolar por ciclo

- [ ] `Inscrito` significa que tiene una inscripcion activa en un ciclo.
- [ ] `No Inscrito` significa que existe como alumno pero no esta activo en el ciclo.
- [ ] `Baja Temporal` significa que conserva posible reingreso.
- [ ] `Baja Definitiva` significa cierre escolar de ese ciclo.
- [ ] `Graduado` significa fin de trayectoria en su plan.

## 3. Reglas propuestas sobre inscripcion

### 3.1 Inscripcion por ciclo

- [ ] Un alumno no debe tener mas de una inscripcion activa en el mismo ciclo.
- [ ] Cada inscripcion debe guardar carrera o plan, modalidad, semestre, grupo y estatus.
- [ ] La inscripcion debe tener fecha de alta.
- [ ] Si el alumno se da de baja, la inscripcion debe guardar fecha y motivo.

### 3.2 Reinscripcion

- [ ] Reinscribir no debe modificar la inscripcion anterior.
- [ ] Cada nuevo ciclo debe generar un nuevo registro de inscripcion.
- [ ] El semestre siguiente debe definirse desde la inscripcion nueva, no desde `User`.

## 4. Reglas propuestas sobre grupos

### 4.1 Naturaleza del grupo

- [ ] Un grupo debe existir como entidad propia.
- [ ] Un grupo debe pertenecer a un ciclo.
- [ ] Un grupo debe pertenecer a un plan o carrera.
- [ ] Un grupo debe tener modalidad.
- [ ] Un grupo puede tener tutor o responsable academico.
- [ ] Un grupo debe poder manejar cupo.

### 4.2 Movimiento de alumnos

- [ ] Cambiar de grupo no debe borrar el historial del alumno.
- [ ] Un alumno no debe pertenecer a dos grupos activos del mismo ciclo.
- [ ] Si cambia de grupo, debe quedar evidencia del movimiento.

## 5. Reglas propuestas sobre materias y oferta academica

### 5.1 Plan de estudios

- [ ] Las materias deben colgar de un plan de estudios versionado.
- [ ] Un plan puede tener varias versiones historicas.
- [ ] Una generacion debe seguir el plan asignado al momento de su ingreso o reinscripcion.

### 5.2 Asignacion docente

- [ ] La oferta de una materia en un ciclo debe definirse por asignacion.
- [ ] Una asignacion debe poder distinguir grupo o seccion.
- [ ] Un docente no debe tener la misma materia duplicada en la misma seccion del mismo ciclo.

## 6. Reglas propuestas sobre carga academica

### 6.1 Inscripcion a materia

- [ ] La inscripcion a materia debe ser una entidad distinta a la calificacion.
- [ ] Un alumno no debe inscribirse dos veces a la misma materia en la misma oportunidad.
- [ ] La inscripcion a materia debe estar ligada a una inscripcion escolar vigente.

### 6.2 Baja de materia

- [ ] Una baja de materia debe conservar historial.
- [ ] Dar de baja una materia no debe borrar calificaciones previas ni trazabilidad.

### 6.3 Recursa y extraordinario

- [ ] `Regular` debe representar el intento ordinario del ciclo.
- [ ] `Extraordinario` debe representar una oportunidad adicional del mismo ciclo o cierre definido por administracion.
- [ ] `Recursa` debe representar volver a cursar una materia en un ciclo posterior.
- [ ] Recursa y extraordinario no deben modelarse igual.

## 7. Reglas propuestas sobre calificaciones

### 7.1 Captura

- [ ] La captura de calificacion debe poder manejar parciales.
- [ ] Debe existir una calificacion final.
- [ ] Debe existir control de extraordinario si aplica.

### 7.2 Cierre

- [ ] Una vez cerrada una calificacion, no debe editarse libremente.
- [ ] Solo un permiso especial debe permitir reapertura o correccion.
- [ ] Todo cambio posterior al cierre debe quedar auditado.

### 7.3 Aprobacion

- [ ] La calificacion aprobatoria base propuesta es `>= 6`, salvo que administracion defina otra politica.
- [ ] El sistema debe distinguir claramente entre cursando, aprobada, reprobada y proximamente.

## 8. Reglas propuestas sobre finanzas

### 8.1 Cargo

- [ ] Un cargo debe asociarse a la inscripcion del alumno, no solo al usuario.
- [ ] El sistema no debe depender solo del texto `concept` para identificar el cargo.
- [ ] Debe existir un identificador de periodo o tipo de cargo.

### 8.2 Generacion automatica

- [ ] Los cargos del ciclo deben generarse solo para alumnos inscritos.
- [ ] No se deben duplicar cargos del mismo periodo para la misma inscripcion.
- [ ] Debe poder distinguirse colegiatura, reinscripcion, recargo, tramite u otro concepto.

### 8.3 Pago

- [ ] Registrar pago no debe destruir el cargo original.
- [ ] Debe quedar evidencia de fecha de pago y estatus.
- [ ] Debe existir posibilidad futura de descuento, beca o recargo.

## 9. Reglas propuestas sobre bloqueo por adeudo

Estas reglas deben validarse con administracion porque impactan operacion y experiencia del alumno.

- [ ] Definir cuantas mensualidades vencidas causan bloqueo.
- [ ] Definir si el bloqueo impide solo acceso o tambien reinscripcion, carga academica y tramites.
- [ ] Definir si el bloqueo aplica por ciclo actual o por cualquier adeudo historico.
- [ ] Definir quien puede desbloquear manualmente.
- [ ] Definir si existe desbloqueo temporal por convenio.

## 10. Reglas propuestas sobre tramites

- [ ] Un tramite debe conservar historial de estatus.
- [ ] El tramite debe poder asociarse a restricciones por adeudo si administracion lo decide.
- [ ] Debe quedar claro que tramites requieren estatus academico activo.

## 11. Preguntas que administracion debe responder

Estas preguntas siguen abiertas y deben validarse antes de entrar a Fase 2:

- [ ] ¿El alumno puede existir sin ciclo activo asignado?
- [ ] ¿El semestre pertenece al alumno o a la inscripcion del ciclo?
- [ ] ¿Un grupo puede mezclar modalidades?
- [ ] ¿Un grupo puede mezclar semestres?
- [ ] ¿Como debe manejarse un cambio de carrera?
- [ ] ¿El extraordinario cuenta dentro del mismo ciclo o como cierre posterior?
- [ ] ¿La recursa crea una nueva inscripcion a materia en otro ciclo?
- [ ] ¿Que adeudos bloquean login y cuales solo bloquean procesos escolares?
- [ ] ¿Como debe modelarse una beca o descuento recurrente?

## 12. Recomendacion operativa

Antes de entrar a cambios de base de datos, se recomienda validar como minimo estas decisiones:

- [ ] que es una inscripcion activa
- [ ] que es un grupo real
- [ ] como distinguir extraordinario de recursa
- [ ] cuando bloquear por adeudo
- [ ] como se cierra una calificacion

Si esas cinco decisiones quedan aprobadas, ya se puede pasar a crear `Group` y `StudentEnrollment` con mucha menos incertidumbre.
