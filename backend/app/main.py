from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, DefaultDict, Deque, Dict, List, Optional, Union
from pathlib import Path
import json
import logging
import os
import re
import secrets
import string
import time
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Request, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session, aliased
from sqlalchemy import inspect, or_, and_, text

from . import models, schemas, auth
from .curriculum import ensure_subjects_for_career, get_public_curriculum
from .database import engine, get_db
from .config import settings
from .moodle_client import moodle_client

# Intentos de login por IP en memoria para rate limiting simple
_login_attempts: DefaultDict[str, Deque[datetime]] = defaultdict(deque)


def _enforce_login_rate_limit(client_ip: str) -> None:
    """Bloquea el login si se excede el numero de intentos en la ventana configurada."""
    if not client_ip:
        client_ip = "unknown"
    window_start = datetime.utcnow() - timedelta(seconds=settings.LOGIN_RATE_WINDOW_SECONDS)
    attempts = _login_attempts[client_ip]
    while attempts and attempts[0] < window_start:
        attempts.popleft()
    if len(attempts) >= settings.LOGIN_RATE_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de login. Intenta mas tarde.",
        )
    attempts.append(datetime.utcnow())


def _reset_login_attempts(client_ip: str) -> None:
    if not client_ip:
        client_ip = "unknown"
    _login_attempts.pop(client_ip, None)


