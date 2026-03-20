# Documentación de la API - Plataforma Escolar Unives

Base URL: `http://localhost:8000` (o la URL de tu despliegue)

## Autenticación

La API usa **JWT Bearer**. Tras iniciar sesión en `POST /token`, incluye el token en el header:

```
Authorization: Bearer <access_token>
```

---

## Endpoints

### Raíz

#### `GET /`

Mensaje de bienvenida.

**Respuesta 200:**
```json
{
  "message": "Bienvenido a la API de la Plataforma Escolar Unives"
}
```

---

### Autenticación

#### `POST /token`

Inicia sesión y devuelve un token JWT.

**Content-Type:** `application/x-www-form-urlencoded`

**Parámetros (form-data):**
| Campo      | Tipo   | Requerido | Descripción                    |
|------------|--------|-----------|--------------------------------|
| username   | string | Sí        | Matrícula o usuario            |
| password   | string | Sí        | Contraseña                     |

**Respuesta 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errores:**
- `401`: Usuario o contraseña incorrectos

---

### Usuario actual (todos los roles autenticados)

#### `GET /users/me`

Obtiene el perfil del usuario autenticado.

**Autenticación:** Bearer token requerido

**Respuesta 200:** Objeto `User` con `id`, `username`, `email`, `full_name`, `role`, `carrera`, `modalidad`, `semestre`, `grupo`.

---

#### `PUT /users/me`

Actualiza el perfil del usuario autenticado.

**Autenticación:** Bearer token requerido

**Body (JSON):**
```json
{
  "full_name": "string (opcional)",
  "email": "string (opcional)",
  "password": "string (opcional)"
}
```

**Respuesta 200:** Objeto `User` actualizado.

---

#### `GET /users/me/grades`

Lista las calificaciones del alumno autenticado.

**Autenticación:** Bearer token requerido

**Respuesta 200:**
```json
[
  {
    "period": "2do Semestre",
    "description": "Bases de Datos",
    "score": 8.5,
    "status": "Aprobada"
  }
]
```

---

#### `GET /users/me/courses`

Lista los cursos del alumno con progreso y calificación.

**Autenticación:** Bearer token requerido

**Respuesta 200:**
```json
[
  {
    "id": 1,
    "name": "Bases de Datos",
    "progress": 100,
    "score": 8.5,
    "professor": "Nombre del docente (desde BD)"
  }
]
```

---

#### `GET /users/me/academic-history`

Devuelve el historial académico del alumno autenticado usando el modelo nuevo cuando existe y datos legacy como fallback.

**Autenticación:** Bearer token requerido

**Respuesta 200:**
```json
[
  {
    "grade_id": 10,
    "course_enrollment_id": 12,
    "subject_name": "Bases de Datos",
    "cycle": "2026-1",
    "attempt_type": "Regular",
    "final_score": 8.5,
    "status": "Aprobada"
  }
]
```

---

#### `GET /users/me/payments`

Lista los pagos del alumno autenticado.

**Autenticación:** Bearer token requerido

**Respuesta 200:** Lista de objetos `Payment` (`id`, `concept`, `amount`, `due_date`, `status`, `student_id`).

---

#### `GET /users/me/charges`

Lista los cargos del alumno autenticado.

**Autenticación:** Bearer token requerido

**Respuesta 200:** Lista de objetos `Charge` (`id`, `charge_type`, `concept`, `period_label`, `amount`, `due_date`, `status`).

---

#### `GET /users/me/services`

Lista los trámites del alumno autenticado.

**Autenticación:** Bearer token requerido

**Respuesta 200:** Lista de objetos `ServiceRequest` (`id`, `type`, `status`, `request_date`, `student_id`, `attachment_filename`, `attachment_path`).

---

#### `POST /users/me/services`

Permite al alumno autenticado solicitar un trámite con estatus inicial `En Proceso`.

**Autenticación:** Bearer token requerido

**Body (JSON):**
```json
{
  "type": "Kardex",
  "request_date": "2026-03-19"
}
```

---

#### `POST /users/me/services/with-document`

Permite al alumno autenticado solicitar un trámite y adjuntar un documento en el mismo flujo.

**Autenticación:** Bearer token requerido

**Body:** `multipart/form-data`
- `type`
- `request_date`
- `file`

---

#### `GET /users/me/services/{service_id}/attachment`

Descarga el adjunto de un trámite del propio alumno.

---

#### `GET /users/me/documents`

Lista los documentos subidos por el alumno.

**Autenticación:** Bearer token requerido

**Respuesta 200:**
```json
[
  {
    "filename": "documento.pdf",
    "size": 1024,
    "date": "2026-03-12 14:30:00"
  }
]
```

