# Backlog PagWebUnives

Lista viva para atacar pendientes. Marca `[x]` lo completado y trabaja por bloques.

## Seguridad y configuracion
- [x] Separar secretos y credenciales reales en `backend/.env` y no en `docker-compose.yml`.
- [x] Restringir CORS en produccion a dominios reales (no `*`).
- [x] Rotar `SECRET_KEY` con politica y documentarla; agregar soporte de rotacion.
- [x] Validar tamanio/tipo de archivos en uploads e importaciones CSV.
- [x] Agregar rate limiting / bloqueo tras intentos fallidos de login.

## Infra y despliegue
- [x] Crear `docker-compose.override.yml` para desarrollo y dejar `docker-compose.yml` endurecido para prod.
- [x] Agregar healthchecks para `backend` y `db`.
- [x] Incluir `env_file: backend/.env` en el servicio backend para despliegues.

## Base de datos y migraciones
- [x] Eliminar `Base.metadata.create_all` en `app/main.py` y depender solo de Alembic.
- [x] Ejecutar y documentar `alembic upgrade head` en README (documentado; ejecución requiere Python disponible en el entorno).
- [x] Completar modelos con constraints (enums para status/role, ranges de score, FK con ON DELETE).

## Testing y CI
- [x] Instalar dependencias de test (`pip install -r requirements.txt`) y hacer que `pytest` corra localmente.
- [x] Ampliar cobertura: flujos de docente, servicios escolares, importaciones CSV, uploads.
- [x] Configurar pipeline CI (p.ej. GitHub Actions) con lint + pytest + alembic check.
- [x] Medir cobertura y fijar umbral (p.ej. 80%).

## Backend API
- [x] Validar datos de entrada (pydantic enums/regex, rangos de score 0-100, montos > 0, fechas futuras).
- [x] Agregar endpoints de refresh token o reducir expiracion del access token.
- [x] Manejo de errores estructurado y logs formateados (JSON) con niveles.
- [x] Separar permisos por rol en endpoints docentes/servicios (autorization checks finos).

## Frontend (public/)
- [x] Centralizar base URL de la API mediante configuracion/env, evitar hardcode `http://localhost:8000`.
- [x] Manejar expiracion y errores de token en `login.html` y demas vistas.
- [x] Diferenciar vistas/menus por rol (admin, teacher, student).
- [x] Mejorar estado de carga y mensajes de error en fetch.

## Documentacion
- [x] Documentacion base de endpoints en `docs/API.md`.
- [x] Corregir problemas de encoding (acentos) en README y docs.
- [x] Agregar guia de desarrollo rapido: activar venv, cargar .env, ejecutar alembic, correr tests.
- [x] Incluir seccion de seeds/datos de demo y como cargarlos.

## Datos y archivos
- [x] Limpiar CSV vacios en `backend/` y documentar fuente de datos reales en la raiz.
- [x] Definir politica de limpieza/backups para `uploads/`.

## Nuevos pendientes
- [x] Actualizar README (sección "Tareas Pendientes") para reflejar que las pruebas unitarias y el CI ya están implementados.
- [x] Migrar validadores Pydantic a la sintaxis V2 para eliminar los warnings actuales en los tests.
- [x] Limpiar los directorios temporales de pruebas (`pytest_tmp_*`, `temp_pytest_accessible`) y documentar la ruta de `basetemp` en la guía de contribución.

## Rediseño del panel admin escolar

### Fase 1. Reglas de negocio y analisis
- [x] Documentar el flujo actual de alta de alumno, asignacion de grupo, materias, calificaciones y pagos.
- [x] Definir con administracion que significa alumno inscrito, baja temporal, baja definitiva, recursa y extraordinario.
- [x] Definir politica de bloqueo por adeudo y en que procesos aplica.
- [x] Documentar que campos actuales de `User`, `Grade` y `Payment` se consideran legacy.
- [x] Crear documento de estado actual en `docs/ADMIN_PHASE1_CURRENT_STATE.md`.
- [x] Crear borrador de reglas de negocio en `docs/ADMIN_PHASE1_BUSINESS_RULES_DRAFT.md`.
- [x] Cerrar reglas aprobadas en `docs/ADMIN_PHASE1_APPROVED_RULES.md`.