def _get_client_ip(request: Request) -> str:
    """Obtiene IP real contemplando cabeceras de proxy."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _validate_upload_file(
    file: UploadFile,
    *,
    max_size_bytes: Optional[int] = None,
    allowed_types: Optional[List[str]] = None,
) -> None:
    """Valida tipo MIME y peso de archivos subidos."""
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo requerido")
    allowed = allowed_types or settings.ALLOWED_UPLOAD_TYPES
    limit = max_size_bytes or settings.max_upload_size_bytes
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Tipo de archivo no permitido",
        )
    file.file.seek(0, os.SEEK_END)
    size_bytes = file.file.tell()
    file.file.seek(0)
    if size_bytes > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo supera el limite de {limit // (1024 * 1024)}MB",
        )


def _validate_csv_upload(file: UploadFile) -> None:
    _validate_upload_file(
        file,
        max_size_bytes=settings.max_csv_size_bytes,
        allowed_types=["text/csv", "application/vnd.ms-excel"],
    )


def _service_attachment_absolute_path(relative_path: Optional[str]) -> Optional[Path]:
    if not relative_path:
        return None
    return (Path(settings.UPLOAD_DIR) / relative_path).resolve()


def _store_service_attachment(*, student_username: str, file: UploadFile) -> tuple[str, str]:
    _validate_upload_file(file)
    safe_name = Path(file.filename or "documento").name
    relative_dir = Path(student_username) / "services"
    absolute_dir = Path(settings.UPLOAD_DIR) / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}_{safe_name}"
    absolute_path = absolute_dir / stored_name
    with absolute_path.open("wb") as buffer:
        buffer.write(file.file.read())
    return safe_name, str(relative_dir / stored_name)


def _student_document_absolute_path(relative_path: Optional[str]) -> Optional[Path]:
    if not relative_path:
        return None
    return (Path(settings.UPLOAD_DIR) / relative_path).resolve()


def _store_student_document(*, student_username: str, file: UploadFile) -> tuple[str, str]:
    _validate_upload_file(file)
    safe_name = Path(file.filename or "documento").name
    relative_dir = Path(student_username) / "student_documents"
    absolute_dir = Path(settings.UPLOAD_DIR) / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}_{safe_name}"
    absolute_path = absolute_dir / stored_name
    with absolute_path.open("wb") as buffer:
        buffer.write(file.file.read())
    return safe_name, str(relative_dir / stored_name)


_portal_extensions_ready = False
_moodle_credentials_schema_ready = False


def _table_has_column(db: Session, table_name: str, column_name: str) -> bool:
    inspector = inspect(db.connection())
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _execute_schema_statement(connection, statement: str) -> None:
    normalized = " ".join(statement.strip().split())
    if connection.dialect.name == "sqlite" and "DEFAULT NOW()" in statement:
        statement = statement.replace("DEFAULT NOW()", "DEFAULT CURRENT_TIMESTAMP")
        normalized = " ".join(statement.strip().split())
    sqlite_add_column = re.match(
        r"ALTER TABLE ([A-Za-z_][A-Za-z0-9_]*) ADD COLUMN IF NOT EXISTS ([A-Za-z_][A-Za-z0-9_]*) (.+)",
        normalized,
        flags=re.IGNORECASE,
    )
    if connection.dialect.name == "sqlite" and sqlite_add_column:
        table_name, column_name, column_sql = sqlite_add_column.groups()
        inspector = inspect(connection)
        if any(column.get("name") == column_name for column in inspector.get_columns(table_name)):
            return
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"))
        return
    connection.execute(text(statement))


def _ensure_portal_extensions(db: Session) -> None:
    pass


def _ensure_runtime_schema_extensions(db: Optional[Session] = None) -> None:
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS moodle_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS curp VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS seg_unique_key VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS academic_advisor_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_moodle_id ON users (moodle_id)",
        "CREATE INDEX IF NOT EXISTS ix_users_curp ON users (curp)",
        "CREATE INDEX IF NOT EXISTS ix_users_seg_unique_key ON users (seg_unique_key)",
        "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS moodle_course_id INTEGER",
        "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS modality VARCHAR DEFAULT 'presencial'",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_subjects_moodle_course_id ON subjects (moodle_course_id)",
        "ALTER TABLE subject_assignments ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_subject_assignments_group_id ON subject_assignments (group_id)",
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS career_id INTEGER REFERENCES careers(id) ON DELETE SET NULL",
        """
        CREATE TABLE IF NOT EXISTS moodle_user_credentials (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            moodle_username VARCHAR NOT NULL,
            moodle_password VARCHAR NULL,
            updated_by VARCHAR NULL,
            password_updated_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE moodle_user_credentials ADD COLUMN IF NOT EXISTS moodle_username VARCHAR",
        "ALTER TABLE moodle_user_credentials ADD COLUMN IF NOT EXISTS moodle_password VARCHAR",
        "ALTER TABLE moodle_user_credentials ADD COLUMN IF NOT EXISTS updated_by VARCHAR",
        "ALTER TABLE moodle_user_credentials ADD COLUMN IF NOT EXISTS password_updated_at TIMESTAMP",
        "ALTER TABLE moodle_user_credentials ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
        "ALTER TABLE moodle_user_credentials ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
    ]
    if db is not None:
        pass
    else:
        with engine.begin() as connection:
            for statement in statements:
                _execute_schema_statement(connection, statement)

            if connection.dialect.name == "postgresql":
                connection.execute(text("ALTER TYPE attempt_type ADD VALUE IF NOT EXISTS 'Recursa'"))
                connection.execute(text("ALTER TYPE course_enrollment_attempt_type ADD VALUE IF NOT EXISTS 'Recursa'"))
                connection.execute(text("ALTER TABLE subject_assignments DROP CONSTRAINT IF EXISTS uq_assignment_subject_teacher_cycle"))
                connection.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM information_schema.table_constraints
                            WHERE constraint_name = 'uq_assignment_subject_teacher_cycle_group'
                              AND table_name = 'subject_assignments'
                        ) THEN
                            ALTER TABLE subject_assignments
                            ADD CONSTRAINT uq_assignment_subject_teacher_cycle_group
                            UNIQUE (subject_id, teacher_id, cycle_id, group_id);
                        END IF;
                    END$$;
                """))

            # También ejecutamos las extensiones del portal aquí en el arranque
            models.StudentDocument.__table__.create(bind=connection, checkfirst=True)
            portal_statements = [
                ("service_requests", "subject", "ALTER TABLE service_requests ADD COLUMN subject VARCHAR(180)"),
                ("service_requests", "description", "ALTER TABLE service_requests ADD COLUMN description TEXT"),
                ("service_requests", "source_system", "ALTER TABLE service_requests ADD COLUMN source_system VARCHAR(80)"),
                ("service_requests", "admin_response", "ALTER TABLE service_requests ADD COLUMN admin_response TEXT"),
                ("service_requests", "history_json", "ALTER TABLE service_requests ADD COLUMN history_json TEXT"),
                ("service_requests", "is_support_ticket", "ALTER TABLE service_requests ADD COLUMN is_support_ticket BOOLEAN DEFAULT FALSE"),
                ("service_requests", "closed_at", "ALTER TABLE service_requests ADD COLUMN closed_at TIMESTAMP"),
                ("service_requests", "updated_at", "ALTER TABLE service_requests ADD COLUMN updated_at TIMESTAMP"),
            ]
            inspector = inspect(connection)
            for table_name, column_name, sql in portal_statements:
                if not any(c.get("name") == column_name for c in inspector.get_columns(table_name)):
                    connection.execute(text(sql))


def _ensure_moodle_credentials_schema(db: Session) -> None:
    pass


def _ensure_notification_schema(db: Optional[Session] = None) -> None:
    bind = db.get_bind() if db is not None else engine
    models.NotificationMessage.__table__.create(bind=bind, checkfirst=True)
    statements = [
        "ALTER TABLE notification_messages ADD COLUMN IF NOT EXISTS target_scope VARCHAR(30) DEFAULT 'role'",
        "ALTER TABLE notification_messages ADD COLUMN IF NOT EXISTS recipient_group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE",
        "ALTER TABLE notification_messages ADD COLUMN IF NOT EXISTS category VARCHAR(30) DEFAULT 'general'",
        "ALTER TABLE notification_messages ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE",
        "ALTER TABLE notification_messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMP",
        "ALTER TABLE notification_messages ADD COLUMN IF NOT EXISTS deleted_by_recipient BOOLEAN DEFAULT FALSE",
        "ALTER TABLE notification_messages ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    ]
    if db is not None:
        connection = db.connection()
        for statement in statements:
            _execute_schema_statement(connection, statement)
        db.commit()
    else:
        with engine.begin() as connection:
            for statement in statements:
                _execute_schema_statement(connection, statement)


def _serialize_custom_notification(notification: models.NotificationMessage) -> dict:
    return {
        "id": notification.id,
        "type": "admin_message",
        "title": notification.title,
        "message": notification.message,
        "level": notification.level or "info",
        "source": notification.created_by_user.full_name if notification.created_by_user and notification.created_by_user.full_name
            else (notification.created_by_user.username if notification.created_by_user else "Administracion"),
        "action_url": notification.action_url,
        "created_at": (notification.created_at or datetime.utcnow()).isoformat(),
        "recipient_role": notification.recipient_role,
        "recipient_user_id": notification.recipient_user_id,
        "recipient_username": notification.recipient_user.username if notification.recipient_user else None,
        "recipient_group_id": notification.recipient_group_id,
        "recipient_group_name": notification.recipient_group.name if notification.recipient_group else None,
        "target_scope": notification.target_scope or "role",
        "category": notification.category or "general",
        "is_read": bool(notification.is_read),
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "deleted_by_recipient": bool(notification.deleted_by_recipient),
        "deleted_at": notification.deleted_at.isoformat() if notification.deleted_at else None,
        "can_manage": True,
    }


def _get_custom_notifications_for_user(db: Session, user: models.User) -> list[dict]:
    _ensure_notification_schema(db)
    now = datetime.utcnow()
    
    # Auto-cleanup: Eliminar notificaciones de alumnos más antiguas a 15 días
    if user.role == models.UserRole.STUDENT:
        fifteen_days_ago = now - timedelta(days=15)
        try:
            db.query(models.NotificationMessage).filter(
                models.NotificationMessage.recipient_role == models.UserRole.STUDENT,
                models.NotificationMessage.created_at < fifteen_days_ago
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()

    active_enrollment = _get_active_student_enrollment(db, user.id) if user.role == models.UserRole.STUDENT else None
    active_group_id = active_enrollment.group_id if active_enrollment else None
    rows = (
        db.query(models.NotificationMessage)
        .filter(
            models.NotificationMessage.is_active == True,
            models.NotificationMessage.recipient_role == user.role,
            or_(
                models.NotificationMessage.target_scope == "role",
                and_(models.NotificationMessage.target_scope == "user", models.NotificationMessage.recipient_user_id == user.id, models.NotificationMessage.deleted_by_recipient == False),
                and_(models.NotificationMessage.target_scope == "group", models.NotificationMessage.recipient_group_id == active_group_id) if active_group_id else False,
            ),
            or_(
                models.NotificationMessage.expires_at.is_(None),
                models.NotificationMessage.expires_at >= now,
            ),
        )
        .order_by(models.NotificationMessage.created_at.desc(), models.NotificationMessage.id.desc())
        .limit(20)
        .all()
    )
    return [_serialize_custom_notification(row) for row in rows]


def _get_user_manageable_notification(
    db: Session,
    *,
    notification_id: int,
    user: models.User,
) -> Optional[models.NotificationMessage]:
    _ensure_notification_schema(db)
    active_enrollment = _get_active_student_enrollment(db, user.id) if user.role == models.UserRole.STUDENT else None
    active_group_id = active_enrollment.group_id if active_enrollment else None
    now = datetime.utcnow()
    return (
        db.query(models.NotificationMessage)
        .filter(
            models.NotificationMessage.id == notification_id,
            models.NotificationMessage.is_active == True,
            models.NotificationMessage.recipient_role == user.role,
            or_(
                models.NotificationMessage.target_scope == "role",
                and_(models.NotificationMessage.target_scope == "user", models.NotificationMessage.recipient_user_id == user.id, models.NotificationMessage.deleted_by_recipient == False),
                and_(models.NotificationMessage.target_scope == "group", models.NotificationMessage.recipient_group_id == active_group_id) if active_group_id else False,
            ),
            or_(
                models.NotificationMessage.expires_at.is_(None),
                models.NotificationMessage.expires_at >= now,
            ),
        )
        .first()
    )


def _get_effective_student_advisor(db: Session, student: models.User) -> Optional[models.User]:
    if not student:
        return None
    if student.academic_advisor_id:
        direct_advisor = db.query(models.User).filter(models.User.id == student.academic_advisor_id).first()
        if direct_advisor and direct_advisor.role == models.UserRole.TEACHER:
            return direct_advisor
    active_enrollment = _get_active_student_enrollment(db, student.id)
    if active_enrollment and active_enrollment.group and active_enrollment.group.tutor:
        return active_enrollment.group.tutor
    return None


def _teacher_can_advise_student(db: Session, teacher_id: int, student: models.User) -> bool:
    if not student:
        return False
    if student.academic_advisor_id == teacher_id:
        return True
    active_enrollment = _get_active_student_enrollment(db, student.id)
    return bool(active_enrollment and active_enrollment.group and active_enrollment.group.tutor_id == teacher_id)


def _safe_ticket_history(raw_value: Optional[str]) -> list[dict]:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _append_ticket_history(raw_value: Optional[str], *, actor: str, action: str, message: str, status_value: Optional[str] = None) -> str:
    history = _safe_ticket_history(raw_value)
    history.insert(0, {
        "actor": actor,
        "action": action,
        "message": message,
        "status": status_value,
        "created_at": datetime.utcnow().isoformat(),
    })
    return json.dumps(history, ensure_ascii=True)


def _serialize_ticket_row(row) -> dict:
    data = dict(row._mapping)
    data["history"] = _safe_ticket_history(data.get("history_json"))
    return data


def _build_moodle_url(path: str = "") -> str:
    base = (settings.MOODLE_BASE_URL or "").rstrip("/")
    if not base:
        return ""
    if not path:
        return base
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _build_moodle_public_url(path: str = "") -> str:
    base = (settings.MOODLE_PUBLIC_URL or settings.MOODLE_BASE_URL or "").rstrip("/")
    if not base:
        return ""
    if not path:
        return base
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _get_active_student_enrollment(db: Session, student_id: int):
    return (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student_id,
            models.StudentEnrollment.is_active == True,
        )
        .order_by(models.StudentEnrollment.id.desc())
        .first()
    )


def _push_notification(items: list[dict], *, notif_type: str, title: str, message: str, level: str = "info", source: str = "Sistema", action_url: Optional[str] = None, created_at: Optional[datetime] = None) -> None:
    items.append({
        "type": notif_type,
        "title": title,
        "message": message,
        "level": level,
        "source": source,
        "action_url": action_url,
        "created_at": (created_at or datetime.utcnow()).isoformat(),
    })


def _upsert_moodle_credentials(
    db: Session,
    *,
    user_id: int,
    moodle_username: str,
    moodle_password: Optional[str],
    updated_by: str,
    overwrite_password: bool,
) -> None:
    _ensure_moodle_credentials_schema(db)
    db.execute(
        text(
            """
            INSERT INTO moodle_user_credentials (user_id, moodle_username, moodle_password, updated_by, password_updated_at, created_at, updated_at)
            VALUES (:user_id, :moodle_username, :moodle_password, :updated_by, :password_updated_at, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                moodle_username = EXCLUDED.moodle_username,
                moodle_password = CASE
                    WHEN :overwrite_password THEN EXCLUDED.moodle_password
                    ELSE moodle_user_credentials.moodle_password
                END,
                updated_by = EXCLUDED.updated_by,
                password_updated_at = CASE
                    WHEN :overwrite_password THEN EXCLUDED.password_updated_at
                    ELSE moodle_user_credentials.password_updated_at
                END,
                updated_at = NOW()
            """
        ),
        {
            "user_id": user_id,
            "moodle_username": moodle_username,
            "moodle_password": moodle_password if overwrite_password else None,
            "updated_by": updated_by,
            "password_updated_at": datetime.utcnow() if overwrite_password else None,
            "overwrite_password": bool(overwrite_password),
        },
    )
    db.commit()


def _get_moodle_credentials_for_user(db: Session, user: models.User) -> dict:
    _ensure_moodle_credentials_schema(db)
    row = db.execute(
        text(
            """
            SELECT user_id, moodle_username, moodle_password, updated_by, password_updated_at, updated_at
            FROM moodle_user_credentials
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user.id},
    ).mappings().first()
    fallback_username = (user.username or "").strip().lower()
    if not row:
        return {
            "user_id": user.id,
            "moodle_username": fallback_username,
            "moodle_password": None,
            "password_configured": False,
            "updated_by": None,
            "password_updated_at": None,
            "updated_at": None,
        }
    return {
        "user_id": row.get("user_id"),
        "moodle_username": row.get("moodle_username") or fallback_username,
        "moodle_password": row.get("moodle_password"),
        "password_configured": bool(row.get("moodle_password")),
        "updated_by": row.get("updated_by"),
        "password_updated_at": row.get("password_updated_at"),
        "updated_at": row.get("updated_at"),
    }


