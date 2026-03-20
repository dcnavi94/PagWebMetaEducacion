# PagWebUnives

Proyecto de gestión académica para Unives. Este sistema permite la administración de alumnos, calificaciones y carga masiva de datos mediante un backend en FastAPI y una estructura preparada para despliegue con Docker.

## Estructura del Proyecto

```text
.
|- backend/           # API principal (FastAPI)
|  |- app/            # Lógica de la aplicación
|  |- Dockerfile      # Configuración de Docker para el backend
|  |- requirements.txt
|- public/            # Archivos estáticos o frontend
|- docker-compose.yml # Orquestación de servicios
|- README.md
```

## Requisitos

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Instrucciones de Ejecución (contenedores)

1. **Levantar los servicios:**
   Ejecuta el siguiente comando en la raíz del proyecto para iniciar el backend y los servicios necesarios:

   ```bash
   docker-compose up --build
   ```

2. **Acceder a la API:**
   La documentación automática de FastAPI estará disponible en:
   `http://localhost:8000/docs`

## Configuración

### Variables de entorno

Copia `backend/.env.example` como `backend/.env` y ajusta los valores. Docker Compose ya usa `env_file: backend/.env` para backend y base de datos, así que ahí es donde van los secretos reales:

```bash
# Windows PowerShell
Copy-Item backend/.env.example backend/.env
```