---

#### `POST /upload-document`

Sube un documento del alumno.

**Autenticación:** Bearer token requerido

**Content-Type:** `multipart/form-data`

**Parámetros:**
| Campo         | Tipo   | Requerido | Descripción                    |
|---------------|--------|-----------|--------------------------------|
| file          | file   | Sí        | Archivo a subir                |
| document_type | string | No        | Tipo de documento (default: "otro") |

**Respuesta 200:**
```json
{
  "filename": "documento.pdf",
  "status": "success",
  "message": "Documento otro subido correctamente"
}
```

---

### Administración (rol `admin`)

#### `GET /admin/stats`

Estadísticas generales del sistema.

**Autenticación:** Bearer token (admin)

**Respuesta 200:**
```json
{
  "total_students": 150,
  "total_income": 125000.50,
  "pending_services": 12,
  "total_teachers": 25
}
```

**Errores:** `403` si no es admin.

---

#### `GET /admin/students`

Lista todos los alumnos.

---

#### `GET /admin/groups`

Lista grupos con conteo de alumnos y metadatos de compatibilidad.

**Autenticación:** Bearer token (admin)

---

#### `POST /admin/groups`

Crea un grupo formal.

**Autenticación:** Bearer token (admin)

**Body (JSON):**
```json
{
  "name": "A",
  "modality_id": 1,
  "tutor_id": 5,
  "is_active": true
}
```

---

#### `PUT /admin/student-enrollments/move-group`

Mueve un alumno a un grupo dentro del ciclo activo o de un ciclo dado.

**Autenticación:** Bearer token (admin)

**Body (JSON):**
```json
{
  "username": "2024001",
  "group_name": "A",
  "cycle_id": 1,
  "reason": "Movimiento administrativo"
}
```

---

#### `PUT /admin/group-actions/bulk-enrollment`

Actualiza el estatus de inscripción de los alumnos de un grupo formal usando `StudentEnrollment` como fuente operativa.

**Autenticación:** Bearer token (admin)

---

#### `POST /admin/group-actions/bulk-assign`

Inscribe a los alumnos de un grupo formal a una asignación académica usando membresías reales del grupo.

**Autenticación:** Bearer token (admin)

---

#### `GET /admin/course-enrollments`

Lista carga académica del modelo nuevo.

**Autenticación:** Bearer token (admin)

---

#### `POST /admin/course-enrollments`

Inscribe un alumno en una asignación concreta.

**Autenticación:** Bearer token (admin)

---

#### `POST /admin/course-enrollments/extraordinary`

Registra extraordinario para una asignación concreta.

**Autenticación:** Bearer token (admin)

---

#### `POST /admin/course-enrollments/retake`

Registra recursa sobre una materia con antecedente reprobado.

**Autenticación:** Bearer token (admin)

---

#### `GET /admin/migration-audit`

Audita conteos entre el modelo legacy y el modelo nuevo para el ciclo activo.

**Autenticación:** Bearer token (admin)

---

#### `GET /admin/reports/enrollment-summary`

Reporte de matrícula activa por ciclo, carrera, modalidad, semestre y grupo.

**Autenticación:** Bearer token (admin)

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

---

#### `GET /admin/reports/grade-outcomes`

Reporte de aprobación y reprobación por materia y docente.

**Autenticación:** Bearer token (admin)

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `teacher_username`, `date_from`, `date_to`

---

#### `GET /admin/reports/finance-summary`

Resumen de cargos emitidos, cobrados, pendientes y vencidos.

**Autenticación:** Bearer token (admin)

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

---

#### `GET /admin/reports/blocked-students`

Reporte de alumnos bloqueados con información de adeudos vencidos.

**Autenticación:** Bearer token (admin)

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

**Respuesta 200:** Lista de objetos `BlockedStudentRow`.

Nota:
Los reportes administrativos ya toman como base operativa el modelo nuevo (`StudentEnrollment`, `Group`, `CourseEnrollment` y `Charge`).
Los campos legacy en `User` se conservan solo como compatibilidad temporal.

---

#### `GET /admin/reports/overview`

Resumen ejecutivo con matrícula, promedio final, aprobación, cartera vencida, bloqueos y servicios pendientes.

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

---

#### `GET /admin/reports/enrollment-status`

Distribución de alumnos por estatus de inscripción.

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

---

#### `GET /admin/reports/teacher-workload`

Carga docente por asignaciones, alumnos, materias y grupos.

**Filtros soportados:** `cycle_id`, `career`, `semester`, `date_from`, `date_to`

---

#### `GET /admin/reports/academic-risk`

Lista de alumnos con reprobación o materias en curso para seguimiento académico.

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