def _build_moodle_sync_evidence(*, entity_type: str, entity_key: str, action: str) -> dict:
    return {
        "entity_type": entity_type,
        "entity_key": entity_key,
        "action": action,
        "started_at": datetime.utcnow().isoformat(),
        "steps": [],
    }


def _append_moodle_step(evidence: dict, step: str, status: str, detail: str, **extra) -> None:
    payload = {
        "step": step,
        "status": status,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat(),
    }
    payload.update(extra)
    evidence["steps"].append(payload)


def _finalize_moodle_evidence(evidence: dict, *, success: bool) -> dict:
    evidence["success"] = success
    evidence["finished_at"] = datetime.utcnow().isoformat()
    return evidence


def _split_full_name(full_name: Optional[str]) -> tuple[str, str]:
    normalized = (full_name or "").strip() or "Usuario Moodle"
    parts = normalized.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else "Portal"
    return first_name, last_name


def _build_temp_moodle_password(username: str) -> str:
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%*"),
    ]
    alphabet = string.ascii_letters + string.digits + "!@#$%*"
    password = required + [secrets.choice(alphabet) for _ in range(10)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def _latest_moodle_error() -> Optional[str]:
    return moodle_client.get_last_error()


def _serialize_moodle_course(course: dict) -> dict:
    return {
        "id": course.get("id"),
        "shortname": course.get("shortname"),
        "fullname": course.get("fullname"),
        "displayname": course.get("displayname") or course.get("fullname"),
        "summary": course.get("summary"),
        "progress": course.get("progress"),
        "visible": course.get("visible"),
        "categoryid": course.get("categoryid"),
        "view_url": _build_moodle_public_url(f"/course/view.php?id={course.get('id')}") if course.get("id") else None,
    }


async def _find_moodle_course_by_shortname(shortname: str) -> Optional[dict]:
    if not shortname:
        return None
    courses = await moodle_client.search_courses(shortname)
    if not courses:
        return None
    lowered = shortname.strip().lower()
    for course in courses:
        if (course.get("shortname") or "").strip().lower() == lowered:
            return course
    return None


import re as _re

def _parse_semester_num(semester_str: Optional[str]) -> int:
    """Extrae el numero de semestre de strings como '1er Semestre', '2do Semestre', etc."""
    if not semester_str:
        return 0
    m = _re.search(r'\d+', str(semester_str))
    return int(m.group()) if m else 0


def _subject_order_key(subject: models.Subject) -> tuple[int, int]:
    return (_parse_semester_num(subject.semester), subject.id or 0)


def _grade_status_for_semester(subject_sem: int, student_sem: int) -> "models.GradeStatus":
    """Determina el estatus inicial de una calificacion segun el cuatrimestre."""
    if student_sem == 0 or subject_sem == 0:
        return models.GradeStatus.CURSANDO
    if subject_sem < student_sem:
        return models.GradeStatus.REPROBADA
    if subject_sem == student_sem:
        return models.GradeStatus.CURSANDO
    return models.GradeStatus.PROXIMAMENTE


def _is_passing_score(score: Optional[float]) -> bool:
    """La calificacion minima aprobatoria es 6; 5 o menos es reprobatoria."""
    return score is not None and score > 5


def _build_subject_moodle_shortname(subject: models.Subject) -> str:
    career_token = "".join(ch for ch in (subject.career or "GEN") if ch.isalnum()).upper()[:4] or "GEN"
    semester_num = _parse_semester_num(subject.semester)
    return f"UNV-{career_token}-S{semester_num}-{subject.id:04d}"


async def _sync_student_to_moodle(db: Session, *, user: models.User, password: Optional[str] = None) -> dict:
    evidence = _build_moodle_sync_evidence(entity_type="student", entity_key=user.username, action="sync_student_to_moodle")
    _append_moodle_step(evidence, "validate_user", "ok", "Alumno localizado en base local", user_id=user.id)

    first_name, last_name = _split_full_name(user.full_name)
    moodle_username = (user.username or "").strip().lower()
    chosen_password: Optional[str] = None
    moodle_id = user.moodle_id

    if moodle_id and not await moodle_client.check_user_exists(int(moodle_id)):
        _append_moodle_step(
            evidence,
            "validate_existing_link",
            "warning",
            "El moodle_id local no existe en Moodle, se recreara el vinculo",
            moodle_id=moodle_id,
            moodle_error=_latest_moodle_error(),
        )
        user.moodle_id = None
        db.add(user)
        db.commit()
        db.refresh(user)
        moodle_id = None

    if not moodle_id:
        moodle_id = await moodle_client.get_user_by_username(moodle_username)
        if not moodle_id and user.email:
            moodle_id = await moodle_client.get_user_by_email(user.email)
        if not moodle_id:
            chosen_password = password or _build_temp_moodle_password(user.username)
            moodle_id = await moodle_client.create_user(
                moodle_username,
                chosen_password,
                first_name,
                last_name,
                user.email or f"{user.username}@portal.local",
            )
            if not moodle_id:
                _append_moodle_step(
                    evidence,
                    "create_remote_user",
                    "error",
                    "Moodle no devolvio un ID de usuario",
                    moodle_error=_latest_moodle_error(),
                )
                return _finalize_moodle_evidence(evidence, success=False)
            _append_moodle_step(evidence, "create_remote_user", "ok", "Usuario creado en Moodle", moodle_id=moodle_id)

    user.moodle_id = int(moodle_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    _append_moodle_step(evidence, "persist_local_link", "ok", "moodle_id guardado localmente", moodle_id=user.moodle_id)

    _upsert_moodle_credentials(
        db,
        user_id=user.id,
        moodle_username=moodle_username,
        moodle_password=chosen_password,
        updated_by="system_sync",
        overwrite_password=bool(chosen_password),
    )
    _append_moodle_step(
        evidence,
        "role_assignment",
        "ok",
        "La cuenta se vinculo; el rol student se asignara al matricularla en un curso",
        moodle_id=user.moodle_id,
    )
    return _finalize_moodle_evidence(evidence, success=True)


async def _sync_teacher_to_moodle(db: Session, *, user: models.User, password: Optional[str] = None) -> dict:
    evidence = _build_moodle_sync_evidence(entity_type="teacher", entity_key=user.username, action="sync_teacher_to_moodle")
    _append_moodle_step(evidence, "validate_user", "ok", "Docente localizado en base local", user_id=user.id)

    first_name, last_name = _split_full_name(user.full_name)
    moodle_username = (user.username or "").strip().lower()
    chosen_password: Optional[str] = None
    moodle_id = user.moodle_id

    if moodle_id and not await moodle_client.check_user_exists(int(moodle_id)):
        user.moodle_id = None
        db.add(user)
        db.commit()
        db.refresh(user)
        moodle_id = None

    if not moodle_id:
        moodle_id = await moodle_client.get_user_by_username(moodle_username)
        if not moodle_id and user.email:
            moodle_id = await moodle_client.get_user_by_email(user.email)
        if not moodle_id:
            chosen_password = password or _build_temp_moodle_password(user.username)
            moodle_id = await moodle_client.create_user(
                moodle_username,
                chosen_password,
                first_name,
                last_name,
                user.email or f"{user.username}@portal.local",
            )
            if not moodle_id:
                _append_moodle_step(
                    evidence,
                    "create_remote_user",
                    "error",
                    "Moodle no devolvio un ID de usuario docente",
                    moodle_error=_latest_moodle_error(),
                )
                return _finalize_moodle_evidence(evidence, success=False)

    user.moodle_id = int(moodle_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    _upsert_moodle_credentials(
        db,
        user_id=user.id,
        moodle_username=moodle_username,
        moodle_password=chosen_password,
        updated_by="system_sync",
        overwrite_password=bool(chosen_password),
    )
    _append_moodle_step(
        evidence,
        "role_assignment",
        "ok",
        "La cuenta se vinculo; el rol editingteacher se asignara al matricularla en un curso",
        moodle_id=user.moodle_id,
    )
    return _finalize_moodle_evidence(evidence, success=True)


async def _sync_subject_to_moodle_internal(db: Session, *, subject: models.Subject, category_id: int = 1) -> dict:
    evidence = _build_moodle_sync_evidence(entity_type="subject", entity_key=str(subject.id), action="sync_subject_to_moodle")
    shortname = _build_subject_moodle_shortname(subject)
    moodle_course_id = subject.moodle_course_id

    if moodle_course_id and await moodle_client.check_course_exists(int(moodle_course_id)):
        _append_moodle_step(evidence, "verify_existing_course", "ok", "La materia ya estaba vinculada", moodle_course_id=moodle_course_id)
        return {
            "success": True,
            "action": "already_linked",
            "message": "La materia ya esta vinculada con Moodle",
            "moodle_course_id": moodle_course_id,
            "shortname": shortname,
            "evidence": _finalize_moodle_evidence(evidence, success=True),
        }

    existing_by_shortname = await _find_moodle_course_by_shortname(shortname)
    if existing_by_shortname and existing_by_shortname.get("id"):
        subject.moodle_course_id = int(existing_by_shortname["id"])
        db.add(subject)
        db.commit()
        db.refresh(subject)
        _append_moodle_step(evidence, "link_existing_course_by_shortname", "ok", "Curso Moodle encontrado por shortname", moodle_course_id=subject.moodle_course_id)
        return {
            "success": True,
            "action": "linked_existing_shortname",
            "message": "Materia vinculada a curso Moodle existente",
            "moodle_course_id": subject.moodle_course_id,
            "shortname": shortname,
            "evidence": _finalize_moodle_evidence(evidence, success=True),
        }

    created = await moodle_client.create_course_admin(
        fullname=subject.name or f"Materia {subject.id}",
        shortname=shortname,
        category_id=category_id,
        summary=f"Curso sincronizado desde el portal institucional para la materia #{subject.id}.",
        format_name="topics",
        visible=True,
    )
    if not created or not created.get("id"):
        _append_moodle_step(evidence, "create_course", "error", "No se pudo crear el curso en Moodle", moodle_error=_latest_moodle_error())
        return {
            "success": False,
            "action": "error",
            "message": "Error al crear curso Moodle",
            "moodle_error": _latest_moodle_error(),
            "shortname": shortname,
            "evidence": _finalize_moodle_evidence(evidence, success=False),
        }

    subject.moodle_course_id = int(created["id"])
    db.add(subject)
    db.commit()
    db.refresh(subject)
    _append_moodle_step(evidence, "create_course", "ok", "Curso creado y vinculado", moodle_course_id=subject.moodle_course_id)
    return {
        "success": True,
        "action": "created",
        "message": "Materia sincronizada exitosamente",
        "moodle_course_id": subject.moodle_course_id,
        "shortname": shortname,
        "evidence": _finalize_moodle_evidence(evidence, success=True),
    }


def _assign_curriculum_to_student(db: Session, student_id: int, career_name: Optional[str]) -> None:
    """Crea calificaciones para todas las materias de la carrera con estatus segun cuatrimestre.

    - Semestres anteriores al del alumno  → Reprobada  (admin puede editar)
    - Semestre actual del alumno          → Cursando
    - Semestres posteriores               → Proximamente
    """
    if not career_name:
        return

    ensure_subjects_for_career(db, career_name)
    subjects = (
        db.query(models.Subject)
        .filter(models.Subject.career == career_name)
        .order_by(models.Subject.semester.asc(), models.Subject.id.asc())
        .all()
    )
    if not subjects:
        return

    # Semestre actual del alumno (para asignar estatus correcto)
    student = db.query(models.User).filter(models.User.id == student_id).first()
    student_sem = _parse_semester_num(student.semestre if student else None)

    active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()

    student_grades = (
        db.query(models.Grade)
        .filter(models.Grade.student_id == student_id)
        .all()
    )
    existing_subject_ids = {grade.subject_id for grade in student_grades}
    placeholder_grades_by_subject_id = {
        grade.subject_id: grade
        for grade in student_grades
        if grade.subject_id is not None
        and grade.attempt_type == models.AttemptType.REGULAR
        and grade.score is None
        and grade.recorded_at is None
        and grade.course_enrollment_id is None
        and not grade.teacher_locked
    }

    if active_cycle:
        # Asignaciones existentes del ciclo activo para las materias de esta carrera
        assignments = (
            db.query(models.SubjectAssignment)
            .join(models.Subject)
            .filter(
                models.Subject.career == career_name,
                models.SubjectAssignment.cycle_id == active_cycle.id,
            )
            .all()
        )

        existing_assignment_ids = {
            g.assignment_id
            for g in db.query(models.Grade).filter(
                models.Grade.student_id == student_id,
                models.Grade.assignment_id.isnot(None),
            ).all()
        }

        # Materias con asignación → usar estatus por cuatrimestre
        assigned_subject_ids = set()
        for assignment in assignments:
            subject_sem = _parse_semester_num(assignment.subject.semester if assignment.subject else None)
            status = _grade_status_for_semester(subject_sem, student_sem)
            if assignment.id in existing_assignment_ids:
                placeholder = placeholder_grades_by_subject_id.get(assignment.subject_id)
                if placeholder and placeholder.status != status:
                    placeholder.status = status
                assigned_subject_ids.add(assignment.subject_id)
                continue
            placeholder = placeholder_grades_by_subject_id.get(assignment.subject_id)
            if placeholder:
                placeholder.assignment_id = assignment.id
                placeholder.status = status
                assigned_subject_ids.add(assignment.subject_id)
                continue
            db.add(
                models.Grade(
                    student_id=student_id,
                    subject_id=assignment.subject_id,
                    assignment_id=assignment.id,
                    attempt_type=models.AttemptType.REGULAR,
                    score=None,
                    status=status,
                )
            )
            assigned_subject_ids.add(assignment.subject_id)

        # Materias sin asignación → crear grade sin assignment_id con estatus por cuatrimestre
        for subject in subjects:
            if subject.id in assigned_subject_ids:
                continue
            subject_sem = _parse_semester_num(subject.semester)
            status = _grade_status_for_semester(subject_sem, student_sem)
            placeholder = placeholder_grades_by_subject_id.get(subject.id)
            if placeholder:
                if placeholder.status != status:
                    placeholder.status = status
                continue
            if subject.id in existing_subject_ids:
                continue
            db.add(
                models.Grade(
                    student_id=student_id,
                    subject_id=subject.id,
                    attempt_type=models.AttemptType.REGULAR,
                    score=None,
                    status=status,
                )
            )
    else:
        # Sin ciclo activo: inscribir todas las materias con estatus por cuatrimestre
        for subject in subjects:
            subject_sem = _parse_semester_num(subject.semester)
            status = _grade_status_for_semester(subject_sem, student_sem)
            placeholder = placeholder_grades_by_subject_id.get(subject.id)
            if placeholder:
                if placeholder.status != status:
                    placeholder.status = status
                continue
            if subject.id in existing_subject_ids:
                continue
            db.add(
                models.Grade(
                    student_id=student_id,
                    subject_id=subject.id,
                    attempt_type=models.AttemptType.REGULAR,
                    score=None,
                    status=status,
                )
            )


def _get_active_cycle(db: Session) -> Optional[models.SchoolCycle]:
    return db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).order_by(models.SchoolCycle.id.desc()).first()


def _has_enrollment_seed_data(student: models.User) -> bool:
    return any([
        student.career_id,
        student.carrera,
        student.modality_id,
        student.modalidad,
        student.semestre,
        student.grupo,
        student.enrollment_status != models.EnrollmentStatus.NO_INSCRITO,
    ])


def _is_active_enrollment_status(enrollment_status: models.EnrollmentStatus) -> bool:
    return enrollment_status == models.EnrollmentStatus.INSCRITO


def _ensure_single_active_enrollment_per_cycle(
    db: Session,
    *,
    student_id: int,
    cycle_id: int,
    current_enrollment_id: Optional[int] = None,
    enrollment_status: models.EnrollmentStatus,
) -> None:
    if not _is_active_enrollment_status(enrollment_status):
        return

    active_enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student_id,
            models.StudentEnrollment.cycle_id == cycle_id,
            models.StudentEnrollment.id != (current_enrollment_id or 0),
            models.StudentEnrollment.is_active == True,
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
        )
        .first()
    )
    if active_enrollment:
        raise HTTPException(
            status_code=400,
            detail="El alumno ya tiene una inscripcion activa en este ciclo escolar",
        )