Variables críticas para producción:
- `DATABASE_URL`: Conexión a PostgreSQL.
- `SECRET_KEY`: Clave para JWT (genera una segura: `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
- `OLD_SECRET_KEYS`: Llaves previas para permitir validar tokens emitidos antes de la rotación.
- `REFRESH_TOKEN_EXPIRE_MINUTES`: Duración del refresh token (por defecto 7 días).
- `ENVIRONMENT`: `production` o `development`.
- `CORS_ORIGINS`: Orígenes permitidos (en producción restringir a dominios reales; el backend ahora falla si está en producción y `CORS_ORIGINS` es `*`).
- `ALLOWED_UPLOAD_TYPES` / `MAX_UPLOAD_SIZE_MB`: Control de tipo y tamaño de archivos subidos.
- `MAX_CSV_SIZE_MB`: Límite de tamaño para importaciones CSV.
- `LOGIN_RATE_MAX_ATTEMPTS` y `LOGIN_RATE_WINDOW_SECONDS`: Rate limiting para `/token`.

## Base de Datos

El sistema utiliza PostgreSQL. La configuración se gestiona mediante variables de entorno (ver `backend/.env.example`).

- **URL de conexión por defecto:** `postgresql://unives_user:unives_password@localhost:5433/plataforma_escolar`
- **Tablas principales:**
  - `users`: Alumnos, docentes y administradores.
  - `careers`: Carreras disponibles.
  - `modalities`: Modalidades de estudio.
  - `subjects`: Materias.
  - `grades`: Calificaciones vinculadas a alumnos y materias.
  - `payments`: Pagos realizados.
  - `service_requests`: Trámites escolares.

### Migraciones (Alembic)
- La app ya no crea tablas automáticamente con `Base.metadata.create_all`; usa migraciones versionadas.
- Ejecuta siempre `python -m alembic upgrade head` desde `backend/` después de configurar las variables de entorno  
  (probado el 2026-03-18). En Windows puedes usar `.\migrate_db.ps1` desde la raíz.
- Para nuevas modificaciones al esquema: `python -m alembic revision --autogenerate -m "descripcion"`
- Exporta `ALEMBIC_DATABASE_URL` o `DATABASE_URL` apuntando al entorno deseado antes de correr las migraciones.

## API

- Documentación detallada: ver `docs/API.md` para la especificación completa de cada endpoint.
- Documentación interactiva:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`

### Resumen de endpoints

| Categoría    | Endpoints principales |
|--------------|-----------------------|
| Autenticación| `POST /token` |
| Usuario      | `GET /users/me`, `GET /users/me/grades`, `GET /users/me/payments`, `GET /users/me/services`, `GET /users/me/courses` |
| Administración | `GET /admin/stats`, `GET/POST/PUT` alumnos, docentes, materias, pagos, trámites |
| Docente      | `GET /teacher/subjects`, `GET /teacher/students/{id}`, `PUT /teacher/grades/{id}` |

### Seguridad operativa
- **CORS:** en producción define dominios reales en `CORS_ORIGINS` (ej. `https://plataforma.unives.edu.mx,https://admin.unives.edu.mx`). Si `ENVIRONMENT=production` y `CORS_ORIGINS=*`, la app se detiene.
- **JWT y rotación de llaves:** usa `SECRET_KEY` para firmar y coloca llaves previas en `OLD_SECRET_KEYS` (separadas por coma). Política sugerida: genera nueva llave, mueve la actual a `OLD_SECRET_KEYS`, despliega; tras el TTL de los tokens viejos, elimina la llave anterior.
- **Rate limiting de login:** 5 intentos cada 15 minutos por IP (controlado con `LOGIN_RATE_MAX_ATTEMPTS` y `LOGIN_RATE_WINDOW_SECONDS`, tomando `X-Forwarded-For`).
- **Uploads/CSV:** tipos permitidos en `ALLOWED_UPLOAD_TYPES`; tamaño máximo `MAX_UPLOAD_SIZE_MB` para cualquier upload y `MAX_CSV_SIZE_MB` para importaciones. El directorio `UPLOAD_DIR` se crea automáticamente.

## Guía de desarrollo rápido (local)

1. **Activar entorno virtual**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r backend\requirements.txt
   ```

2. **Configurar variables de entorno**
   ```powershell
   Copy-Item backend/.env.example backend/.env
   # Ajusta DATABASE_URL y SECRET_KEY según tu entorno
   ```

3. **Aplicar migraciones Alembic**
   ```powershell
   cd backend
   alembic upgrade head
   cd ..
   ```

4. **Levantar la API en modo desarrollo**
   ```powershell
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Ejecutar pruebas**
   ```powershell
   cd backend
   pytest
   ```

## Seeds / Datos de demo

Para poblar la base de datos con usuarios y datos de ejemplo:

1. Asegúrate de que `DATABASE_URL` apunte a tu instancia (por ejemplo, el contenedor de Postgres levantado por `docker-compose`).
2. Ejecuta el script de seeding desde la raíz del proyecto:
   ```powershell
   cd backend
   python -m app.seed
   ```
   - Este script crea usuarios demo (admin, profesor, alumno) y datos base.
   - Para generar datos adicionales para estudiantes existentes, puedes usar:
   ```powershell
   python -m app.seed_data
   ```
3. Si usas los contenedores, el `CMD` del `backend/Dockerfile` ya ejecuta `python -m app.seed` antes de iniciar Uvicorn, por lo que tendrás datos de demo al levantar con `docker-compose`.

## Tareas Pendientes (TODO)

Estado actual del backlog principal:

- [x] Completar documentaci?n detallada de cada endpoint.
- [x] Implementar un archivo `.env` robusto para producci?n.
- [x] Implementar pruebas unitarias (pytest) y cobertura >=80%.
- [x] Configurar CI (lint + pytest + alembic check) con GitHub Actions en `.github/workflows/`.
- [x] Mejorar la interfaz del frontend.
- [ ] Mantener la suite sin warnings de compatibilidad (Pydantic V2).
- [ ] Mantener limpios los temporales de pruebas y la gu?a de contribuci?n al d?a.

## Contribuci?n y housekeeping

- Pruebas: `cd backend && pytest`.
- `basetemp`: la ruta est? fijada en `backend/pytest.ini` como `--basetemp=../temp_pytest_accessible`, as? los temporales de pytest quedan centralizados en la ra?z del repo.
- Limpieza: si quedaron residuos de ejecuciones anteriores, elimina `temp_pytest_accessible` y cualquier `pytest_tmp_*` desde la ra?z del proyecto.

## Licencia

Propiedad de Unives. Todos los derechos reservados.