---

#### `GET /admin/reports/service-summary`

Resumen de trámites y servicios escolares por tipo y estatus.

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

---

#### `GET /admin/reports/charge-breakdown`

Desglose financiero por tipo de cargo y estatus.

**Filtros soportados:** `cycle_id`, `career`, `modality`, `semester`, `group_name`, `date_from`, `date_to`

---

#### `POST /admin/students`

Crea un nuevo alumno.

**Body (JSON):**
```json
{
  "username": "2024001",
  "email": "alumno@ejemplo.com",
  "full_name": "Nombre Completo",
  "password": "contraseña_segura",
  "carrera": "Ingeniería en Software",
  "modalidad": "Escolarizada",
  "semestre": "2",
  "grupo": "A"
}
```

| Campo    | Tipo   | Requerido | Descripción                    |
|----------|--------|-----------|--------------------------------|
| username | string | Sí        | Matrícula (única)              |
| email    | string | No        | Correo electrónico             |
| full_name| string | No        | Nombre completo                |
| password | string | Sí        | Contraseña                     |
| carrera  | string | No        | Carrera                        |
| modalidad| string | No        | Modalidad de estudio           |
| semestre | string | No        | Semestre                       |
| grupo    | string | No        | Grupo                          |

**Respuesta 200:** Objeto `User` creado.

**Errores:** `400` si la matrícula ya existe.

---

#### `GET /admin/students/{username}/full`

Obtiene el perfil completo de un alumno por matrícula.

**Parámetros de ruta:** `username` — matrícula del alumno

**Respuesta 200:** Objeto `User` completo.

**Errores:** `404` si el alumno no existe.

---

#### `PUT /admin/students/{username}`

Actualiza un alumno.

**Parámetros de ruta:** `username` — matrícula del alumno

**Body (JSON):**
```json
{
  "full_name": "string (opcional)",
  "email": "string (opcional)",
  "password": "string (opcional)",
  "carrera": "string (opcional)",
  "modalidad": "string (opcional)",
  "semestre": "string (opcional)",
  "grupo": "string (opcional)"
}
```

**Respuesta 200:** Objeto `User` actualizado.

**Errores:** `404` si el alumno no existe.

---

#### `GET /admin/teachers`

Lista todos los docentes.

**Respuesta 200:** Lista de objetos `User` con rol teacher.

---

#### `POST /admin/teachers`

Crea un nuevo docente.

**Body (JSON):**
```json
{
  "username": "PROF001",
  "email": "profesor@ejemplo.com",
  "full_name": "Nombre del Profesor",
  "password": "contraseña_segura"
}
```

**Respuesta 200:** Objeto `User` creado.

**Errores:** `400` si la matrícula/usuario ya existe.

---

#### `PUT /admin/teachers/{username}`

Actualiza un docente.

**Parámetros de ruta:** `username` — usuario/matrícula del docente

**Body (JSON):**
```json
{
  "full_name": "string (opcional)",
  "email": "string (opcional)",
  "password": "string (opcional)"
}
```

**Respuesta 200:** Objeto `User` actualizado.

**Errores:** `404` si el docente no existe.

---

#### `GET /admin/subjects`

Lista todas las materias.

**Respuesta 200:** Lista de objetos `Subject` (`id`, `name`, `credits`, `semester`, `career`).

---

#### `POST /admin/subjects`

Crea una nueva materia.

**Body (JSON):**
```json
{
  "name": "Bases de Datos",
  "credits": 8,
  "semester": "2do Semestre",
  "career": "Ingeniería en Software"
}
```

**Respuesta 200:** Objeto `Subject` creado.

---

#### `PUT /admin/subjects/{subject_id}`

Actualiza una materia.

**Parámetros de ruta:** `subject_id` — ID de la materia

**Body (JSON):**
```json
{
  "name": "string (opcional)",
  "credits": "int (opcional)",
  "semester": "string (opcional)",
  "career": "string (opcional)"
}
```

**Respuesta 200:** Objeto `Subject` actualizado.

**Errores:** `404` si la materia no existe.

---

#### `PUT /admin/grades/{grade_id}`

Actualiza una calificación (admin).

**Parámetros de ruta:** `grade_id` — ID de la calificación

**Body (JSON):**
```json
{
  "score": 8.5,
  "status": "Aprobada"
}
```

Valores de `status`: `"Cursando"`, `"Aprobada"`, `"Reprobada"`.

**Respuesta 200:** Objeto `Grade` actualizado.

**Errores:** `404` si la calificación no existe.

---

#### `GET /admin/payments`

Lista todos los pagos del sistema.