def _get_or_create_group(
    db: Session,
    *,
    group_name: Optional[str],
    modality_id: Optional[int] = None,
) -> Optional[models.Group]:
    if not group_name:
        return None
    normalized = group_name.strip()
    if not normalized:
        return None

    group = (
        db.query(models.Group)
        .filter(
            models.Group.name == normalized,
            models.Group.modality_id == modality_id,
        )
        .first()
    )
    if group:
        return group

    group = models.Group(name=normalized, modality_id=modality_id)
    db.add(group)
    db.flush()
    return group


def _sync_student_enrollment_from_legacy(
    db: Session,
    student: models.User,
    *,
    cycle_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> Optional[models.StudentEnrollment]:
    if student.role != models.UserRole.STUDENT:
        return None

    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id
        else _get_active_cycle(db)
    )
    if not cycle:
        return None

    enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student.id,
            models.StudentEnrollment.cycle_id == cycle.id,
        )
        .first()
    )
    if not enrollment and not _has_enrollment_seed_data(student):
        return None

    group = _get_or_create_group(
        db,
        group_name=student.grupo,
        modality_id=student.modality_id,
    )

    if not enrollment:
        enrollment = models.StudentEnrollment(
            student_id=student.id,
            cycle_id=cycle.id,
        )
        db.add(enrollment)

    enrollment.career_id = student.career_id
    enrollment.modality_id = student.modality_id
    enrollment.group_id = group.id if group else None
    enrollment.semester = student.semestre
    _ensure_single_active_enrollment_per_cycle(
        db,
        student_id=student.id,
        cycle_id=cycle.id,
        current_enrollment_id=enrollment.id,
        enrollment_status=student.enrollment_status,
    )
    enrollment.enrollment_status = student.enrollment_status
    enrollment.is_active = student.user_status != models.UserStatus.BAJA and _is_active_enrollment_status(student.enrollment_status)
    if reason:
        enrollment.change_reason = reason
    db.flush()
    return enrollment


