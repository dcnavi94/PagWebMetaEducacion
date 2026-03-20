# Fase 1 - Reglas Aprobadas

Este documento cierra la Fase 1 con base en las respuestas capturadas en la reunion administrativa.

Su objetivo es dejar por escrito las reglas operativas aprobadas y separar los puntos que ya quedaron definidos de los que todavia requieren alineacion tecnica.

## 1. Regla principal aprobada

La unidad operativa del sistema sera la **inscripcion del alumno por ciclo**.

Esto implica:

- el alumno puede existir como usuario sin estar inscrito
- semestre, carrera, modalidad y grupo deben registrarse por ciclo
- el historial no debe sobrescribirse cuando cambie la situacion del alumno

## 2. Reglas aprobadas sobre alumnos e inscripcion

- Un alumno si puede existir en el sistema sin estar inscrito en un ciclo.
- Un alumno no puede tener mas de una inscripcion activa en el mismo ciclo.
- El semestre debe guardarse por ciclo.
- Carrera, modalidad y grupo deben registrarse por cada ciclo.
- Los estatus operativos aprobados son: `Inscrito`, `No Inscrito`, `Baja Temporal`, `Baja Definitiva`, `Graduado`.
- `Baja Temporal` permite reingreso posterior.
- `Baja Definitiva` representa cierre del alumno en ese ciclo.

## 3. Reglas aprobadas sobre grupos

- El grupo debe existir como entidad propia.
- El grupo no queda amarrado tecnicamente a un ciclo.
- El grupo debe tener modalidad.
- El grupo no requiere cupo maximo obligatorio.
- El grupo no requiere tutor obligatorio.
- El grupo puede asociarse a una carrera o plan, pero en universidad puede compartirse entre `Ingenieria en Telematica` e `Ingenieria en Software`.
- Todo cambio de grupo debe guardar fecha y motivo.

## 4. Reglas aprobadas sobre plan y materias

- Las materias deben depender de un plan de estudios formal.
- No se manejaran varias versiones activas de plan por carrera como regla normal.
- La generacion debe conservar el plan que le corresponda aunque despues cambie el actual.

## 5. Reglas aprobadas sobre calificaciones

- El sistema no manejara calificaciones parciales.
- Solo se capturara calificacion final.
- La minima aprobatoria se mantiene en `6`.
- El docente solo puede asignar la calificacion una sola vez.
- Una calificacion cerrada solo puede ser corregida por `admin`.

## 6. Reglas aprobadas sobre extraordinario y recursa

- `Extraordinario` y `Recursa` son procesos distintos.
- `Extraordinario` normalmente ocurre dentro del mismo ciclo, aunque administrativamente puede impactar otro ciclo.
- `Recursa` significa volver a cursar la materia en un ciclo posterior.

## 7. Reglas aprobadas sobre pagos y adeudos

- Los pagos deben asociarse a la inscripcion del ciclo.
- Deben distinguirse tipos de cargo como colegiatura, reinscripcion, tramite, recargo y otros.
- Deben existir becas o descuentos recurrentes.
- Debe existir cartera vencida por ciclo.

## 8. Politica aprobada de bloqueo por adeudo

- El bloqueo puede activarse manualmente por `admin`.
- Referencia operativa inicial: `3` mensualidades vencidas.
- El bloqueo afecta inicio de sesion.
- El bloqueo afecta reinscripcion.
- El bloqueo afecta tramites.
- Solo `admin` puede desbloquear manualmente.

## 9. Puntos que quedaron definidos como decisiones tecnicas

- La Fase 1 queda cerrada para continuar con diseno e implementacion.
- Las definiciones base de alumno, inscripcion, grupo, calificacion final, extraordinario, recursa y bloqueo ya quedaron aprobadas.

## 10. Puntos que requieren alineacion tecnica posterior

Estas decisiones fueron respondidas, pero hoy no estan totalmente alineadas con la implementacion actual y deben revisarse en Fase 2/Fase 3:

- `Un alumno puede estar en dos grupos activos del mismo ciclo`: la respuesta capturada fue `SI`, pero el modelo actual trabaja con una sola inscripcion activa por ciclo y un solo grupo por inscripcion.
- `El grupo no pertenece a un ciclo`: esto ya se acerca al modelo actual porque `Group` es reutilizable, pero la operacion diaria sigue descansando en `StudentEnrollment` por ciclo.
- `Extraordinario dentro del mismo ciclo, aunque puede impactar otro ciclo`: esto requiere una regla tecnica mas precisa para reportes e historial.

## 11. Cierre de Fase 1

Con estas reglas, la Fase 1 se considera cerrada.

Lo siguiente pertenece a implementacion:

- alinear las reglas aprobadas con el modelo de datos
- resolver las excepciones que chocan con la implementacion actual
- seguir con migracion, compatibilidad y frontend admin