**Respuesta 200:** Lista de objetos `PaymentWithStudent` (pago + datos del alumno).

---

#### `GET /admin/charges`

Lista todos los cargos del sistema.

**Respuesta 200:** Lista de objetos `ChargeWithStudent`.

---

#### `POST /admin/charges`

Crea un cargo por inscripción o periodo y genera su `Payment` espejo de compatibilidad.

**Body (JSON):**
```json
{
  "student_username": "2024001",
  "cycle_id": 1,
  "charge_type": "Inscripcion",
  "concept": "Inscripción 2026-1",
  "period_label": "2026-1",
  "amount": 3500.00,
  "due_date": "2026-03-15T23:59:59",
  "status": "Pendiente"
}
```

**Respuesta 200:** Objeto `ChargeWithStudent`.

---

#### `PUT /admin/charges/{charge_id}`

Actualiza un cargo y sincroniza su `Payment` asociado.

**Parámetros de ruta:** `charge_id` — ID del cargo

**Respuesta 200:** Objeto `Charge` actualizado.

---

#### `POST /admin/payments`

Crea un nuevo pago.

**Body (JSON):**
```json
{
  "student_username": "2024001",
  "concept": "Inscripción Semestre 2026-1",
  "amount": 3500.00,
  "due_date": "2026-03-15T23:59:59",
  "status": "Pendiente"
}
```

Valores de `status`: `"Pendiente"`, `"Pagado"`, `"Vencido"`.

**Respuesta 200:** Objeto `PaymentWithStudent` creado.

**Errores:** `404` si el alumno no existe.

---

#### `PUT /admin/payments/{payment_id}`

Actualiza un pago.

**Parámetros de ruta:** `payment_id` — ID del pago

**Body (JSON):**
```json
{
  "concept": "string (opcional)",
  "amount": "float (opcional)",
  "due_date": "datetime (opcional)",
  "status": "string (opcional)"
}
```

**Respuesta 200:** Objeto `Payment` actualizado.

**Errores:** `404` si el pago no existe.

---

#### `GET /admin/services`

Lista todos los trámites del sistema.

**Respuesta 200:** Lista de objetos `ServiceRequestWithStudent` (trámite + datos del alumno).

---

#### `POST /admin/services`

Crea un nuevo trámite.

**Body (JSON):**
```json
{
  "student_username": "2024001",
  "type": "Constancia de estudios",
  "status": "En Proceso",
  "request_date": "2026-03-12T10:00:00"
}
```

Valores de `status`: `"En Proceso"`, `"Listo"`, `"Entregado"`.

**Respuesta 200:** Objeto `ServiceRequestWithStudent` creado.

**Errores:** `404` si el alumno no existe.

---

#### `GET /admin/services/{service_id}/attachment`

Descarga el adjunto de un trámite para administración o servicios escolares.

**Autenticación:** Bearer token (`admin` o `services`)

---

#### `PUT /admin/services/{service_id}`

Actualiza un trámite.

**Parámetros de ruta:** `service_id` — ID del trámite

**Body (JSON):**
```json
{
  "type": "string (opcional)",
  "status": "string (opcional)",
  "request_date": "datetime (opcional)"
}
```

**Respuesta 200:** Objeto `ServiceRequest` actualizado.

**Errores:** `404` si el trámite no existe.

---

### Docentes (rol `teacher` o `admin`)

#### `GET /teacher/subjects`

Lista las materias disponibles para el docente.

**Respuesta 200:** Lista de objetos `Subject`.

---

#### `GET /teacher/students/{subject_id}`

Lista los alumnos inscritos en una materia con sus calificaciones.

**Parámetros de ruta:** `subject_id` — ID de la materia

**Respuesta 200:**
```json
[
  {
    "grade_id": 1,
    "student_id": 10,
    "username": "2024001",
    "full_name": "Juan Pérez",
    "score": 8.5,
    "status": "Aprobada"
  }
]
```

---

#### `PUT /teacher/grades/{grade_id}`

Actualiza la calificación de un alumno en una materia.

**Parámetros de ruta:** `grade_id` — ID de la calificación

**Body (JSON):**
```json
{
  "score": 8.5,
  "status": "Aprobada"
}
```

**Respuesta 200:** Objeto `Grade` actualizado.

**Errores:** `404` si la calificación no existe.

---

## Códigos de error HTTP

| Código | Significado                             |
|--------|-----------------------------------------|
| 400    | Bad Request - Datos inválidos           |
| 401    | Unauthorized - Token inválido o ausente |
| 403    | Forbidden - Sin permisos                |
| 404    | Not Found - Recurso no existe           |

---

## Documentación interactiva

FastAPI genera documentación automática:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