def _get_or_create_student_enrollment_for_cycle(
    db: Session,
    student: models.User,
    cycle_id: Optional[int],
    *,
    reason: Optional[str] = None,
) -> models.StudentEnrollment:
    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id
        else _get_active_cycle(db)
    )
    if not cycle:
        raise HTTPException(status_code=404, detail="No hay ciclo escolar activo")

    enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student.id,
            models.StudentEnrollment.cycle_id == cycle.id,
        )
        .first()
    )
    if enrollment:
        return enrollment

    enrollment = _sync_student_enrollment_from_legacy(
        db,
        student,
        cycle_id=cycle.id,
        reason=reason,
    )
    if enrollment:
        return enrollment

    enrollment = models.StudentEnrollment(
        student_id=student.id,
        cycle_id=cycle.id,
        career_id=student.career_id,
        modality_id=student.modality_id,
        semester=student.semestre,
        enrollment_status=student.enrollment_status,
        is_active=student.user_status != models.UserStatus.BAJA and _is_active_enrollment_status(student.enrollment_status),
        change_reason=reason,
    )
    db.add(enrollment)
    db.flush()
    return enrollment


def _assignment_group_label(assignment: Optional[models.SubjectAssignment]) -> str:
    if assignment and assignment.group and assignment.group.name:
        return assignment.group.name
    return "Sin grupo"