### Fase 2. Nuevo modelo base
- [x] Crear entidad `Group` como grupo real por ciclo.
- [x] Crear entidad `StudentEnrollment` como expediente del alumno por ciclo.
- [x] Crear entidad `StudyPlan`.
- [x] Crear entidad `StudyPlanSubject`.
- [x] Crear entidad `CourseEnrollment`.
- [x] Redefinir `Grade` para que represente el resultado evaluativo y no toda la inscripcion academica.
- [x] Agregar `recorded_at` y `teacher_locked` en `Grade` para captura docente de una sola vez.
- [x] Crear migraciones Alembic para las nuevas entidades.
- [x] Cerrar Fase 2 en `docs/ADMIN_PHASE2_CLOSURE.md`.

### Fase 3. Migracion y compatibilidad
- [x] Alinear tecnicamente las reglas aprobadas en `docs/ADMIN_RULES_ALIGNMENT.md`.
- [x] Crear script de backfill desde `User.carrera`, `User.modalidad`, `User.semestre` y `User.grupo` hacia `StudentEnrollment`.
- [x] Convertir grupos basados en texto en registros de `Group`.
- [x] Crear `CourseEnrollment` a partir de `Grade` existente.
- [x] Mantener compatibilidad temporal con el frontend actual mientras conviven ambos modelos.
- [x] Validar conteos de alumnos, grupos y materias inscritas despues de migrar.
- [x] Cerrar Fase 3 en `docs/ADMIN_PHASE3_CLOSURE.md`.

### Fase 4. Backend por dominios
- [x] Crear endpoints de control escolar para listar inscripciones por ciclo, crear inscripcion y mover alumno de grupo.
- [x] Crear endpoints de grupos para alta, edicion, asignacion de tutor y gestion de alumnos.
- [x] Crear endpoints de oferta academica para planes de estudio y materias por plan.
- [x] Crear endpoints de carga academica para inscripcion a materias, baja de materia, recursa y extraordinario.
- [x] Crear endpoints de calificacion final e historial academico.
- [x] Definir `Charge` como nuevo dominio financiero y mantener `Payment` como compatibilidad temporal.

### Fase 5. Frontend admin
- [x] Reordenar el menu admin por dominios: Control escolar, Grupos, Oferta academica, Calificaciones, Tesoreria, Servicios escolares y Reportes.
- [x] Crear una vista de Control escolar centrada en expediente por ciclo.
- [x] Rediseñar la vista de Grupos para operar con grupos reales y cupos.
- [x] Separar en frontend la oferta academica de la operacion escolar.
- [x] Rediseñar la captura de calificaciones para operar por grupo y materia.
- [x] Rediseñar Tesoreria para mostrar cargos, pagos, cartera y bloqueos.

### Fase 6. Reglas y calidad
- [x] Impedir mas de una inscripcion activa del mismo alumno en el mismo ciclo.
- [x] Impedir duplicar inscripcion a la misma materia en la misma oportunidad.
- [x] Impedir cargos duplicados para la misma inscripcion y periodo.
- [x] Impedir editar calificaciones cerradas sin permiso especial.
- [x] Agregar tests para las nuevas reglas operativas.
- [x] Actualizar `docs/API.md` conforme se publiquen los endpoints nuevos.

### Fase 7. Reportes y cierre
- [x] Crear reportes de matricula activa por ciclo, carrera, modalidad, semestre y grupo.
- [x] Crear reportes de aprobacion y reprobacion por materia y docente.
- [x] Crear reportes de cartera vencida e ingresos cobrados vs pendientes.
- [x] Crear reporte de alumnos bloqueados por adeudo.
- [x] Deprecar el uso operativo de `User.grupo`, `User.semestre`, `User.carrera` y `User.modalidad`.
- [x] Eliminar codigo puente legacy cuando el frontend nuevo ya no lo necesite.

### Primer bloque recomendado
- [x] Crear `Group`.
- [x] Crear `StudentEnrollment`.
- [x] Crear migracion Alembic inicial.
- [x] Crear endpoint para listar inscripciones por ciclo.
- [x] Crear endpoint para mover alumno a grupo.
- [x] Adaptar la vista de grupos para consumir las nuevas entidades.