def _validate_assignment_group_for_enrollment(
    *,
    student_enrollment: models.StudentEnrollment,
    assignment: models.SubjectAssignment,
    attempt_type: models.AttemptType,
) -> None:
    if not assignment.group_id:
        return

    current_group_id = student_enrollment.group_id
    is_regular_attempt = attempt_type == models.AttemptType.REGULAR

    if current_group_id is None and is_regular_attempt:
        student_enrollment.group_id = assignment.group_id
        return

    if current_group_id == assignment.group_id:
        return

    if is_regular_attempt:
        raise HTTPException(
            status_code=400,
            detail=f"El alumno pertenece a otro grupo del ciclo activo. Debe inscribirse en la asignación de su grupo ({_assignment_group_label(assignment)}).",
        )


def _get_or_create_course_enrollment(
    db: Session,
    *,
    student: models.User,
    assignment: models.SubjectAssignment,
    attempt_type: models.AttemptType,
    status: models.GradeStatus,
) -> models.CourseEnrollment:
    student_enrollment = _get_or_create_student_enrollment_for_cycle(
        db,
        student,
        assignment.cycle_id,
        reason="Inscripcion academica automatica",
    )
    _validate_assignment_group_for_enrollment(
        student_enrollment=student_enrollment,
        assignment=assignment,
        attempt_type=attempt_type,
    )
    course_enrollment = (
        db.query(models.CourseEnrollment)
        .filter(
            models.CourseEnrollment.student_enrollment_id == student_enrollment.id,
            models.CourseEnrollment.assignment_id == assignment.id,
            models.CourseEnrollment.attempt_type == attempt_type,
        )
        .first()
    )
    if course_enrollment:
        if course_enrollment.status != status:
            course_enrollment.status = status
        return course_enrollment

    course_enrollment = models.CourseEnrollment(
        student_enrollment_id=student_enrollment.id,
        assignment_id=assignment.id,
        attempt_type=attempt_type,
        status=status,
    )
    db.add(course_enrollment)
    db.flush()
    return course_enrollment


def _ensure_grade_record_for_course_enrollment(
    db: Session,
    *,
    student: models.User,
    assignment: models.SubjectAssignment,
    course_enrollment: models.CourseEnrollment,
    status: models.GradeStatus,
) -> models.Grade:
    grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.course_enrollment_id == course_enrollment.id,
        )
        .first()
    )
    if grade:
        if grade.status != status:
            grade.status = status
        return grade

    grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.assignment_id == assignment.id,
            models.Grade.attempt_type == course_enrollment.attempt_type,
        )
        .first()
    )
    if grade:
        grade.course_enrollment_id = course_enrollment.id
        if grade.status != status:
            grade.status = status
        return grade

    grade = models.Grade(
        student_id=student.id,
        subject_id=assignment.subject_id,
        assignment_id=assignment.id,
        course_enrollment_id=course_enrollment.id,
        attempt_type=course_enrollment.attempt_type,
        status=status,
    )
    db.add(grade)
    db.flush()
    return grade


def _create_admin_course_enrollment(
    db: Session,
    *,
    student: models.User,
    assignment: models.SubjectAssignment,
    attempt_type: models.AttemptType,
    status: models.GradeStatus,
    create_grade_record: bool = True,
) -> models.CourseEnrollment:
    student_enrollment = _get_or_create_student_enrollment_for_cycle(
        db,
        student,
        assignment.cycle_id,
        reason="Inscripcion academica administrativa",
    )
    _validate_assignment_group_for_enrollment(
        student_enrollment=student_enrollment,
        assignment=assignment,
        attempt_type=attempt_type,
    )

    existing = (
        db.query(models.CourseEnrollment)
        .filter(
            models.CourseEnrollment.student_enrollment_id == student_enrollment.id,
            models.CourseEnrollment.assignment_id == assignment.id,
            models.CourseEnrollment.attempt_type == attempt_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="El alumno ya esta inscrito en esta materia para la misma oportunidad")

    course_enrollment = models.CourseEnrollment(
        student_enrollment_id=student_enrollment.id,
        assignment_id=assignment.id,
        attempt_type=attempt_type,
        status=status,
    )
    db.add(course_enrollment)
    db.flush()

    if create_grade_record:
        _ensure_grade_record_for_course_enrollment(
            db,
            student=student,
            assignment=assignment,
            course_enrollment=course_enrollment,
            status=status,
        )

    return course_enrollment


def _apply_grade_payload(
    grade: models.Grade,
    grade_update: schemas.GradeUpdate,
    *,
    lock_for_teacher: bool = False,
) -> None:
    if grade_update.score is not None:
        grade.score = grade_update.score
        grade.status = (
            models.GradeStatus.APROBADA if _is_passing_score(grade_update.score)
            else models.GradeStatus.REPROBADA
        )
        grade.recorded_at = datetime.utcnow()
    elif grade_update.status is not None:
        grade.status = grade_update.status
        if grade.recorded_at is None and grade_update.status != models.GradeStatus.CURSANDO:
            grade.recorded_at = datetime.utcnow()

    if lock_for_teacher and (grade.score is not None or grade.status != models.GradeStatus.CURSANDO):
        grade.teacher_locked = True

    if grade.course_enrollment:
        grade.course_enrollment.status = grade.status


def _get_grade_for_course_enrollment(course_enrollment: models.CourseEnrollment) -> Optional[models.Grade]:
    if not course_enrollment.grades:
        return None
    ordered = sorted(
        course_enrollment.grades,
        key=lambda grade: (
            grade.recorded_at or datetime.min,
            grade.id,
        ),
        reverse=True,
    )
    return ordered[0]


def _get_teacher_name_from_assignment(assignment: Optional[models.SubjectAssignment]) -> Optional[str]:
    if assignment and assignment.teacher:
        return assignment.teacher.full_name or assignment.teacher.username
    return None


def _attempt_type_sort_key(attempt_type: Optional[Union[models.AttemptType, str]]) -> int:
    normalized = str(attempt_type or "")
    if normalized == models.AttemptType.EXTEMPORANEO.value:
        return 3
    if normalized == models.AttemptType.RECURSA.value:
        return 2
    if normalized == models.AttemptType.REGULAR.value:
        return 1
    return 0


def _status_sort_key(status_value: Optional[Union[models.GradeStatus, str]]) -> int:
    normalized = str(status_value or "")
    if normalized == models.GradeStatus.APROBADA.value:
        return 4
    if normalized == models.GradeStatus.CURSANDO.value:
        return 3
    if normalized == models.GradeStatus.REPROBADA.value:
        return 2
    if normalized == models.GradeStatus.PROXIMAMENTE.value:
        return 1
    return 0


def _effective_student_grade_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[object, str], dict] = {}
    for row in rows:
        key = (
            row.get("subject_id") or row.get("description") or row.get("subject_name") or row.get("assignment_id") or row.get("grade_id"),
            row.get("description") or row.get("subject_name") or "",
        )
        current = grouped.get(key)
        candidate_rank = (
            _status_sort_key(row.get("status")),
            _attempt_type_sort_key(row.get("attempt_type")),
            1 if row.get("course_enrollment_id") else 0,
            1 if row.get("assignment_id") else 0,
            row.get("grade_id") or 0,
        )
        if not current:
            grouped[key] = row
            continue
        current_rank = (
            _status_sort_key(current.get("status")),
            _attempt_type_sort_key(current.get("attempt_type")),
            1 if current.get("course_enrollment_id") else 0,
            1 if current.get("assignment_id") else 0,
            current.get("grade_id") or 0,
        )
        if candidate_rank > current_rank:
            grouped[key] = row

    result = [r for r in list(grouped.values()) if r.get("status") not in (models.GradeStatus.PROXIMAMENTE, "Proximamente")]
    result.sort(
        key=lambda item: (
            _parse_semester_num(item.get("period") or item.get("semester")),
            (item.get("description") or item.get("subject_name") or "").lower(),
            item.get("grade_id") or 0,
        )
    )
    return result


def _serialize_grade_row(
    *,
    grade: Optional[models.Grade] = None,
    course_enrollment: Optional[models.CourseEnrollment] = None,
) -> dict:
    assignment = course_enrollment.assignment if course_enrollment else (grade.assignment if grade else None)
    subject = assignment.subject if assignment and assignment.subject else (grade.subject if grade else None)
    teacher_name = _get_teacher_name_from_assignment(assignment)

    status = grade.status if grade else (course_enrollment.status if course_enrollment else None)
    attempt_type = grade.attempt_type if grade else (course_enrollment.attempt_type if course_enrollment else None)
    score = grade.score if grade and grade.score is not None else None

    return {
        "grade_id": grade.id if grade else None,
        "course_enrollment_id": course_enrollment.id if course_enrollment else (grade.course_enrollment_id if grade else None),
        "assignment_id": assignment.id if assignment else (grade.assignment_id if grade else None),
        "subject_id": subject.id if subject else None,
        "period": subject.semester if subject else None,
        "description": subject.name if subject else None,
        "credits": subject.credits if subject else None,
        "score": score,
        "status": status,
        "teacher": teacher_name,
        "attempt_type": attempt_type,
        "group": assignment.group.name if assignment and assignment.group else None,
    }


def _serialize_course_card(
    course_enrollment: models.CourseEnrollment,
    grade: Optional[models.Grade],
) -> dict:
    assignment = course_enrollment.assignment
    subject = assignment.subject if assignment else (grade.subject if grade else None)
    teacher_name = _get_teacher_name_from_assignment(assignment) or "Docente no asignado"
    status = grade.status if grade else course_enrollment.status
    score = grade.score if grade and grade.score is not None else 0

    return {
        "id": subject.id if subject else None,
        "course_enrollment_id": course_enrollment.id,
        "grade_id": grade.id if grade else None,
        "assignment_id": assignment.id if assignment else None,
        "group_id": assignment.group_id if assignment else None,
        "name": subject.name if subject else None,
        "progress": 100 if status == models.GradeStatus.APROBADA else (40 if status == models.GradeStatus.CURSANDO else 0),
        "score": score,
        "professor": teacher_name,
        "semester": subject.semester if subject else None,
        "credits": subject.credits if subject else None,
        "status": status,
        "attempt_type": grade.attempt_type if grade else course_enrollment.attempt_type,
        "group": assignment.group.name if assignment and assignment.group else None,
    }


def _subject_is_virtual_classroom_enabled(subject: Optional[models.Subject]) -> bool:
    if not subject:
        return False
    modality = (subject.modality or "").strip().lower()
    return bool(subject.moodle_course_id) or modality in {"virtual", "hibrido", "híbrido"}


def _serialize_academic_history_item(
    *,
    grade: Optional[models.Grade] = None,
    course_enrollment: Optional[models.CourseEnrollment] = None,
) -> dict:
    assignment = course_enrollment.assignment if course_enrollment else (grade.assignment if grade else None)
    subject = assignment.subject if assignment and assignment.subject else (grade.subject if grade else None)
    cycle = None
    if assignment and assignment.cycle:
        cycle = assignment.cycle.period
    elif course_enrollment and course_enrollment.student_enrollment and course_enrollment.student_enrollment.cycle:
        cycle = course_enrollment.student_enrollment.cycle.period

    return {
        "grade_id": grade.id if grade else None,
        "course_enrollment_id": course_enrollment.id if course_enrollment else (grade.course_enrollment_id if grade else None),
        "assignment_id": assignment.id if assignment else (grade.assignment_id if grade else None),
        "subject_id": subject.id if subject else None,
        "subject_name": subject.name if subject else None,
        "semester": subject.semester if subject else None,
        "credits": subject.credits if subject else None,
        "cycle": cycle,
        "teacher": _get_teacher_name_from_assignment(assignment),
        "attempt_type": grade.attempt_type if grade else (course_enrollment.attempt_type if course_enrollment else None),
        "final_score": grade.score if grade else None,
        "status": grade.status if grade else (course_enrollment.status if course_enrollment else None),
        "dropped_at": course_enrollment.dropped_at if course_enrollment else None,
        "group": assignment.group.name if assignment and assignment.group else None,
    }


def _should_include_legacy_grade_in_student_view(grade: models.Grade) -> bool:
    """Oculta del portal del alumno las filas placeholder de currícula no inscrita.

    Se muestran solo si la materia tiene una asignación/carga real o evidencia de
    evaluación histórica capturada.
    """
    if grade.course_enrollment_id or grade.assignment_id:
        return True
    if grade.score is not None or grade.recorded_at is not None:
        return True
    return False


def _get_academic_history_for_student(db: Session, student_id: int) -> list[dict]:
    history = []
    seen_grade_ids = set()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == student_id)
        .all()
    )
    for course_enrollment in course_enrollments:
        grade = _get_grade_for_course_enrollment(course_enrollment)
        if grade:
            seen_grade_ids.add(grade.id)
        history.append(_serialize_academic_history_item(grade=grade, course_enrollment=course_enrollment))

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == student_id).all()
    for grade in legacy_grades:
        if grade.id in seen_grade_ids:
            continue
        history.append(_serialize_academic_history_item(grade=grade))

    history.sort(
        key=lambda item: (
            item["cycle"] or "",
            item["semester"] or "",
            item["subject_name"] or "",
            item["grade_id"] or 0,
        )
    )
    return history


def _get_student_enrollment_for_charge(
    db: Session,
    *,
    student: models.User,
    cycle_id: Optional[int] = None,
    student_enrollment_id: Optional[int] = None,
) -> Optional[models.StudentEnrollment]:
    if student_enrollment_id is not None:
        return (
            db.query(models.StudentEnrollment)
            .filter(
                models.StudentEnrollment.id == student_enrollment_id,
                models.StudentEnrollment.student_id == student.id,
            )
            .first()
        )

    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id is not None
        else _get_active_cycle(db)
    )
    if not cycle:
        return None

    return (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student.id,
            models.StudentEnrollment.cycle_id == cycle.id,
        )
        .first()
    )


def _get_group_member_enrollments(
    db: Session,
    *,
    group_name: str,
    cycle_id: Optional[int] = None,
    career_name: Optional[str] = None,
    usernames: Optional[list[str]] = None,
) -> tuple[list[models.StudentEnrollment], models.SchoolCycle]:
    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id is not None
        else _get_active_cycle(db)
    )
    if not cycle:
        raise HTTPException(status_code=404, detail="No hay ciclo escolar activo")

    query = (
        db.query(models.StudentEnrollment)
        .join(models.Group, models.Group.id == models.StudentEnrollment.group_id)
        .join(models.User, models.User.id == models.StudentEnrollment.student_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .filter(
            models.StudentEnrollment.cycle_id == cycle.id,
            models.Group.name == group_name,
            models.User.role == models.UserRole.STUDENT,
        )
    )

    normalized_career = (career_name or "").strip()
    if normalized_career:
        query = query.filter(models.Career.name == normalized_career)

    if usernames:
        query = query.filter(models.User.username.in_(usernames))

    return query.all(), cycle


def _ensure_payment_for_charge(db: Session, charge: models.Charge) -> models.Payment:
    payment = (
        db.query(models.Payment)
        .filter(models.Payment.charge_id == charge.id)
        .first()
    )
    if not payment:
        payment = models.Payment(student_id=charge.student_id, charge_id=charge.id)
        db.add(payment)

    payment.concept = charge.concept
    payment.amount = charge.amount
    payment.due_date = charge.due_date
    payment.status = charge.status
    db.flush()
    return payment


def _ensure_unique_charge_for_enrollment_period(
    db: Session,
    *,
    student_enrollment_id: Optional[int],
    concept: str,
    period_label: Optional[str],
    current_charge_id: Optional[int] = None,
) -> None:
    if student_enrollment_id is None:
        return

    duplicate = (
        db.query(models.Charge)
        .filter(
            models.Charge.student_enrollment_id == student_enrollment_id,
            models.Charge.concept == concept,
            models.Charge.period_label == period_label,
            models.Charge.id != (current_charge_id or 0),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="Ya existe un cargo para esa inscripcion y periodo")


class JsonFormatter(logging.Formatter):
    """Formato JSON compacto para logs estructurados."""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                log[key] = value
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=True)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("unives.api")
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Validar configuracion en produccion
if settings.is_production:
    settings.validate_production()

# Origenes CORS: "*" o lista separada por coma
_cors_origins = settings.cors_origins

app = FastAPI(
    title="Plataforma Escolar Unives API",
    description="API de gestion academica: alumnos, docentes, materias, calificaciones, pagos y tramites.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_runtime_schema_extensions() -> None:
    _ensure_runtime_schema_extensions()
    _ensure_notification_schema()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
admin_required = auth.require_roles(models.UserRole.ADMIN)
teacher_or_admin = auth.require_roles(models.UserRole.TEACHER, models.UserRole.ADMIN)
services_or_admin = auth.require_roles(models.UserRole.SERVICES, models.UserRole.ADMIN)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = int((time.time() - start) * 1000)
        status_code = response.status_code if response else 500
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client": _get_client_ip(request),
            },
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    error_id = str(uuid4())
    logger.warning(
        "http_error",
        extra={
            "error_id": error_id,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"id": error_id, "message": exc.detail, "status_code": exc.status_code}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid4())
    logger.exception(
        "unhandled_error",
        extra={"error_id": error_id, "path": request.url.path},
    )
    message = str(exc) if settings.DEBUG else "Error interno. Revisa logs con el id proporcionado."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"id": error_id, "message": message, "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}},
    )


def _resolve_report_cycle(db: Session, cycle_id: Optional[int] = None):
    return (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id is not None
        else _get_active_cycle(db)
    )


def _parse_report_datetime(value: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Formato de fecha invalido. Usa YYYY-MM-DD") from exc
    if len(value) <= 10:
        if end_of_day:
            return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed


def _apply_datetime_range(query, column, date_from: Optional[str] = None, date_to: Optional[str] = None):
    start = _parse_report_datetime(date_from)
    end = _parse_report_datetime(date_to, end_of_day=True)
    if start:
        query = query.filter(column >= start)
    if end:
        query = query.filter(column <= end)
    return query


def _datetime_in_range(value: Optional[datetime], date_from: Optional[str] = None, date_to: Optional[str] = None) -> bool:
    if value is None:
        return not date_from and not date_to
    start = _parse_report_datetime(date_from)
    end = _parse_report_datetime(date_to, end_of_day=True)
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


def _filtered_student_enrollments_query(
    db: Session,
    *,
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    cycle = _resolve_report_cycle(db, cycle_id)
    query = (
        db.query(models.StudentEnrollment)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    if cycle:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle.id)
    if career:
        query = query.filter(models.Career.name == career)
    if modality:
        query = query.filter(models.Modality.name == modality)
    if semester:
        query = query.filter(models.StudentEnrollment.semester == semester)
    if group_name:
        query = query.filter(models.Group.name == group_name)
    query = _apply_datetime_range(query, models.StudentEnrollment.created_at, date_from, date_to)
    return query, cycle


def _grade_matches_filters(
    grade: models.Grade,
    *,
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    teacher_username: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> bool:
    assignment = grade.assignment
    course_enrollment = grade.course_enrollment
    student_enrollment = course_enrollment.student_enrollment if course_enrollment else None
    effective_date = grade.recorded_at or (
        student_enrollment.created_at if student_enrollment else None
    )

    if cycle_id is not None and assignment and assignment.cycle_id != cycle_id:
        return False
    if teacher_username and assignment and assignment.teacher and assignment.teacher.username != teacher_username:
        return False
    if career and student_enrollment and student_enrollment.career and student_enrollment.career.name != career:
        return False
    if modality and student_enrollment and student_enrollment.modality and student_enrollment.modality.name != modality:
        return False
    if semester and student_enrollment and student_enrollment.semester != semester:
        return False
    if group_name and student_enrollment and student_enrollment.group and student_enrollment.group.name != group_name:
        return False
    if not _datetime_in_range(effective_date, date_from, date_to):
        return False
    return True


@app.get("/", summary="Estado del API")
def root():
    return {"message": "Plataforma Escolar Unives API operativa"}


@app.get("/")
def read_root():
    return {"message": "Bienvenido a la API de la Plataforma Escolar Unives"}



# --- Include Routers ---
from app.routers import auth
app.include_router(auth.router)
from app.routers import users
app.include_router(users.router)
from app.routers import admin_students
app.include_router(admin_students.router)
from app.routers import admin_academics
app.include_router(admin_academics.router)
from app.routers import admin_reports
app.include_router(admin_reports.router)
from app.routers import catalogs
app.include_router(catalogs.router)
from app.routers import config
app.include_router(config.router)
from app.routers import web_management
app.include_router(web_management.router)
from app.routers import schedules
app.include_router(schedules.router)
from app.routers import laboratory
app.include_router(laboratory.router)
from app.routers import library
app.include_router(library.router)



# --- Include Routers ---
from app.routers import admin_teachers
app.include_router(admin_teachers.router)
from app.routers import admin_subjects
app.include_router(admin_subjects.router)
from app.routers import admin_finances
app.include_router(admin_finances.router)
from app.routers import admin_services
app.include_router(admin_services.router)
from app.routers import admin_moodle
app.include_router(admin_moodle.router)
from app.routers import admin_notifications
app.include_router(admin_notifications.router)
from app.routers import admin_misc
app.include_router(admin_misc.router)
from app.routers import teacher
app.include_router(teacher.router)



# --- Include Routers ---
from app.routers import admin_academics
app.include_router(admin_academics.router)
from app.routers import admin_finances
app.include_router(admin_finances.router)
from app.routers import admin_misc
app.include_router(admin_misc.router)
from app.routers import admin_moodle
app.include_router(admin_moodle.router)
from app.routers import admin_notifications
app.include_router(admin_notifications.router)
from app.routers import admin_reports
app.include_router(admin_reports.router)
from app.routers import admin_services
app.include_router(admin_services.router)
from app.routers import admin_students
app.include_router(admin_students.router)
from app.routers import admin_subjects
app.include_router(admin_subjects.router)
from app.routers import admin_teachers
app.include_router(admin_teachers.router)
from app.routers import admin_web
app.include_router(admin_web.router)
from app.routers import auth
app.include_router(auth.router)
from app.routers import catalogs
app.include_router(catalogs.router)
from app.routers import config
app.include_router(config.router)
from app.routers import public_web
app.include_router(public_web.router)
from app.routers import teacher
app.include_router(teacher.router)
from app.routers import users
app.include_router(users.router)
from app.routers import web_management
app.include_router(web_management.router)
