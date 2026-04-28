from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, DefaultDict, Deque, Dict, List, Optional, Union
from pathlib import Path
import json
import logging
import os
import time
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Request, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session, aliased
from sqlalchemy import inspect, or_, text

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


_portal_extensions_ready = False
_moodle_credentials_schema_ready = False


def _table_has_column(db: Session, table_name: str, column_name: str) -> bool:
    inspector = inspect(db.connection())
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _ensure_portal_extensions(db: Session) -> None:
    pass


def _ensure_runtime_schema_extensions(db: Optional[Session] = None) -> None:
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS moodle_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS academic_advisor_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_moodle_id ON users (moodle_id)",
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
                connection.execute(text(statement))

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
    ]
    if db is not None:
        for statement in statements:
            db.execute(text(statement))
        db.commit()
    else:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))


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
        "can_manage": True,
    }


def _get_custom_notifications_for_user(db: Session, user: models.User) -> list[dict]:
    _ensure_notification_schema(db)
    now = datetime.utcnow()
    active_enrollment = _get_active_student_enrollment(db, user.id) if user.role == models.UserRole.STUDENT else None
    active_group_id = active_enrollment.group_id if active_enrollment else None
    rows = (
        db.query(models.NotificationMessage)
        .filter(
            models.NotificationMessage.is_active == True,
            models.NotificationMessage.recipient_role == user.role,
            or_(
                models.NotificationMessage.target_scope == "role",
                models.NotificationMessage.recipient_user_id == user.id,
                models.NotificationMessage.recipient_group_id == active_group_id if active_group_id else False,
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
                models.NotificationMessage.recipient_user_id == user.id,
                models.NotificationMessage.recipient_group_id == active_group_id if active_group_id else False,
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
    suffix = "".join(ch for ch in (username or "Alumno").strip() if ch.isalnum())[:6] or "Alumno"
    return f"Portal#{suffix}2026!"


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

    role_assigned = await moodle_client.assign_system_role(
        user_id=int(user.moodle_id),
        role_id=settings.MOODLE_STUDENT_ROLE_ID,
        context_level=settings.MOODLE_ROLE_CONTEXT_LEVEL,
        instance_id=settings.MOODLE_ROLE_INSTANCE_ID or None,
    )
    if not role_assigned:
        _append_moodle_step(evidence, "assign_role", "error", "No se pudo asignar rol student", moodle_error=_latest_moodle_error())
        return _finalize_moodle_evidence(evidence, success=False)

    _upsert_moodle_credentials(
        db,
        user_id=user.id,
        moodle_username=moodle_username,
        moodle_password=chosen_password,
        updated_by="system_sync",
        overwrite_password=bool(chosen_password),
    )
    _append_moodle_step(evidence, "assign_role", "ok", "Rol student asignado", moodle_id=user.moodle_id)
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
    role_assigned = await moodle_client.assign_system_role(
        user_id=int(user.moodle_id),
        role_id=settings.MOODLE_TEACHER_ROLE_ID,
        context_level=settings.MOODLE_ROLE_CONTEXT_LEVEL,
        instance_id=settings.MOODLE_ROLE_INSTANCE_ID or None,
    )
    if not role_assigned:
        _append_moodle_step(evidence, "assign_role", "error", "No se pudo asignar rol teacher", moodle_error=_latest_moodle_error())
        return _finalize_moodle_evidence(evidence, success=False)

    _upsert_moodle_credentials(
        db,
        user_id=user.id,
        moodle_username=moodle_username,
        moodle_password=chosen_password,
        updated_by="system_sync",
        overwrite_password=bool(chosen_password),
    )
    _append_moodle_step(evidence, "assign_role", "ok", "Rol teacher asignado", moodle_id=user.moodle_id)
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

    result = list(grouped.values())
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


@app.get("/", summary="Estado del API")
def root():
    return {"message": "Plataforma Escolar Unives API operativa"}


@app.get("/catalogs/careers", response_model=list[schemas.Career], summary="Catalogo de carreras", tags=["Catalogos"])
def list_careers(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las carreras almacenadas en la base de datos."""
    return db.query(models.Career).order_by(models.Career.name).all()


@app.post("/admin/catalogs/careers", response_model=schemas.Career, summary="Crear carrera", tags=["Catalogos"])
def create_career(
    career: schemas.CareerCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Career).filter(models.Career.name == career.name).first()
    if existing:
        return existing

    new_career = models.Career(name=career.name, description=career.description)
    db.add(new_career)
    db.commit()
    db.refresh(new_career)
    return new_career


@app.get("/catalogs/modalities", response_model=list[schemas.Modality], summary="Catalogo de modalidades", tags=["Catalogos"])
def list_modalities(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las modalidades disponibles."""
    return db.query(models.Modality).order_by(models.Modality.name).all()


@app.post("/admin/catalogs/modalities", response_model=schemas.Modality, summary="Crear modalidad", tags=["Catalogos"])
def create_modality(
    modality: schemas.ModalityCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    existing = db.query(models.Modality).filter(models.Modality.name == modality.name).first()
    if existing:
        return existing

    new_modality = models.Modality(name=modality.name)
    db.add(new_modality)
    db.commit()
    db.refresh(new_modality)
    return new_modality


@app.get("/admin/study-plans", response_model=list[schemas.StudyPlan], summary="Listar planes de estudio", tags=["Administracion"])
def get_study_plans(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.StudyPlan).order_by(models.StudyPlan.id.desc()).all()


@app.post("/admin/study-plans", response_model=schemas.StudyPlan, summary="Crear plan de estudio", tags=["Administracion"])
def create_study_plan(
    study_plan: schemas.StudyPlanCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    career = db.query(models.Career).filter(models.Career.id == study_plan.career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Carrera no encontrada")

    existing = (
        db.query(models.StudyPlan)
        .filter(
            models.StudyPlan.career_id == study_plan.career_id,
            models.StudyPlan.name == study_plan.name,
        )
        .first()
    )
    if existing:
        return existing

    new_plan = models.StudyPlan(
        career_id=study_plan.career_id,
        name=study_plan.name.strip(),
        version=study_plan.version.strip() or "1",
        is_active=study_plan.is_active,
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return new_plan


@app.get("/admin/study-plans/{study_plan_id}", response_model=schemas.StudyPlanWithSubjects, summary="Detalle de plan de estudio", tags=["Administracion"])
def get_study_plan(
    study_plan_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    plan = db.query(models.StudyPlan).filter(models.StudyPlan.id == study_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan de estudio no encontrado")
    return plan


@app.post("/admin/study-plans/{study_plan_id}/subjects", response_model=schemas.StudyPlanSubject, summary="Agregar materia a plan", tags=["Administracion"])
def add_subject_to_study_plan(
    study_plan_id: int,
    payload: schemas.StudyPlanSubjectCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    plan = db.query(models.StudyPlan).filter(models.StudyPlan.id == study_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan de estudio no encontrado")

    subject = db.query(models.Subject).filter(models.Subject.id == payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    existing = (
        db.query(models.StudyPlanSubject)
        .filter(
            models.StudyPlanSubject.study_plan_id == study_plan_id,
            models.StudyPlanSubject.subject_id == payload.subject_id,
        )
        .first()
    )
    if existing:
        return existing

    item = models.StudyPlanSubject(
        study_plan_id=study_plan_id,
        subject_id=payload.subject_id,
        semester=payload.semester or subject.semester,
        order_index=payload.order_index,
        is_required=payload.is_required,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/admin/school-cycle", response_model=Optional[schemas.SchoolCycle], tags=["Configuracion"])
def get_active_school_cycle(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).order_by(models.SchoolCycle.id.desc()).first()


@app.post("/admin/school-cycle", response_model=schemas.SchoolCycle, tags=["Configuracion"])
def save_school_cycle(cycle: schemas.SchoolCycleCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    if not (cycle.period or "").strip():
        raise HTTPException(status_code=400, detail="El periodo del ciclo es obligatorio")
    if cycle.start_date >= cycle.end_date:
        raise HTTPException(status_code=400, detail="La fecha de inicio debe ser anterior a la fecha de fin")
    if not cycle.tuitions:
        raise HTTPException(status_code=400, detail="Debes capturar al menos un costo por carrera y modalidad")

    seen_pairs: set[tuple[int, int]] = set()
    for tuition in cycle.tuitions:
        key = (tuition.career_id, tuition.modality_id)
        if key in seen_pairs:
            raise HTTPException(status_code=400, detail="Hay costos duplicados para la misma carrera y modalidad")
        seen_pairs.add(key)

    try:
        db.query(models.SchoolCycle).update({"is_active": False})
        new_cycle = models.SchoolCycle(
            period=cycle.period.strip(),
            start_date=cycle.start_date,
            end_date=cycle.end_date,
            monthly_amount=cycle.monthly_amount,
            is_active=True,
        )
        db.add(new_cycle)
        db.flush()
        for t in cycle.tuitions:
            db.add(models.CycleTuition(
                cycle_id=new_cycle.id,
                career_id=t.career_id,
                modality_id=t.modality_id,
                amount=t.amount,
            ))
        db.commit()
        db.refresh(new_cycle)
        return new_cycle
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo guardar el ciclo escolar: {exc}")


@app.post("/admin/school-cycle/generate-payments", response_model=schemas.SchoolCyclePaymentResult, tags=["Configuracion"])
def generate_cycle_payments(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    import calendar
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).order_by(models.SchoolCycle.id.desc()).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="No hay ciclo escolar activo")

    # Generate monthly payment dates between start and end
    months = []
    current = cycle.start_date.replace(day=1)
    end = cycle.end_date
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        due = current.replace(day=min(15, last_day))
        month_name = due.strftime("%B %Y").capitalize()
        months.append({"month": month_name, "due_date": due})
        # Advance to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    # Tuition lookup: (career_id, modality_id) -> amount
    tuition_map = {(t.career_id, t.modality_id): t.amount for t in cycle.tuitions}

    payments_created = 0
    students_affected = set()
    enrollments = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.cycle_id == cycle.id,
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
            models.StudentEnrollment.is_active == True,
        )
        .all()
    )

    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        for month_info in months:
            concept = f"Colegiatura {month_info['month']}"
            existing_charge = db.query(models.Charge).filter(
                models.Charge.student_enrollment_id == enrollment.id,
                models.Charge.concept == concept,
            ).first()
            if existing_charge:
                continue
            # Amount: prefer per career+modality, fallback to cycle default
            amount = tuition_map.get(
                (enrollment.career_id or student.career_id, enrollment.modality_id or student.modality_id),
                cycle.monthly_amount or 0
            )
            if amount <= 0:
                continue
            due_date = datetime(
                month_info["due_date"].year,
                month_info["due_date"].month,
                month_info["due_date"].day,
                23, 59, 59,
            )
            charge = models.Charge(
                student_id=student.id,
                student_enrollment_id=enrollment.id,
                charge_type=models.ChargeType.TUITION,
                concept=concept,
                period_label=month_info["month"],
                amount=amount,
                due_date=due_date,
                status=models.PaymentStatus.PENDIENTE,
            )
            db.add(charge)
            db.flush()
            _ensure_payment_for_charge(db, charge)
            payments_created += 1
            students_affected.add(student.id)

    db.commit()
    return {
        "payments_created": payments_created,
        "students_affected": len(students_affected),
        "months": [m["month"] for m in months],
    }


@app.post("/admin/school-cycles/{cycle_id}/recalculate-charges", tags=["Configuracion"])
def recalculate_cycle_charges(
    cycle_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    import calendar

    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")

    months = []
    current = cycle.start_date.replace(day=1)
    end = cycle.end_date
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        due = current.replace(day=min(15, last_day))
        month_name = due.strftime("%B %Y").capitalize()
        months.append({"month": month_name, "due_date": due})
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    tuition_map = {(t.career_id, t.modality_id): t.amount for t in cycle.tuitions}
    enrollments = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.cycle_id == cycle.id,
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
            models.StudentEnrollment.is_active == True,
        )
        .all()
    )

    updated_count = 0
    created_count = 0
    students_affected = set()

    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        target_amount = tuition_map.get(
            (enrollment.career_id or student.career_id, enrollment.modality_id or student.modality_id),
            cycle.monthly_amount or 0,
        )
        if target_amount <= 0:
            continue

        for month_info in months:
            concept = f"Colegiatura {month_info['month']}"
            due_date = datetime(
                month_info["due_date"].year,
                month_info["due_date"].month,
                month_info["due_date"].day,
                23, 59, 59,
            )
            existing_charge = (
                db.query(models.Charge)
                .filter(
                    models.Charge.student_enrollment_id == enrollment.id,
                    models.Charge.concept == concept,
                    models.Charge.period_label == month_info["month"],
                    models.Charge.charge_type == models.ChargeType.TUITION,
                )
                .first()
            )
            if existing_charge:
                if existing_charge.status != models.PaymentStatus.PAGADO and (
                    float(existing_charge.amount or 0) != float(target_amount)
                    or existing_charge.due_date != due_date
                ):
                    existing_charge.amount = target_amount
                    existing_charge.due_date = due_date
                    _ensure_payment_for_charge(db, existing_charge)
                    updated_count += 1
                    students_affected.add(student.id)
                continue

            charge = models.Charge(
                student_id=student.id,
                student_enrollment_id=enrollment.id,
                charge_type=models.ChargeType.TUITION,
                concept=concept,
                period_label=month_info["month"],
                amount=target_amount,
                due_date=due_date,
                status=models.PaymentStatus.PENDIENTE,
            )
            db.add(charge)
            db.flush()
            _ensure_payment_for_charge(db, charge)
            created_count += 1
            students_affected.add(student.id)

    db.commit()
    return {
        "ok": True,
        "cycle_id": cycle.id,
        "cycle_period": cycle.period,
        "created_count": created_count,
        "updated_count": updated_count,
        "students_affected": len(students_affected),
        "months": [m["month"] for m in months],
    }


@app.post("/token", response_model=schemas.TokenPair, summary="Iniciar sesion", tags=["Autenticacion"])
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Autentica con username (matricula) y password. Devuelve tokens JWT (access y refresh)."""
    client_ip = _get_client_ip(request)
    _enforce_login_rate_limit(client_ip)

    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contrasena incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.user_status == models.UserStatus.BAJA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este perfil ha sido dado de baja. Consulta a servicios escolares.",
        )
    if user.user_status == models.UserStatus.BLOQUEADO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso bloqueado. Consulta a servicios escolares, es posible que tengas algún pago pendiente.",
        )
    _reset_login_attempts(client_ip)
    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
    refresh_token = auth.create_refresh_token(data={"sub": user.username, "role": user.role})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@app.post("/token/refresh", response_model=schemas.TokenPair, summary="Refrescar access token", tags=["Autenticacion"])
async def refresh_access_token(payload: schemas.RefreshTokenRequest):
    decoded = auth.validate_refresh_token(payload.refresh_token)
    access_token = auth.create_access_token(data={"sub": decoded.get("sub"), "role": decoded.get("role")})
    refresh_token = auth.create_refresh_token(data={"sub": decoded.get("sub"), "role": decoded.get("role")})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@app.get("/users/me", response_model=schemas.User, summary="Perfil del usuario", tags=["Usuario"])
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    valid_service_types = {item.value for item in schemas.ServiceRequestType}
    filtered_service_requests = [
        service_request
        for service_request in (current_user.service_requests or [])
        if (service_request.type in valid_service_types)
    ]
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "moodle_id": current_user.moodle_id,
        "user_status": current_user.user_status,
        "enrollment_status": current_user.enrollment_status,
        "career_id": current_user.career_id,
        "carrera": current_user.carrera,
        "modality_id": current_user.modality_id,
        "modalidad": current_user.modalidad,
        "semestre": current_user.semestre,
        "grupo": current_user.grupo,
        "academic_advisor_id": current_user.academic_advisor_id,
        "payments": current_user.payments or [],
        "grades": current_user.grades or [],
        "service_requests": filtered_service_requests,
    }


@app.get("/users/me/profile", response_model=schemas.UserProfileOut, summary="Perfil completo del alumno", tags=["Usuario"])
def read_user_profile(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # Buscar inscripción activa del alumno en el ciclo vigente
    active_enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == current_user.id,
            models.StudentEnrollment.is_active == True,
        )
        .order_by(models.StudentEnrollment.id.desc())
        .first()
    )

    career_name = None
    modality_name = None
    semester = None
    group_name = None
    cycle_period = None

    if active_enrollment:
        if active_enrollment.career:
            career_name = active_enrollment.career.name
        if active_enrollment.modality:
            modality_name = active_enrollment.modality.name
        semester = active_enrollment.semester
        if active_enrollment.group:
            group_name = active_enrollment.group.name
        if active_enrollment.cycle:
            cycle_period = active_enrollment.cycle.period

    # Fallback a campos legacy si la inscripción no tiene relaciones
    if not career_name:
        career_name = (
            current_user.career_rel.name if current_user.career_rel else current_user.carrera
        )
    if not modality_name:
        modality_name = (
            current_user.modality_rel.name if current_user.modality_rel else current_user.modalidad
        )
    if not semester:
        semester = current_user.semestre
    if not group_name:
        group_name = current_user.grupo

    return schemas.UserProfileOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        user_status=current_user.user_status,
        enrollment_status=current_user.enrollment_status,
        career_name=career_name,
        modality_name=modality_name,
        semester=semester,
        group_name=group_name,
        cycle_period=cycle_period,
    )


# ----------------------------
# Admin
# ----------------------------

@app.get("/admin/stats", summary="Estadisticas generales", tags=["Administracion"])
def get_admin_stats(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    total_students = db.query(models.User).filter(models.User.role == models.UserRole.STUDENT).count()
    paid_payments = db.query(models.Payment).filter(models.Payment.status == models.PaymentStatus.PAGADO).all()
    total_income = sum(p.amount for p in paid_payments)
    pending_services = db.query(models.ServiceRequest).filter(models.ServiceRequest.status == models.ServiceRequestStatus.EN_PROCESO).count()
    total_teachers = db.query(models.User).filter(models.User.role == models.UserRole.TEACHER).count()
    return {
        "total_students": total_students,
        "total_income": total_income,
        "pending_services": pending_services,
        "total_teachers": total_teachers,
    }


@app.get("/admin/students", response_model=list[schemas.UserListItem], summary="Listar alumnos", tags=["Administracion"])
def get_all_students(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from sqlalchemy import func as _func
    avg_subq = (
        db.query(
            models.Grade.student_id,
            _func.avg(models.Grade.score).label("average_score"),
        )
        .filter(models.Grade.score.isnot(None))
        .group_by(models.Grade.student_id)
        .subquery()
    )
    students = (
        db.query(
            models.User.id,
            models.User.username,
            models.User.email,
            models.User.full_name,
            models.User.role,
            models.User.moodle_id,
            models.User.user_status,
            models.User.enrollment_status,
            models.User.career_id,
            models.User.carrera,
            models.User.modality_id,
            models.User.modalidad,
            models.User.semestre,
            models.User.grupo,
            avg_subq.c.average_score,
        )
        .outerjoin(avg_subq, avg_subq.c.student_id == models.User.id)
        .filter(models.User.role == models.UserRole.STUDENT)
        .order_by(models.User.id.asc())
        .all()
    )
    return [row._asdict() for row in students]


@app.post("/admin/students", response_model=schemas.User, summary="Crear alumno", tags=["Administracion"])
def create_student(student: schemas.UserCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == student.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="La matricula/usuario ya esta registrada")

    career = None
    if student.career_id:
        career = db.query(models.Career).filter(models.Career.id == student.career_id).first()
        if not career:
            raise HTTPException(status_code=400, detail="Carrera no encontrada")
    elif student.carrera:
        career = db.query(models.Career).filter(models.Career.name == student.carrera).first()
        if not career:
            career = models.Career(name=student.carrera)
            db.add(career)
            db.flush()

    modality = None
    if student.modality_id:
        modality = db.query(models.Modality).filter(models.Modality.id == student.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
    elif student.modalidad:
        modality = db.query(models.Modality).filter(models.Modality.name == student.modalidad).first()
        if not modality:
            modality = models.Modality(name=student.modalidad)
            db.add(modality)
            db.flush()

    hashed_password = auth.get_password_hash(student.password)
    new_user = models.User(
        username=student.username,
        email=student.email,
        full_name=student.full_name,
        role=models.UserRole.STUDENT,
        hashed_password=hashed_password,
        career_id=career.id if career else None,
        carrera=career.name if career else student.carrera,
        modality_id=modality.id if modality else None,
        modalidad=modality.name if modality else student.modalidad,
        semestre=student.semestre,
        grupo=student.grupo,
    )
    db.add(new_user)
    db.flush()
    _assign_curriculum_to_student(db, new_user.id, career.name if career else student.carrera)
    _sync_student_enrollment_from_legacy(db, new_user, reason="Alta de alumno")
    db.commit()
    db.refresh(new_user)
    return new_user


@app.put("/admin/students/{username}", response_model=schemas.User, summary="Actualizar alumno", tags=["Administracion"])
def update_student(username: str, student_update: schemas.UserUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    if student_update.full_name is not None:
        db_user.full_name = student_update.full_name
    if student_update.email is not None:
        db_user.email = student_update.email
    if student_update.password:
        db_user.hashed_password = auth.get_password_hash(student_update.password)
    if student_update.user_status is not None:
        db_user.user_status = student_update.user_status
    if student_update.enrollment_status is not None:
        db_user.enrollment_status = student_update.enrollment_status
    if student_update.career_id is not None:
        career = db.query(models.Career).filter(models.Career.id == student_update.career_id).first()
        if not career:
            raise HTTPException(status_code=400, detail="Carrera no encontrada")
        db_user.career_id = career.id
        db_user.carrera = career.name
    if hasattr(student_update, "carrera") and student_update.carrera is not None:
        career = db.query(models.Career).filter(models.Career.name == student_update.carrera).first()
        if not career and student_update.carrera:
            career = models.Career(name=student_update.carrera)
            db.add(career)
            db.flush()
        if career:
            db_user.career_id = career.id
            db_user.carrera = career.name
    if student_update.modality_id is not None:
        modality = db.query(models.Modality).filter(models.Modality.id == student_update.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
        db_user.modality_id = modality.id
        db_user.modalidad = modality.name
    if hasattr(student_update, "modalidad") and student_update.modalidad is not None:
        modality = db.query(models.Modality).filter(models.Modality.name == student_update.modalidad).first()
        if not modality and student_update.modalidad:
            modality = models.Modality(name=student_update.modalidad)
            db.add(modality)
            db.flush()
        if modality:
            db_user.modality_id = modality.id
            db_user.modalidad = modality.name
    if student_update.semestre is not None:
        db_user.semestre = student_update.semestre
    if student_update.grupo is not None:
        db_user.grupo = student_update.grupo

    _sync_student_enrollment_from_legacy(db, db_user, reason="Actualizacion de alumno")

    db.commit()
    db.refresh(db_user)

    # Reforzar la currícula al editar carrera o semestre desde el panel.
    if db_user.carrera and (
        student_update.career_id is not None
        or (hasattr(student_update, "carrera") and student_update.carrera is not None)
        or student_update.semestre is not None
    ):
        _assign_curriculum_to_student(db, db_user.id, db_user.carrera)
        db.commit()

    db.refresh(db_user)
    return db_user


@app.delete("/admin/students/{username}", status_code=204, summary="Eliminar alumno", tags=["Administracion"])
def delete_student(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(
        models.User.username == username,
        models.User.role == models.UserRole.STUDENT,
    ).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    enrollment_ids = [
        enrollment.id
        for enrollment in db.query(models.StudentEnrollment.id).filter(
            models.StudentEnrollment.student_id == db_user.id
        ).all()
    ]

    if enrollment_ids:
        db.query(models.CourseEnrollment).filter(
            models.CourseEnrollment.student_enrollment_id.in_(enrollment_ids)
        ).delete(synchronize_session=False)

    db.query(models.Payment).filter(models.Payment.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.Charge).filter(models.Charge.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.ServiceRequest).filter(models.ServiceRequest.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.Grade).filter(models.Grade.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.StudentEnrollment).filter(models.StudentEnrollment.student_id == db_user.id).delete(synchronize_session=False)
    db.delete(db_user)
    db.commit()


@app.get("/admin/students/{username}/full", summary="Perfil completo de alumno con docentes", tags=["Administracion"])
def get_student_full_profile(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    grades_data = []
    for g in db_user.grades:
        teacher_name = None
        cycle_period = None
        if g.assignment:
            if g.assignment.teacher:
                teacher_name = g.assignment.teacher.full_name or g.assignment.teacher.username
            if g.assignment.cycle:
                cycle_period = g.assignment.cycle.period
        grades_data.append({
            "id": g.id,
            "subject_id": g.subject_id,
            "subject_name": g.subject.name if g.subject else None,
            "subject_semester": g.subject.semester if g.subject else None,
            "subject_credits": g.subject.credits if g.subject else None,
            "assignment_id": g.assignment_id,
            "course_enrollment_id": g.course_enrollment_id,
            "teacher": teacher_name,
            "cycle": cycle_period,
            "score": g.score,
            "status": g.status,
            "attempt_type": g.attempt_type,
        })

    return {
        "id": db_user.id,
        "username": db_user.username,
        "full_name": db_user.full_name,
        "email": db_user.email,
        "role": db_user.role,
        "user_status": db_user.user_status,
        "enrollment_status": db_user.enrollment_status,
        "carrera": db_user.carrera,
        "career_id": db_user.career_id,
        "modalidad": db_user.modalidad,
        "modality_id": db_user.modality_id,
        "semestre": db_user.semestre,
        "grupo": db_user.grupo,
        "academic_advisor_id": db_user.academic_advisor_id,
        "grades": grades_data,
        "payments": [{"id": p.id, "concept": p.concept, "amount": p.amount, "status": p.status, "due_date": str(p.due_date)} for p in db_user.payments],
        "charges": [{"id": c.id, "concept": c.concept, "amount": c.amount, "status": c.status, "due_date": str(c.due_date)} for c in db_user.charges],
        "service_requests": [{"id": r.id, "type": r.type, "status": r.status} for r in db_user.service_requests],
    }


@app.get("/admin/students/{username}/boleta", summary="Boleta de calificaciones en PDF", tags=["Administracion"])
def get_student_boleta_pdf(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from fpdf import FPDF
    from fastapi.responses import Response as FastAPIResponse

    student = db.query(models.User).filter(models.User.username == username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    grades = (
        db.query(models.Grade)
        .filter(models.Grade.student_id == student.id)
        .order_by(models.Grade.id.asc())
        .all()
    )

    def safe(s: object, maxlen: int = 999) -> str:
        normalized = str(s or "-").replace("—", "-").replace("–", "-")
        normalized = normalized.encode("latin-1", errors="replace").decode("latin-1")
        return normalized[:maxlen]

    approved = sum(1 for g in grades if str(g.status) == "Aprobada")
    failed = sum(1 for g in grades if str(g.status) == "Reprobada")
    in_prog = sum(1 for g in grades if str(g.status) == "Cursando")
    scored = [g.score for g in grades if g.score is not None]
    avg = round(sum(scored) / len(scored), 2) if scored else 0.0

    folio = f"BOL-{username}-{int(datetime.utcnow().timestamp()) % 1000000:06d}"
    generated_at = datetime.utcnow()

    class BoletaPDF(FPDF):
        def header(self):
            self.set_fill_color(22, 52, 125)
            self.rect(0, 0, 210, 32, "F")
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 17)
            self.set_xy(12, 8)
            self.cell(186, 8, safe("Universidad Unives"), align="L")
            self.set_font("Helvetica", "", 10)
            self.set_xy(12, 18)
            self.cell(186, 6, safe("Boleta Oficial de Calificaciones"), align="L")
            self.set_text_color(35, 35, 35)
            self.ln(18)

        def footer(self):
            self.set_y(-12)
            self.set_draw_color(210, 214, 224)
            self.line(10, self.get_y(), 200, self.get_y())
            self.set_y(-9)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(110, 118, 135)
            footer = f"Pagina {self.page_no()} | Generado el {generated_at.strftime('%d/%m/%Y %H:%M')} UTC"
            self.cell(0, 5, safe(footer), align="C")

    pdf = BoletaPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_fill_color(245, 247, 251)
    pdf.set_draw_color(223, 228, 238)
    pdf.rect(10, 36, 190, 30, style="DF")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(97, 107, 127)
    pdf.set_xy(14, 40)
    pdf.cell(90, 5, safe(f"Folio: {folio}"), align="L")
    pdf.cell(82, 5, safe(f"Fecha: {generated_at.strftime('%d/%m/%Y')}"), align="R")

    info_rows = [
        ("Alumno", safe(student.full_name, 55), "Matricula", safe(student.username, 24)),
        ("Carrera", safe(student.carrera, 55), "Semestre", safe(student.semestre, 24)),
        ("Correo", safe(student.email, 55), "Grupo", safe(student.grupo, 24)),
    ]
    y = 48
    for label_left, value_left, label_right, value_right in info_rows:
        pdf.set_xy(14, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(24, 5, safe(label_left + ":"), align="L")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(70, 5, value_left, align="L")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(24, 5, safe(label_right + ":"), align="L")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(42, 5, value_right, align="L")
        y += 6

    summary_y = 72
    card_w = 45
    summary_cards = [
        ("Aprobadas", str(approved), (22, 163, 74)),
        ("Reprobadas", str(failed), (220, 53, 69)),
        ("En curso", str(in_prog), (245, 158, 11)),
        ("Promedio", str(avg), (37, 99, 235)),
    ]
    x = 10
    for label, value, color in summary_cards:
        pdf.set_fill_color(*color)
        pdf.rect(x, summary_y, card_w, 18, style="F")
        pdf.set_xy(x, summary_y + 3)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(card_w, 4, safe(label), align="C")
        pdf.set_xy(x, summary_y + 8)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(card_w, 6, safe(value), align="C")
        x += card_w + 3

    pdf.set_text_color(35, 35, 35)
    pdf.set_xy(10, 96)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 7, safe("Boleta por Cuatrimestre"), align="L")
    pdf.ln(10)

    def _subject_for_grade(grade: models.Grade):
        if grade.subject:
            return grade.subject
        if grade.assignment and grade.assignment.subject:
            return grade.assignment.subject
        return None

    def _grade_term_number(grade: models.Grade) -> Optional[int]:
        subject = _subject_for_grade(grade)
        semester_label = subject.semester if subject else None
        if not semester_label:
            return None
        parsed = _parse_semester_num(semester_label)
        return parsed if parsed > 0 else None

    def _grade_subject_name(grade: models.Grade) -> str:
        subject = _subject_for_grade(grade)
        return safe(subject.name if subject else "-", 60)

    def _grade_subject_id(grade: models.Grade) -> str:
        subject = _subject_for_grade(grade)
        return safe(subject.id if subject and subject.id is not None else grade.id, 10)

    def _cuatrimestre_label(number: int) -> str:
        return f"{number} Cuatrimestre"

    headers = ["ID", "Materia", "Cuatrimestre", "Calificacion"]
    col_widths = [20, 96, 38, 36]
    row_height = 7
    grades_by_term: dict[int, list[models.Grade]] = {term: [] for term in range(1, 10)}
    for grade in grades:
        term_number = _grade_term_number(grade)
        if term_number and term_number in grades_by_term:
            grades_by_term[term_number].append(grade)

    for term in range(1, 10):
        if pdf.get_y() > 250:
            pdf.add_page()

        term_grades = sorted(
            grades_by_term.get(term, []),
            key=lambda item: (_grade_subject_name(item).lower(), item.id or 0),
        )
        scored = [float(g.score) for g in term_grades if g.score is not None]
        term_avg = round(sum(scored) / len(scored), 2) if scored else None

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(22, 52, 125)
        pdf.cell(190, 6, safe(_cuatrimestre_label(term)), align="L")
        pdf.ln(7)

        pdf.set_fill_color(22, 52, 125)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        for header, width in zip(headers, col_widths):
            pdf.cell(width, 8, safe(header), border=1, align="C", fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(35, 35, 35)

        if term_grades:
            alternate = False
            for grade in term_grades:
                if pdf.get_y() > 268:
                    pdf.add_page()
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(22, 52, 125)
                    pdf.cell(190, 6, safe(_cuatrimestre_label(term) + " (continuacion)"), align="L")
                    pdf.ln(7)
                    pdf.set_fill_color(22, 52, 125)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Helvetica", "B", 8)
                    for header, width in zip(headers, col_widths):
                        pdf.cell(width, 8, safe(header), border=1, align="C", fill=True)
                    pdf.ln()
                    pdf.set_font("Helvetica", "", 8)
                    pdf.set_text_color(35, 35, 35)

                fill = (255, 255, 255) if not alternate else (247, 250, 255)
                alternate = not alternate
                pdf.set_fill_color(*fill)
                values = [
                    _grade_subject_id(grade),
                    _grade_subject_name(grade),
                    safe(_cuatrimestre_label(term), 18),
                    safe(round(grade.score, 1) if grade.score is not None else "-", 12),
                ]
                aligns = ["C", "L", "C", "C"]
                for value, width, align in zip(values, col_widths, aligns):
                    pdf.cell(width, row_height, safe(value, 60), border=1, align=align, fill=True)
                pdf.ln()
        else:
            pdf.set_fill_color(248, 250, 252)
            pdf.set_text_color(90, 98, 112)
            pdf.cell(sum(col_widths), 8, safe("Sin materias registradas."), border=1, align="C", fill=True)
            pdf.ln()
            pdf.set_text_color(35, 35, 35)

        pdf.set_fill_color(236, 242, 255)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(col_widths[0] + col_widths[1] + col_widths[2], 8, safe("Promedio del cuatrimestre"), border=1, align="R", fill=True)
        pdf.cell(col_widths[3], 8, safe(term_avg if term_avg is not None else "-", 12), border=1, align="C", fill=True)
        pdf.ln(12)

    pdf.ln(8)
    pdf.set_text_color(35, 35, 35)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(95, 6, safe("Firmas"), align="L")
    pdf.ln(14)
    line_y = pdf.get_y()
    pdf.set_draw_color(140, 148, 165)
    pdf.line(18, line_y, 82, line_y)
    pdf.line(128, line_y, 192, line_y)
    pdf.set_y(line_y + 2)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(90, 98, 112)
    pdf.set_x(18)
    pdf.cell(64, 5, safe("Director(a) General"), align="C")
    pdf.set_x(128)
    pdf.cell(64, 5, safe("Secretaria Academica"), align="C")

    pdf.ln(14)
    pdf.set_x(10)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(120, 126, 140)
    pdf.multi_cell(
        190,
        4,
        safe(
            "Documento generado electronicamente por el Sistema Administrativo de Universidad Unives. "
            "Valido como consulta interna. Para tramites oficiales solicite documento sellado en Secretaria Academica.",
            280,
        ),
        align="C",
    )

    raw_pdf = pdf.output(dest="S")
    pdf_bytes = raw_pdf if isinstance(raw_pdf, (bytes, bytearray)) else str(raw_pdf).encode("latin-1", errors="replace")
    return FastAPIResponse(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=boleta_{username}.pdf"},
    )


@app.get("/admin/reports/grades-export", summary="Exportar calificaciones CSV por ciclo", tags=["Administracion"])
def export_grades_csv(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    import csv, io
    from fastapi.responses import StreamingResponse

    query = (
        db.query(models.Grade)
        .join(models.Grade.student)
        .filter(models.User.role == models.UserRole.STUDENT)
    )

    if cycle_id:
        query = (
            query
            .join(models.Grade.assignment)
            .join(models.SubjectAssignment.cycle)
            .filter(models.SchoolCycle.id == cycle_id)
        )

    grades = query.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Matricula", "Nombre", "Carrera", "Semestre", "Grupo", "Materia", "Sem.Materia", "Creditos", "Calificacion", "Estatus", "Tipo", "Docente", "Ciclo"])
    for g in grades:
        s = g.student
        subj = g.subject
        teacher = "—"
        cycle_p = "—"
        if g.assignment:
            if g.assignment.teacher:
                teacher = g.assignment.teacher.full_name or g.assignment.teacher.username
            if g.assignment.cycle:
                cycle_p = g.assignment.cycle.period or "—"
        writer.writerow([
            s.username if s else "",
            s.full_name if s else "",
            s.carrera if s else "",
            s.semestre if s else "",
            s.grupo if s else "",
            subj.name if subj else "",
            subj.semester if subj else "",
            subj.credits if subj else "",
            g.score if g.score is not None else "",
            str(g.status) if g.status else "",
            str(g.attempt_type) if g.attempt_type else "",
            teacher,
            cycle_p,
        ])

    content = "\ufeff" + buf.getvalue()
    fname = f"calificaciones_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@app.get("/admin/students/{username}/academic-history", response_model=list[schemas.AcademicHistoryItem], summary="Historial academico del alumno", tags=["Administracion"])
def get_student_academic_history(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    return _get_academic_history_for_student(db, student.id)


@app.put("/admin/students/{username}/password", summary="Resetear contraseña de alumno", tags=["Administracion"])
def reset_student_password(username: str, body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    new_password = body.get("password", "").strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    db_user.hashed_password = auth.get_password_hash(new_password)
    db.commit()
    return {"detail": "Contraseña actualizada"}


@app.post("/admin/enrollments", summary="Inscribir alumno en asignación", tags=["Administracion"])
def enroll_student_in_assignment(body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    """Inscribe manualmente a un alumno en una asignación (materia + docente + ciclo)."""
    username = body.get("username")
    assignment_id = body.get("assignment_id")

    student = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.REGULAR,
        status=models.GradeStatus.CURSANDO,
    )
    db.commit()
    db.refresh(course_enrollment)
    latest_grade = _get_grade_for_course_enrollment(course_enrollment)
    return {
        "detail": "Inscripción exitosa",
        "grade_id": latest_grade.id if latest_grade else None,
        "course_enrollment_id": course_enrollment.id,
        "reassigned": False,
    }


@app.get("/admin/course-enrollments", response_model=list[schemas.CourseEnrollmentWithRelations], summary="Listar carga académica", tags=["Administracion"])
def get_course_enrollments(
    cycle_id: Optional[int] = None,
    username: Optional[str] = None,
    assignment_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    query = db.query(models.CourseEnrollment).join(models.StudentEnrollment)

    if cycle_id:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle_id)
    if username:
        query = query.join(models.User).filter(models.User.username == username)
    if assignment_id:
        query = query.filter(models.CourseEnrollment.assignment_id == assignment_id)

    return query.order_by(models.CourseEnrollment.id.desc()).all()


@app.post("/admin/course-enrollments", response_model=schemas.CourseEnrollmentWithRelations, summary="Inscribir alumno a materia", tags=["Administracion"])
def create_course_enrollment(
    body: schemas.CourseEnrollmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == body.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=body.attempt_type,
        status=body.status,
        create_grade_record=body.create_grade_record,
    )
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.post("/admin/course-enrollments/extraordinary", response_model=schemas.CourseEnrollmentWithRelations, summary="Registrar extraordinario", tags=["Administracion"])
def create_extraordinary_course_enrollment(
    body: schemas.CourseEnrollmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == body.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    failed_attempt = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.assignment_id == assignment.id,
            models.Grade.attempt_type.in_([models.AttemptType.REGULAR, models.AttemptType.RECURSA]),
            models.Grade.status == models.GradeStatus.REPROBADA,
        )
        .first()
    )
    if not failed_attempt:
        raise HTTPException(status_code=400, detail="El extraordinario requiere un antecedente reprobado en esta misma asignación")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.EXTEMPORANEO,
        status=body.status,
        create_grade_record=body.create_grade_record,
    )
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.post("/admin/course-enrollments/retake", response_model=schemas.CourseEnrollmentWithRelations, summary="Registrar recursa", tags=["Administracion"])
def create_retake_course_enrollment(
    body: schemas.CourseEnrollmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == body.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    prior_grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.subject_id == assignment.subject_id,
            models.Grade.status == models.GradeStatus.REPROBADA,
        )
        .first()
    )
    if not prior_grade:
        raise HTTPException(status_code=400, detail="La recursa requiere un antecedente reprobado de la misma materia")

    approved_grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.subject_id == assignment.subject_id,
            models.Grade.status == models.GradeStatus.APROBADA,
        )
        .first()
    )
    if approved_grade:
        raise HTTPException(status_code=400, detail="La materia ya fue aprobada. No corresponde registrar recursa")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.RECURSA,
        status=body.status,
        create_grade_record=body.create_grade_record,
    )
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.put("/admin/course-enrollments/{course_enrollment_id}/drop", response_model=schemas.CourseEnrollmentWithRelations, summary="Dar de baja materia", tags=["Administracion"])
def drop_course_enrollment(
    course_enrollment_id: int,
    body: schemas.CourseEnrollmentDropRequest,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    course_enrollment = (
        db.query(models.CourseEnrollment)
        .filter(models.CourseEnrollment.id == course_enrollment_id)
        .first()
    )
    if not course_enrollment:
        raise HTTPException(status_code=404, detail="Inscripcion academica no encontrada")

    if course_enrollment.dropped_at:
        raise HTTPException(status_code=400, detail="La materia ya fue dada de baja")

    course_enrollment.dropped_at = body.dropped_at or datetime.utcnow()
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.get("/admin/groups", response_model=list[schemas.GroupSummary], summary="Listar grupos con conteo de alumnos", tags=["Administracion"])
def get_groups(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from sqlalchemy import func
    active_cycle = _get_active_cycle(db)
    tutor_user = aliased(models.User)
    enrollment_join = models.StudentEnrollment.group_id == models.Group.id
    if active_cycle:
        enrollment_join = enrollment_join & (models.StudentEnrollment.cycle_id == active_cycle.id)

    group_career = aliased(models.Career)
    enroll_career = aliased(models.Career)
    rows = (
        db.query(
            models.Group.id.label("group_id"),
            models.Group.name.label("grupo"),
            models.Group.career_id.label("group_career_id"),
            group_career.name.label("group_career_name"),
            func.coalesce(func.min(enroll_career.name), "Sin carrera").label("enroll_carrera"),
            models.Group.modality_id.label("modality_id"),
            models.Group.tutor_id.label("tutor_id"),
            tutor_user.full_name.label("tutor_name"),
            func.count(models.StudentEnrollment.id).label("total"),
        )
        .outerjoin(models.StudentEnrollment, enrollment_join)
        .outerjoin(enroll_career, enroll_career.id == models.StudentEnrollment.career_id)
        .outerjoin(group_career, group_career.id == models.Group.career_id)
        .outerjoin(tutor_user, tutor_user.id == models.Group.tutor_id)
        .filter(models.Group.is_active == True)
        .group_by(
            models.Group.id,
            models.Group.name,
            models.Group.career_id,
            group_career.name,
            models.Group.modality_id,
            models.Group.tutor_id,
            tutor_user.full_name,
        )
        .order_by(models.Group.name)
        .all()
    )
    return [
        {
            "group_id": r.group_id,
            "grupo": r.grupo,
            "carrera": r.group_career_name or r.enroll_carrera or "Sin carrera",
            "total": r.total,
            "modality_id": r.modality_id,
            "tutor_id": r.tutor_id,
            "tutor_name": r.tutor_name,
            "career_id": r.group_career_id,
        }
        for r in rows
    ]


@app.post("/admin/groups", response_model=schemas.GroupWithRelations, summary="Crear grupo", tags=["Administracion"])
def create_group(
    body: schemas.GroupCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.Group)
        .filter(
            models.Group.name == body.name.strip(),
            models.Group.modality_id == body.modality_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un grupo con ese nombre y modalidad")

    tutor = None
    if body.tutor_id is not None:
        tutor = db.query(models.User).filter(models.User.id == body.tutor_id).first()
        if not tutor or tutor.role != models.UserRole.TEACHER:
            raise HTTPException(status_code=400, detail="Tutor no encontrado o no es docente")

    group = models.Group(
        name=body.name.strip(),
        modality_id=body.modality_id,
        tutor_id=tutor.id if tutor else None,
        is_active=body.is_active,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@app.get("/admin/groups/{group_id}", response_model=schemas.GroupWithRelations, summary="Detalle de grupo", tags=["Administracion"])
def get_group_detail(
    group_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return group


@app.put("/admin/groups/{group_id}", response_model=schemas.GroupWithRelations, summary="Editar grupo", tags=["Administracion"])
def update_group(
    group_id: int,
    body: schemas.GroupUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    if body.name is not None:
        normalized_name = body.name.strip()
        duplicate = (
            db.query(models.Group)
            .filter(
                models.Group.id != group.id,
                models.Group.name == normalized_name,
                models.Group.modality_id == (body.modality_id if body.modality_id is not None else group.modality_id),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Ya existe otro grupo con ese nombre y modalidad")
        group.name = normalized_name

    if "modality_id" in body.model_fields_set:
        group.modality_id = body.modality_id

    if "tutor_id" in body.model_fields_set:
        if body.tutor_id is None:
            group.tutor_id = None
        else:
            tutor = db.query(models.User).filter(models.User.id == body.tutor_id).first()
            if not tutor or tutor.role != models.UserRole.TEACHER:
                raise HTTPException(status_code=400, detail="Tutor no encontrado o no es docente")
            group.tutor_id = tutor.id

    if "career_id" in body.model_fields_set:
        if body.career_id is None:
            group.career_id = None
        else:
            career = db.query(models.Career).filter(models.Career.id == body.career_id).first()
            if not career:
                raise HTTPException(status_code=404, detail="Carrera no encontrada")
            group.career_id = career.id

    if "is_active" in body.model_fields_set:
        group.is_active = body.is_active

    db.commit()
    db.refresh(group)
    return group


@app.delete("/admin/groups/{group_id}", summary="Eliminar grupo", tags=["Administracion"])
def delete_group(
    group_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    affected_enrollments = (
        db.query(models.StudentEnrollment)
        .filter(models.StudentEnrollment.group_id == group_id)
        .all()
    )

    affected_student_ids = {enrollment.student_id for enrollment in affected_enrollments if enrollment.student_id}
    for enrollment in affected_enrollments:
        enrollment.group_id = None
        enrollment.change_reason = f"Grupo eliminado: {group.name}"

    if affected_student_ids:
        students = db.query(models.User).filter(models.User.id.in_(affected_student_ids)).all()
        for student in students:
            has_other_group = (
                db.query(models.StudentEnrollment)
                .filter(
                    models.StudentEnrollment.student_id == student.id,
                    models.StudentEnrollment.group_id.isnot(None),
                )
                .first()
            )
            if not has_other_group and student.grupo == group.name:
                student.grupo = None

    db.delete(group)
    db.commit()
    return {"ok": True, "deleted_group_id": group_id, "released_students": len(affected_student_ids)}


@app.get("/admin/groups/{group_id}/students", response_model=list[schemas.StudentEnrollmentWithRelations], summary="Alumnos del grupo", tags=["Administracion"])
def get_group_students(
    group_id: int,
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    query = db.query(models.StudentEnrollment).filter(models.StudentEnrollment.group_id == group_id)
    if cycle_id:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle_id)
    else:
        active_cycle = _get_active_cycle(db)
        if active_cycle:
            query = query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)

    return query.order_by(models.StudentEnrollment.id.desc()).all()


@app.get("/admin/student-enrollments", response_model=list[schemas.StudentEnrollmentWithRelations], summary="Listar inscripciones por ciclo", tags=["Administracion"])
def get_student_enrollments(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id
        else _get_active_cycle(db)
    )
    if not cycle:
        return []

    return (
        db.query(models.StudentEnrollment)
        .filter(models.StudentEnrollment.cycle_id == cycle.id)
        .order_by(models.StudentEnrollment.id.desc())
        .all()
    )


@app.get("/admin/migration-audit", response_model=schemas.MigrationAuditResult, summary="Auditoria de migracion escolar", tags=["Administracion"])
def get_migration_audit(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    active_cycle = _get_active_cycle(db)

    legacy_students = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.STUDENT)
        .all()
    )
    legacy_students_with_seed_data = [student for student in legacy_students if _has_enrollment_seed_data(student)]
    legacy_students_with_group = [
        student for student in legacy_students
        if student.grupo and str(student.grupo).strip()
    ]

    student_enrollments_query = db.query(models.StudentEnrollment)
    if active_cycle:
        student_enrollments_query = student_enrollments_query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)
    student_enrollments = student_enrollments_query.all()

    enrolled_student_ids = {enrollment.student_id for enrollment in student_enrollments}
    missing_usernames = [
        student.username
        for student in legacy_students_with_seed_data
        if student.id not in enrolled_student_ids
    ]

    grades_total = db.query(models.Grade).count()
    grades_linked = (
        db.query(models.Grade)
        .filter(models.Grade.course_enrollment_id.isnot(None))
        .count()
    )

    return {
        "active_cycle_id": active_cycle.id if active_cycle else None,
        "active_cycle_period": active_cycle.period if active_cycle else None,
        "legacy_students_with_seed_data": len(legacy_students_with_seed_data),
        "student_enrollments_in_active_cycle": len(student_enrollments),
        "legacy_students_missing_enrollment": missing_usernames[:50],
        "legacy_students_with_group": len(legacy_students_with_group),
        "active_cycle_group_memberships": sum(1 for enrollment in student_enrollments if enrollment.group_id),
        "grades_total": grades_total,
        "grades_linked_to_course_enrollment": grades_linked,
        "grades_without_course_enrollment": grades_total - grades_linked,
    }


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


@app.get("/admin/reports/enrollment-summary", response_model=list[schemas.EnrollmentSummaryRow], summary="Reporte de matricula activa", tags=["Administracion"])
def get_enrollment_summary_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    cycle = _resolve_report_cycle(db, cycle_id)

    query = (
        db.query(
            models.StudentEnrollment.cycle_id.label("cycle_id"),
            models.SchoolCycle.period.label("cycle_period"),
            models.Career.name.label("career"),
            models.Modality.name.label("modality"),
            models.StudentEnrollment.semester.label("semester"),
            models.Group.name.label("group_name"),
            func.count(models.StudentEnrollment.id).label("total_students"),
        )
        .outerjoin(models.SchoolCycle, models.SchoolCycle.id == models.StudentEnrollment.cycle_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
        .filter(
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
            models.StudentEnrollment.is_active == True,
        )
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

    rows = (
        query.group_by(
            models.StudentEnrollment.cycle_id,
            models.SchoolCycle.period,
            models.Career.name,
            models.Modality.name,
            models.StudentEnrollment.semester,
            models.Group.name,
        )
        .order_by(models.Career.name, models.Modality.name, models.StudentEnrollment.semester, models.Group.name)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.get("/admin/reports/grade-outcomes", response_model=list[schemas.GradeOutcomeRow], summary="Reporte de aprobacion y reprobacion", tags=["Administracion"])
def get_grade_outcomes_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    teacher_username: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    grades = (
        db.query(models.Grade)
        .outerjoin(models.SubjectAssignment, models.SubjectAssignment.id == models.Grade.assignment_id)
        .all()
    )
    cycle = _resolve_report_cycle(db, cycle_id)
    cycle_filter = cycle.id if cycle else None

    grouped: dict[tuple[Optional[int], Optional[str], Optional[str], Optional[str]], dict] = {}
    for grade in grades:
        assignment = grade.assignment
        if not _grade_matches_filters(
            grade,
            cycle_id=cycle_filter,
            career=career,
            modality=modality,
            semester=semester,
            group_name=group_name,
            teacher_username=teacher_username,
            date_from=date_from,
            date_to=date_to,
        ):
            continue

        subject_name = assignment.subject.name if assignment and assignment.subject else (grade.subject.name if grade.subject else None)
        teacher_name = assignment.teacher.full_name if assignment and assignment.teacher and assignment.teacher.full_name else (
            assignment.teacher.username if assignment and assignment and assignment.teacher else None
        )
        cycle_period = assignment.cycle.period if assignment and assignment.cycle else None
        group_name_for_assignment = assignment.group.name if assignment and assignment.group else None
        key = (grade.assignment_id, subject_name, teacher_name, cycle_period, group_name_for_assignment)
        bucket = grouped.setdefault(
            key,
            {
                "assignment_id": grade.assignment_id,
                "subject_name": subject_name,
                "teacher_name": teacher_name,
                "cycle_period": cycle_period,
                "group_name": group_name_for_assignment,
                "approved_count": 0,
                "failed_count": 0,
                "in_progress_count": 0,
                "total_records": 0,
            },
        )
        bucket["total_records"] += 1
        if grade.status == models.GradeStatus.APROBADA:
            bucket["approved_count"] += 1
        elif grade.status == models.GradeStatus.REPROBADA:
            bucket["failed_count"] += 1
        else:
            bucket["in_progress_count"] += 1

    return list(grouped.values())


@app.get("/admin/reports/finance-summary", response_model=schemas.FinanceSummary, summary="Reporte financiero", tags=["Administracion"])
def get_finance_summary_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    charges_query = (
        db.query(models.Charge)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    cycle = _resolve_report_cycle(db, cycle_id)
    if cycle:
        charges_query = charges_query.filter(models.StudentEnrollment.cycle_id == cycle.id)
    if career:
        charges_query = charges_query.filter(models.Career.name == career)
    if modality:
        charges_query = charges_query.filter(models.Modality.name == modality)
    if semester:
        charges_query = charges_query.filter(models.StudentEnrollment.semester == semester)
    if group_name:
        charges_query = charges_query.filter(models.Group.name == group_name)
    charges_query = _apply_datetime_range(charges_query, models.Charge.due_date, date_from, date_to)

    charges = charges_query.all()
    now = datetime.utcnow()

    total_amount = sum(charge.amount for charge in charges)
    paid = [charge for charge in charges if charge.status == models.PaymentStatus.PAGADO]
    pending = [charge for charge in charges if charge.status == models.PaymentStatus.PENDIENTE]
    overdue = [
        charge
        for charge in charges
        if charge.status in (models.PaymentStatus.PENDIENTE, models.PaymentStatus.VENCIDO) and charge.due_date < now
    ]

    return {
        "total_charges": len(charges),
        "total_charge_amount": total_amount,
        "paid_amount": sum(charge.amount for charge in paid),
        "pending_amount": sum(charge.amount for charge in pending),
        "overdue_amount": sum(charge.amount for charge in overdue),
        "paid_count": len(paid),
        "pending_count": len(pending),
        "overdue_count": len(overdue),
    }


@app.get("/admin/reports/blocked-students", response_model=list[schemas.BlockedStudentRow], summary="Reporte de alumnos bloqueados", tags=["Administracion"])
def get_blocked_students_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    students = db.query(models.User).filter(
        models.User.role == models.UserRole.STUDENT,
        models.User.user_status == models.UserStatus.BLOQUEADO,
    ).all()
    enrollments_query, cycle = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    filtered_student_ids = {enrollment.student_id for enrollment in enrollments_query.all()}
    apply_enrollment_scope = any([
        cycle_id is not None,
        career,
        modality,
        semester,
        group_name,
        date_from,
        date_to,
    ])
    now = datetime.utcnow()
    rows = []
    for student in students:
        if apply_enrollment_scope and student.id not in filtered_student_ids:
            continue
        overdue_charges = [
            charge for charge in student.charges
            if charge.status in (models.PaymentStatus.PENDIENTE, models.PaymentStatus.VENCIDO) and charge.due_date < now
            and _datetime_in_range(charge.due_date, date_from, date_to)
        ]
        pending_charges = [
            charge for charge in student.charges
            if charge.status != models.PaymentStatus.PAGADO
            and _datetime_in_range(charge.due_date, date_from, date_to)
        ]
        rows.append(
            {
                "student_id": student.id,
                "username": student.username,
                "full_name": student.full_name,
                "overdue_charges": len(overdue_charges),
                "overdue_amount": sum(charge.amount for charge in overdue_charges),
                "total_pending_amount": sum(charge.amount for charge in pending_charges),
            }
        )
    return rows


@app.get("/admin/reports/overview", response_model=schemas.AdminOverviewReport, summary="Resumen ejecutivo administrativo", tags=["Administracion"])
def get_admin_overview_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    enrollments_query, cycle = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    enrollments = enrollments_query.all()
    enrollment_ids = [enrollment.id for enrollment in enrollments]
    student_ids = [enrollment.student_id for enrollment in enrollments]
    course_enrollments = (
        db.query(models.CourseEnrollment)
        .filter(models.CourseEnrollment.student_enrollment_id.in_(enrollment_ids or [-1]))
        .all()
    )
    assignments = {ce.assignment_id for ce in course_enrollments if ce.assignment_id}
    teacher_ids = {ce.assignment.teacher_id for ce in course_enrollments if ce.assignment and ce.assignment.teacher_id}
    grades = db.query(models.Grade).filter(models.Grade.course_enrollment_id.isnot(None)).all()
    relevant_grades = [
        grade for grade in grades
        if grade.course_enrollment_id in {ce.id for ce in course_enrollments}
        and _grade_matches_filters(
            grade,
            cycle_id=cycle.id if cycle else None,
            career=career,
            modality=modality,
            semester=semester,
            group_name=group_name,
            date_from=date_from,
            date_to=date_to,
        )
    ]
    scored = [float(grade.score) for grade in relevant_grades if grade.score is not None]
    approved = [grade for grade in relevant_grades if grade.status == models.GradeStatus.APROBADA]
    failed = [grade for grade in relevant_grades if grade.status == models.GradeStatus.REPROBADA]
    in_progress = [grade for grade in relevant_grades if grade.status not in (models.GradeStatus.APROBADA, models.GradeStatus.REPROBADA)]
    blocked_students = (
        db.query(models.User)
        .filter(models.User.id.in_(student_ids or [-1]), models.User.user_status == models.UserStatus.BLOQUEADO)
        .count()
    )
    overdue_amount = sum(
        charge.amount
        for charge in db.query(models.Charge).filter(models.Charge.student_enrollment_id.in_(enrollment_ids or [-1])).all()
        if charge.status in (models.PaymentStatus.PENDIENTE, models.PaymentStatus.VENCIDO) and charge.due_date < datetime.utcnow()
        and _datetime_in_range(charge.due_date, date_from, date_to)
    )
    pending_services = (
        db.query(models.ServiceRequest)
        .filter(
            models.ServiceRequest.student_id.in_(student_ids or [-1]),
            models.ServiceRequest.status != models.ServiceRequestStatus.ENTREGADO,
        )
        .filter(
            models.ServiceRequest.request_date >= _parse_report_datetime(date_from) if date_from else True,
            models.ServiceRequest.request_date <= _parse_report_datetime(date_to, end_of_day=True) if date_to else True,
        )
        .count()
    )
    approval_rate = round((len(approved) / (len(approved) + len(failed)) * 100), 2) if (len(approved) + len(failed)) else 0.0
    failed_rate = round((len(failed) / (len(approved) + len(failed)) * 100), 2) if (len(approved) + len(failed)) else 0.0

    return {
        "cycle_id": cycle.id if cycle else None,
        "cycle_period": cycle.period if cycle else None,
        "total_students": len({enrollment.student_id for enrollment in enrollments}),
        "active_enrollments": sum(1 for enrollment in enrollments if enrollment.is_active),
        "groups_count": len({enrollment.group_id for enrollment in enrollments if enrollment.group_id}),
        "teachers_with_assignments": len(teacher_ids),
        "subjects_with_assignments": len(assignments),
        "average_final_score": round(sum(scored) / len(scored), 2) if scored else 0.0,
        "approval_rate": approval_rate,
        "failed_rate": failed_rate,
        "failed_count": len(failed),
        "in_progress_count": len(in_progress),
        "blocked_students": blocked_students,
        "overdue_amount": overdue_amount,
        "pending_services": pending_services,
    }


@app.get("/admin/reports/enrollment-status", response_model=list[schemas.EnrollmentStatusRow], summary="Resumen de estatus de inscripcion", tags=["Administracion"])
def get_enrollment_status_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    query, _ = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    rows = (
        query.with_entities(
            models.StudentEnrollment.enrollment_status.label("enrollment_status"),
            func.count(models.StudentEnrollment.id).label("total_students"),
        )
        .group_by(models.StudentEnrollment.enrollment_status)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.get("/admin/reports/teacher-workload", response_model=list[schemas.TeacherWorkloadRow], summary="Carga academica por docente", tags=["Administracion"])
def get_teacher_workload_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    semester: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = _resolve_report_cycle(db, cycle_id)
    assignments_query = (
        db.query(models.SubjectAssignment)
        .outerjoin(models.Subject, models.Subject.id == models.SubjectAssignment.subject_id)
    )
    if cycle:
        assignments_query = assignments_query.filter(models.SubjectAssignment.cycle_id == cycle.id)
    if career:
        assignments_query = assignments_query.filter(models.Subject.career == career)
    if semester:
        assignments_query = assignments_query.filter(models.Subject.semester == semester)
    if date_from or date_to:
        assignments_query = assignments_query.filter(models.SubjectAssignment.cycle_id.isnot(None))

    assignments = assignments_query.all()
    grouped: dict[int, dict] = {}
    for assignment in assignments:
        if not assignment.teacher_id:
            continue
        if date_from or date_to:
            cycle_start = assignment.cycle.start_date if assignment.cycle else None
            if not _datetime_in_range(cycle_start, date_from, date_to):
                continue
        bucket = grouped.setdefault(
            assignment.teacher_id,
            {
                "teacher_username": assignment.teacher.username if assignment.teacher else None,
                "teacher_name": assignment.teacher.full_name if assignment.teacher else None,
                "assignments_count": 0,
                "students_count": 0,
                "subjects_count": set(),
                "groups_count": set(),
            },
        )
        bucket["assignments_count"] += 1
        bucket["subjects_count"].add(assignment.subject_id)
        course_enrollments = assignment.course_enrollments or []
        bucket["students_count"] += len({ce.student_enrollment.student_id for ce in course_enrollments if ce.student_enrollment})
        bucket["groups_count"].update({ce.student_enrollment.group_id for ce in course_enrollments if ce.student_enrollment and ce.student_enrollment.group_id})

    return [
        {
            **value,
            "subjects_count": len(value["subjects_count"]),
            "groups_count": len(value["groups_count"]),
        }
        for value in grouped.values()
    ]


@app.get("/admin/reports/academic-risk", response_model=list[schemas.AcademicRiskRow], summary="Alumnos en riesgo academico", tags=["Administracion"])
def get_academic_risk_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    enrollments_query, _ = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    enrollments = enrollments_query.all()
    rows = []
    for enrollment in enrollments:
        course_enrollments = enrollment.course_enrollments or []
        grades = [
            grade for ce in course_enrollments for grade in (ce.grades or [])
            if _grade_matches_filters(
                grade,
                cycle_id=cycle_id,
                career=career,
                modality=modality,
                semester=semester,
                group_name=group_name,
                date_from=date_from,
                date_to=date_to,
            )
        ]
        scores = [float(grade.score) for grade in grades if grade.score is not None]
        failed_count = sum(1 for grade in grades if grade.status == models.GradeStatus.REPROBADA)
        in_progress_count = sum(1 for grade in grades if grade.status == models.GradeStatus.CURSANDO)
        if failed_count == 0 and in_progress_count == 0:
            continue
        rows.append(
            {
                "username": enrollment.student.username if enrollment.student else "",
                "full_name": enrollment.student.full_name if enrollment.student else None,
                "career": enrollment.career.name if enrollment.career else None,
                "semester": enrollment.semester,
                "group_name": enrollment.group.name if enrollment.group else None,
                "failed_count": failed_count,
                "in_progress_count": in_progress_count,
                "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            }
        )
    rows.sort(key=lambda item: (-item["failed_count"], -item["in_progress_count"], item["average_score"]))
    return rows


@app.get("/admin/reports/service-summary", response_model=list[schemas.ServiceSummaryRow], summary="Resumen de servicios escolares", tags=["Administracion"])
def get_service_summary_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    query = (
        db.query(models.ServiceRequest)
        .join(models.User, models.User.id == models.ServiceRequest.student_id)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.student_id == models.User.id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    cycle = _resolve_report_cycle(db, cycle_id)
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
    query = _apply_datetime_range(query, models.ServiceRequest.request_date, date_from, date_to)

    rows = (
        query.with_entities(
            models.ServiceRequest.type.label("service_type"),
            models.ServiceRequest.status.label("status"),
            func.count(models.ServiceRequest.id).label("total_requests"),
        )
        .group_by(models.ServiceRequest.type, models.ServiceRequest.status)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.get("/admin/reports/charge-breakdown", response_model=list[schemas.ChargeBreakdownRow], summary="Desglose financiero por tipo de cargo", tags=["Administracion"])
def get_charge_breakdown_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    query = (
        db.query(models.Charge)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    cycle = _resolve_report_cycle(db, cycle_id)
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
    query = _apply_datetime_range(query, models.Charge.due_date, date_from, date_to)

    rows = (
        query.with_entities(
            models.Charge.charge_type.label("charge_type"),
            models.Charge.status.label("status"),
            func.count(models.Charge.id).label("total_charges"),
            func.coalesce(func.sum(models.Charge.amount), 0).label("total_amount"),
        )
        .group_by(models.Charge.charge_type, models.Charge.status)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.put("/admin/student-enrollments/move-group", response_model=schemas.StudentEnrollmentWithRelations, summary="Mover alumno a grupo", tags=["Administracion"])
def move_student_to_group(
    body: schemas.MoveStudentGroupRequest,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == body.cycle_id).first()
        if body.cycle_id
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
    if not enrollment:
        enrollment = _sync_student_enrollment_from_legacy(
            db,
            student,
            cycle_id=cycle.id,
            reason=body.reason or "Creacion de inscripcion desde movimiento de grupo",
        )
        if not enrollment:
            enrollment = models.StudentEnrollment(
                student_id=student.id,
                cycle_id=cycle.id,
                career_id=student.career_id,
                modality_id=body.modality_id or student.modality_id,
                semester=student.semestre,
                enrollment_status=student.enrollment_status,
                is_active=student.user_status != models.UserStatus.BAJA and _is_active_enrollment_status(student.enrollment_status),
                change_reason=body.reason,
            )
            _ensure_single_active_enrollment_per_cycle(
                db,
                student_id=student.id,
                cycle_id=cycle.id,
                enrollment_status=enrollment.enrollment_status,
            )
            db.add(enrollment)
            db.flush()

    if body.modality_id is not None:
        modality = db.query(models.Modality).filter(models.Modality.id == body.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
        student.modality_id = modality.id
        student.modalidad = modality.name
        enrollment.modality_id = modality.id

    group = _get_or_create_group(
        db,
        group_name=body.group_name,
        modality_id=enrollment.modality_id or student.modality_id,
    )

    enrollment.group_id = group.id if group else None
    enrollment.change_reason = body.reason or enrollment.change_reason
    student.grupo = group.name if group else None

    db.commit()
    db.refresh(enrollment)
    return enrollment


@app.put("/admin/group-actions/bulk-enrollment", summary="Cambiar inscripción de todo un grupo", tags=["Administracion"])
def bulk_update_group_enrollment(body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    grupo = body.get("grupo", "").strip()
    carrera = body.get("carrera", "").strip()
    enrollment_status = body.get("enrollment_status", "").strip()
    usernames = body.get("usernames")  # Opcional: lista de matrículas específicas

    if not grupo or not enrollment_status:
        raise HTTPException(status_code=400, detail="Faltan grupo o enrollment_status")

    valid = [e.value for e in models.EnrollmentStatus]
    if enrollment_status not in valid:
        raise HTTPException(status_code=400, detail=f"Estatus inválido. Opciones: {valid}")

    enrollments, active_cycle = _get_group_member_enrollments(
        db,
        group_name=grupo,
        career_name=carrera or None,
        usernames=usernames,
    )
    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        student.enrollment_status = enrollment_status
        _ensure_single_active_enrollment_per_cycle(
            db,
            student_id=student.id,
            cycle_id=active_cycle.id,
            current_enrollment_id=enrollment.id,
            enrollment_status=models.EnrollmentStatus(enrollment_status),
        )
        enrollment.enrollment_status = enrollment_status
        enrollment.is_active = _is_active_enrollment_status(models.EnrollmentStatus(enrollment_status))
    db.commit()
    return {"updated": len(enrollments), "enrollment_status": enrollment_status}


@app.post("/admin/group-actions/bulk-assign", summary="Asignar materia a todo un grupo", tags=["Administracion"])
def bulk_assign_group_subject(body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    grupo = body.get("grupo", "").strip()
    carrera = body.get("carrera", "").strip()
    assignment_id = body.get("assignment_id")
    usernames = body.get("usernames")  # Opcional: lista específica

    if not grupo or not assignment_id:
        raise HTTPException(status_code=400, detail="Faltan grupo o assignment_id")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if assignment.group and assignment.group.name != grupo:
        raise HTTPException(status_code=400, detail=f"La asignación pertenece al grupo {assignment.group.name}. Selecciona el mismo grupo para evitar mezclar calificaciones")

    enrollments, _ = _get_group_member_enrollments(
        db,
        group_name=grupo,
        career_name=carrera or None,
        usernames=usernames,
    )
    enrolled = 0
    reassigned = 0

    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        # Ya en esta asignación exacta → skip
        already = db.query(models.Grade).filter(
            models.Grade.student_id == student.id,
            models.Grade.assignment_id == assignment_id,
            models.Grade.attempt_type == models.AttemptType.REGULAR,
        ).first()
        if already:
            continue

        # Tiene grade para la misma materia → reasignar
        existing = db.query(models.Grade).filter(
            models.Grade.student_id == student.id,
            models.Grade.subject_id == assignment.subject_id,
            models.Grade.attempt_type == models.AttemptType.REGULAR,
        ).first()
        if existing:
            course_enrollment = _get_or_create_course_enrollment(
                db,
                student=student,
                assignment=assignment,
                attempt_type=models.AttemptType.REGULAR,
                status=models.GradeStatus.CURSANDO,
            )
            existing.assignment_id = assignment.id
            existing.course_enrollment_id = course_enrollment.id
            existing.status = models.GradeStatus.CURSANDO
            reassigned += 1
        else:
            db.add(models.Grade(
                student_id=student.id,
                subject_id=assignment.subject_id,
                assignment_id=assignment.id,
                course_enrollment_id=_get_or_create_course_enrollment(
                    db,
                    student=student,
                    assignment=assignment,
                    attempt_type=models.AttemptType.REGULAR,
                    status=models.GradeStatus.CURSANDO,
                ).id,
                attempt_type=models.AttemptType.REGULAR,
                status=models.GradeStatus.CURSANDO,
            ))
            enrolled += 1

    db.commit()
    return {"enrolled": enrolled, "reassigned": reassigned, "total": enrolled + reassigned}


@app.get("/admin/school-cycles/all", summary="Todos los ciclos escolares", tags=["Configuracion"])
def get_all_school_cycles(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    cycles = db.query(models.SchoolCycle).order_by(models.SchoolCycle.id.desc()).all()
    result = []
    for c in cycles:
        payment_count = db.query(models.Payment).filter(
            models.Payment.concept.like(f"%{c.period}%") if c.period else False
        ).count() if c.period else 0
        charges = (
            db.query(models.Charge)
            .join(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
            .filter(models.StudentEnrollment.cycle_id == c.id)
            .all()
        )
        total_amount = sum(float(charge.amount or 0) for charge in charges)
        pending_amount = sum(float(charge.amount or 0) for charge in charges if charge.status == models.PaymentStatus.PENDIENTE)
        paid_amount = sum(float(charge.amount or 0) for charge in charges if charge.status == models.PaymentStatus.PAGADO)
        students_affected = len({charge.student_id for charge in charges if charge.student_id})
        result.append({
            "id": c.id,
            "period": c.period,
            "start_date": str(c.start_date)[:10] if c.start_date else None,
            "end_date": str(c.end_date)[:10] if c.end_date else None,
            "is_active": c.is_active,
            "monthly_amount": c.monthly_amount,
            "payment_count": payment_count,
            "total_amount": total_amount,
            "pending_amount": pending_amount,
            "paid_amount": paid_amount,
            "students_affected": students_affected,
        })
    return result


@app.get("/admin/school-cycles/{cycle_id}", response_model=schemas.SchoolCycle, summary="Detalle de ciclo escolar", tags=["Configuracion"])
def get_school_cycle_detail(cycle_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")
    return cycle


@app.put("/admin/school-cycles/{cycle_id}", response_model=schemas.SchoolCycle, summary="Actualizar ciclo escolar", tags=["Configuracion"])
def update_school_cycle(
    cycle_id: int,
    payload: schemas.SchoolCycleCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")
    if not (payload.period or "").strip():
        raise HTTPException(status_code=400, detail="El periodo del ciclo es obligatorio")
    if payload.start_date >= payload.end_date:
        raise HTTPException(status_code=400, detail="La fecha de inicio debe ser anterior a la fecha de fin")
    if not payload.tuitions:
        raise HTTPException(status_code=400, detail="Debes capturar al menos un costo por carrera y modalidad")

    seen_pairs: set[tuple[int, int]] = set()
    for tuition in payload.tuitions:
        key = (tuition.career_id, tuition.modality_id)
        if key in seen_pairs:
            raise HTTPException(status_code=400, detail="Hay costos duplicados para la misma carrera y modalidad")
        seen_pairs.add(key)

    try:
        cycle.period = payload.period.strip()
        cycle.start_date = payload.start_date
        cycle.end_date = payload.end_date
        cycle.monthly_amount = payload.monthly_amount

        db.query(models.CycleTuition).filter(models.CycleTuition.cycle_id == cycle.id).delete()
        db.flush()
        for tuition in payload.tuitions:
            db.add(models.CycleTuition(
                cycle_id=cycle.id,
                career_id=tuition.career_id,
                modality_id=tuition.modality_id,
                amount=tuition.amount,
            ))
        db.commit()
        db.refresh(cycle)
        return cycle
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo actualizar el ciclo escolar: {exc}")


@app.delete("/admin/school-cycles/{cycle_id}", tags=["Configuracion"], summary="Eliminar ciclo escolar")
def delete_school_cycle(
    cycle_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")

    try:
        enrollment_ids = [
            row.id for row in db.query(models.StudentEnrollment.id)
            .filter(models.StudentEnrollment.cycle_id == cycle.id)
            .all()
        ]
        charge_ids = []
        if enrollment_ids:
            charge_ids = [
                row.id for row in db.query(models.Charge.id)
                .filter(models.Charge.student_enrollment_id.in_(enrollment_ids))
                .all()
            ]

        if charge_ids:
            db.query(models.Payment).filter(models.Payment.charge_id.in_(charge_ids)).delete(synchronize_session=False)
            db.query(models.Charge).filter(models.Charge.id.in_(charge_ids)).delete(synchronize_session=False)

        db.query(models.SubjectAssignment).filter(models.SubjectAssignment.cycle_id == cycle.id).update(
            {"cycle_id": None},
            synchronize_session=False,
        )
        db.query(models.StudentEnrollment).filter(models.StudentEnrollment.cycle_id == cycle.id).delete(synchronize_session=False)
        db.query(models.CycleTuition).filter(models.CycleTuition.cycle_id == cycle.id).delete(synchronize_session=False)
        was_active = bool(cycle.is_active)
        cycle_period = cycle.period
        db.delete(cycle)
        db.flush()

        if was_active:
            replacement_cycle = (
                db.query(models.SchoolCycle)
                .filter(models.SchoolCycle.id != cycle_id)
                .order_by(models.SchoolCycle.id.desc())
                .first()
            )
            if replacement_cycle:
                replacement_cycle.is_active = True

        db.commit()
        return {"ok": True, "deleted_cycle_id": cycle_id, "deleted_cycle_period": cycle_period}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo eliminar el ciclo escolar: {exc}")


@app.patch("/admin/school-cycles/{cycle_id}/set-active", response_model=schemas.SchoolCycle, summary="Activar ciclo escolar", tags=["Configuracion"])
def set_active_school_cycle(
    cycle_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")
    db.query(models.SchoolCycle).update({"is_active": False})
    cycle.is_active = True
    db.commit()
    db.refresh(cycle)
    return cycle


@app.get("/admin/teachers", response_model=list[schemas.UserListItem], summary="Listar docentes", tags=["Administracion"])
def get_all_teachers(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    teachers = (
        db.query(
            models.User.id,
            models.User.username,
            models.User.email,
            models.User.full_name,
            models.User.role,
            models.User.moodle_id,
            models.User.user_status,
            models.User.enrollment_status,
            models.User.career_id,
            models.User.carrera,
            models.User.modality_id,
            models.User.modalidad,
            models.User.semestre,
            models.User.grupo,
        )
        .filter(models.User.role == models.UserRole.TEACHER)
        .order_by(models.User.id.asc())
        .all()
    )
    return [row._asdict() for row in teachers]


@app.put("/admin/teachers/{username}", response_model=schemas.User, summary="Actualizar docente", tags=["Administracion"])
def update_teacher(username: str, teacher_update: schemas.UserUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.TEACHER).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    if teacher_update.full_name is not None:
        db_user.full_name = teacher_update.full_name
    if teacher_update.email is not None:
        db_user.email = teacher_update.email
    if teacher_update.password:
        db_user.hashed_password = auth.get_password_hash(teacher_update.password)

    db.commit()
    db.refresh(db_user)
    return db_user


@app.post("/admin/teachers", response_model=schemas.User, summary="Crear docente", tags=["Administracion"])
def create_teacher(teacher: schemas.UserCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == teacher.username).first():
        raise HTTPException(status_code=400, detail="El usuario/matrícula ya está registrado")

    if teacher.email and db.query(models.User).filter(models.User.email == teacher.email).first():
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado por otro usuario")

    hashed_password = auth.get_password_hash(teacher.password)
    new_user = models.User(
        username=teacher.username,
        email=teacher.email,
        full_name=teacher.full_name,
        role=models.UserRole.TEACHER,
        hashed_password=hashed_password,
    )
    db.add(new_user)
    try:
        db.commit()
        db.refresh(new_user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error al guardar: verifica que el usuario y correo sean únicos")
    return new_user


@app.get("/admin/subjects", response_model=list[schemas.Subject], summary="Listar materias", tags=["Administracion"])
def get_all_subjects(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Subject).all()


@app.post("/admin/subjects", response_model=schemas.Subject, summary="Crear materia", tags=["Administracion"])
async def create_subject(subject: schemas.SubjectCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    new_subject = models.Subject(
        name=subject.name,
        credits=subject.credits,
        semester=subject.semester,
        career=subject.career,
        modality=subject.modality,
    )
    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)
    
    if new_subject.modality and new_subject.modality.lower() in ["virtual", "hibrido", "híbrido"]:
        await _sync_subject_to_moodle_internal(db, subject=new_subject, category_id=1)
        db.refresh(new_subject)

    return new_subject


@app.put("/admin/subjects/{subject_id}", response_model=schemas.SubjectWithTeacher, summary="Actualizar materia", tags=["Administracion"])
async def update_subject(subject_id: int, subject_update: schemas.SubjectUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not db_subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    if subject_update.name is not None:
        db_subject.name = subject_update.name
    if subject_update.credits is not None:
        db_subject.credits = subject_update.credits
    if subject_update.semester is not None:
        db_subject.semester = subject_update.semester
    if subject_update.career is not None:
        db_subject.career = subject_update.career
    if subject_update.modality is not None:
        db_subject.modality = subject_update.modality

    db.commit()
    
    if db_subject.modality and db_subject.modality.lower() in ["virtual", "hibrido", "híbrido"] and not db_subject.moodle_course_id:
        await _sync_subject_to_moodle_internal(db, subject=db_subject, category_id=1)

    teacher = None
    assignment = None
    if subject_update.teacher_username is not None:
        teacher = db.query(models.User).filter(
            models.User.username == subject_update.teacher_username,
            models.User.role == models.UserRole.TEACHER,
        ).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Docente no encontrado")

        active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
        cycle_id = active_cycle.id if active_cycle else None
        assignment = db.query(models.SubjectAssignment).filter(
            models.SubjectAssignment.subject_id == db_subject.id,
            models.SubjectAssignment.cycle_id == cycle_id,
        ).first()
        if assignment:
            assignment.teacher_id = teacher.id
        else:
            assignment = models.SubjectAssignment(
                subject_id=db_subject.id,
                teacher_id=teacher.id,
                cycle_id=cycle_id,
            )
            db.add(assignment)

    db.commit()
    db.refresh(db_subject)
    return {
        "id": db_subject.id,
        "name": db_subject.name,
        "credits": db_subject.credits,
        "semester": db_subject.semester,
        "career": db_subject.career,
        "teacher_id": assignment.teacher_id if assignment else None,
        "teacher_username": teacher.username if teacher else None,
    }


# ----------------------------
# Asignaciones de docente a materia por ciclo
# ----------------------------

@app.get("/admin/subject-assignments", summary="Listar asignaciones", tags=["Administracion"])
def get_subject_assignments(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Lista asignaciones. Si cycle_id es None devuelve las del ciclo activo."""
    query = db.query(models.SubjectAssignment)
    if cycle_id:
        query = query.filter(models.SubjectAssignment.cycle_id == cycle_id)
    else:
        active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
        if active_cycle:
            query = query.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    assignments = query.all()
    from fastapi.encoders import jsonable_encoder as _je
    result = []
    for a in assignments:
        student_count = len({
            ce.student_enrollment.student_id
            for ce in a.course_enrollments
            if ce.student_enrollment and ce.student_enrollment.student_id
        })
        item = _je(schemas.SubjectAssignment.model_validate(a))
        item["student_count"] = student_count
        item["group_name"] = a.group.name if a.group else None
        result.append(item)
    return result


@app.post("/admin/subject-assignments", response_model=schemas.SubjectAssignment, summary="Asignar docente a materia", tags=["Administracion"])
def create_subject_assignment(
    data: schemas.SubjectAssignmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    subject = db.query(models.Subject).filter(models.Subject.id == data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    teacher = db.query(models.User).filter(
        models.User.username == data.teacher_username,
        models.User.role == models.UserRole.TEACHER,
    ).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    cycle_id = data.cycle_id
    if not cycle_id:
        active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
        cycle_id = active_cycle.id if active_cycle else None
    if data.group_id is None:
        raise HTTPException(status_code=400, detail="Debes seleccionar un grupo para la asignación")

    group = db.query(models.Group).filter(models.Group.id == data.group_id, models.Group.is_active == True).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    # Verificar duplicado
    existing = db.query(models.SubjectAssignment).filter(
        models.SubjectAssignment.subject_id == data.subject_id,
        models.SubjectAssignment.teacher_id == teacher.id,
        models.SubjectAssignment.cycle_id == cycle_id,
        models.SubjectAssignment.group_id == data.group_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Este docente ya tiene esta materia asignada para ese grupo en el ciclo indicado")

    assignment = models.SubjectAssignment(
        subject_id=data.subject_id,
        teacher_id=teacher.id,
        cycle_id=cycle_id,
        group_id=group.id,
    )
    db.add(assignment)
    db.flush()  # Obtener el ID sin hacer commit todavía

    # Auto-vincular alumnos que tengan esta materia sin docente asignado (assignment_id IS NULL)
    # Solo se vinculan los que aún no tienen asignación → son los que no pertenecen a ninguna sección
    unlinked_grades = (
        db.query(models.Grade)
        .filter(
            models.Grade.subject_id == data.subject_id,
            models.Grade.assignment_id.is_(None),
            models.Grade.attempt_type == models.AttemptType.REGULAR,
        )
        .all()
    )
    linked_count = 0
    for grade in unlinked_grades:
        active_enrollment = _get_active_student_enrollment(db, grade.student_id) if grade.student_id else None
        if assignment.group_id:
            if not active_enrollment or active_enrollment.group_id != assignment.group_id:
                continue
        grade.assignment_id = assignment.id
        if grade.student:
            grade.course_enrollment_id = _get_or_create_course_enrollment(
                db,
                student=grade.student,
                assignment=assignment,
                attempt_type=grade.attempt_type,
                status=grade.status,
            ).id
        linked_count += 1

    db.commit()
    db.refresh(assignment)

    # Devolver el assignment con metadato de alumnos vinculados (usando JSONResponse para incluirlo)
    from fastapi.responses import JSONResponse as _JSONResponse
    from fastapi.encoders import jsonable_encoder as _jsonable_encoder

    data = _jsonable_encoder(assignment)
    data["auto_linked"] = linked_count
    return _JSONResponse(content=data)


@app.put("/admin/subject-assignments/{assignment_id}", summary="Cambiar docente de asignación", tags=["Administracion"])
def update_subject_assignment(
    assignment_id: int,
    data: schemas.SubjectAssignmentUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if data.teacher_username is not None:
        teacher = db.query(models.User).filter(
            models.User.username == data.teacher_username,
            models.User.role == models.UserRole.TEACHER,
        ).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Docente no encontrado")
        existing = db.query(models.SubjectAssignment).filter(
            models.SubjectAssignment.subject_id == assignment.subject_id,
            models.SubjectAssignment.teacher_id == teacher.id,
            models.SubjectAssignment.cycle_id == assignment.cycle_id,
            models.SubjectAssignment.group_id == (data.group_id if data.group_id is not None else assignment.group_id),
            models.SubjectAssignment.id != assignment_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Este docente ya tiene esta materia asignada para ese grupo en el ciclo")
        db.query(models.Grade).filter(models.Grade.assignment_id == assignment_id).update(
            {"assignment_id": assignment_id}, synchronize_session=False
        )
        assignment.teacher_id = teacher.id
    if data.group_id is not None:
        group = db.query(models.Group).filter(models.Group.id == data.group_id, models.Group.is_active == True).first()
        if not group:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")
        duplicate = db.query(models.SubjectAssignment).filter(
            models.SubjectAssignment.subject_id == assignment.subject_id,
            models.SubjectAssignment.teacher_id == assignment.teacher_id,
            models.SubjectAssignment.cycle_id == assignment.cycle_id,
            models.SubjectAssignment.group_id == group.id,
            models.SubjectAssignment.id != assignment_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Ya existe una asignación igual para ese grupo")
        assignment.group_id = group.id
    db.commit()
    db.refresh(assignment)
    return assignment


@app.delete("/admin/subject-assignments/{assignment_id}", summary="Eliminar asignación", tags=["Administracion"])
def delete_subject_assignment(
    assignment_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    db.delete(assignment)
    db.commit()
    return {"detail": "Asignación eliminada"}


@app.put("/admin/grades/{grade_id}", response_model=schemas.Grade, summary="Actualizar calificacion (admin)", tags=["Administracion"])
def update_grade(grade_id: int, grade_update: schemas.GradeUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")

    _apply_grade_payload(db_grade, grade_update)

    db.commit()
    db.refresh(db_grade)
    return db_grade


@app.get("/admin/payments", response_model=list[schemas.PaymentListItem], summary="Listar pagos", tags=["Administracion"])
def get_all_payments(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    payments = (
        db.query(
            models.Payment.id,
            models.Payment.student_id,
            models.Payment.charge_id,
            models.Payment.concept,
            models.Payment.amount,
            models.Payment.due_date,
            models.Payment.status,
            models.User.username.label("student_username"),
            models.User.full_name.label("student_full_name"),
        )
        .join(models.User, models.User.id == models.Payment.student_id)
        .order_by(models.Payment.id.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "student_id": row.student_id,
            "charge_id": row.charge_id,
            "concept": row.concept,
            "amount": row.amount,
            "due_date": row.due_date,
            "status": row.status,
            "student": {
                "username": row.student_username,
                "full_name": row.student_full_name,
            },
        }
        for row in payments
    ]


@app.get("/admin/charges", response_model=list[schemas.ChargeListItem], summary="Listar cargos", tags=["Administracion"])
def get_all_charges(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    charges = (
        db.query(
            models.Charge.id,
            models.Charge.student_id,
            models.Charge.student_enrollment_id,
            models.StudentEnrollment.cycle_id.label("cycle_id"),
            models.SchoolCycle.period.label("cycle_period"),
            models.Charge.charge_type,
            models.Charge.concept,
            models.Charge.period_label,
            models.Charge.amount,
            models.Charge.due_date,
            models.Charge.status,
            models.Charge.created_at,
            models.User.username.label("student_username"),
            models.User.full_name.label("student_full_name"),
        )
        .join(models.User, models.User.id == models.Charge.student_id)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
        .outerjoin(models.SchoolCycle, models.SchoolCycle.id == models.StudentEnrollment.cycle_id)
        .order_by(models.Charge.id.desc())
    )
    if cycle_id:
        charges = charges.filter(models.StudentEnrollment.cycle_id == cycle_id)
    charges = charges.all()
    return [
        {
            "id": row.id,
            "student_id": row.student_id,
            "student_enrollment_id": row.student_enrollment_id,
            "cycle_id": row.cycle_id,
            "cycle_period": row.cycle_period,
            "charge_type": row.charge_type,
            "concept": row.concept,
            "period_label": row.period_label,
            "amount": row.amount,
            "due_date": row.due_date,
            "status": row.status,
            "created_at": row.created_at,
            "student": {
                "username": row.student_username,
                "full_name": row.student_full_name,
            },
        }
        for row in charges
    ]


@app.post("/admin/charges", response_model=schemas.ChargeWithStudent, summary="Crear cargo", tags=["Administracion"])
def create_charge(charge: schemas.ChargeCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(models.User.username == charge.student_username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    enrollment = _get_student_enrollment_for_charge(
        db,
        student=student,
        cycle_id=charge.cycle_id,
        student_enrollment_id=charge.student_enrollment_id,
    )

    _ensure_unique_charge_for_enrollment_period(
        db,
        student_enrollment_id=enrollment.id if enrollment else None,
        concept=charge.concept,
        period_label=charge.period_label,
    )

    new_charge = models.Charge(
        student_id=student.id,
        student_enrollment_id=enrollment.id if enrollment else None,
        charge_type=charge.charge_type,
        concept=charge.concept,
        period_label=charge.period_label,
        amount=charge.amount,
        due_date=charge.due_date,
        status=charge.status,
    )
    db.add(new_charge)
    db.flush()
    _ensure_payment_for_charge(db, new_charge)
    db.commit()
    db.refresh(new_charge)
    return new_charge


@app.put("/admin/charges/{charge_id}", response_model=schemas.Charge, summary="Actualizar cargo", tags=["Administracion"])
def update_charge(charge_id: int, charge_update: schemas.ChargeUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_charge = db.query(models.Charge).filter(models.Charge.id == charge_id).first()
    if not db_charge:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")

    next_concept = charge_update.concept if charge_update.concept is not None else db_charge.concept
    next_period_label = charge_update.period_label if charge_update.period_label is not None else db_charge.period_label
    _ensure_unique_charge_for_enrollment_period(
        db,
        student_enrollment_id=db_charge.student_enrollment_id,
        concept=next_concept,
        period_label=next_period_label,
        current_charge_id=db_charge.id,
    )

    if charge_update.charge_type is not None:
        db_charge.charge_type = charge_update.charge_type
    if charge_update.concept is not None:
        db_charge.concept = charge_update.concept
    if charge_update.period_label is not None:
        db_charge.period_label = charge_update.period_label
    if charge_update.amount is not None:
        db_charge.amount = charge_update.amount
    if charge_update.due_date is not None:
        db_charge.due_date = charge_update.due_date
    if charge_update.status is not None:
        db_charge.status = charge_update.status

    _ensure_payment_for_charge(db, db_charge)
    db.commit()
    db.refresh(db_charge)
    return db_charge


@app.delete("/admin/charges/{charge_id}", tags=["Administracion"], summary="Eliminar cargo")
def delete_charge(charge_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_charge = db.query(models.Charge).filter(models.Charge.id == charge_id).first()
    if not db_charge:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    try:
        db.query(models.Payment).filter(models.Payment.charge_id == db_charge.id).delete(synchronize_session=False)
        db.delete(db_charge)
        db.commit()
        return {"ok": True, "deleted_charge_id": charge_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo eliminar el cargo: {exc}")


@app.post("/admin/payments", response_model=schemas.PaymentWithStudent, summary="Crear pago", tags=["Administracion"])
def create_payment(payment: schemas.PaymentCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_student = db.query(models.User).filter(models.User.username == payment.student_username).first()
    if not db_student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    new_payment = models.Payment(
        student_id=db_student.id,
        concept=payment.concept,
        amount=payment.amount,
        due_date=payment.due_date,
        status=payment.status,
    )
    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)
    return new_payment


@app.put("/admin/payments/{payment_id}", response_model=schemas.Payment, summary="Actualizar pago", tags=["Administracion"])
def update_payment(payment_id: int, payment_update: schemas.PaymentUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not db_payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    if payment_update.concept is not None:
        db_payment.concept = payment_update.concept
    if payment_update.amount is not None:
        db_payment.amount = payment_update.amount
    if payment_update.due_date is not None:
        db_payment.due_date = payment_update.due_date
    if payment_update.status is not None:
        db_payment.status = payment_update.status
        if db_payment.charge:
            db_payment.charge.status = payment_update.status

    db.commit()
    db.refresh(db_payment)
    return db_payment


@app.get("/admin/services", response_model=list[schemas.ServiceRequestListItem], summary="Listar tramites", tags=["Administracion"])
def get_all_services(current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    services = (
        db.query(
            models.ServiceRequest.id,
            models.ServiceRequest.student_id,
            models.ServiceRequest.type,
            models.ServiceRequest.status,
            models.ServiceRequest.request_date,
            models.ServiceRequest.attachment_filename,
            models.ServiceRequest.attachment_path,
            models.User.username.label("student_username"),
            models.User.full_name.label("student_full_name"),
        )
        .join(models.User, models.User.id == models.ServiceRequest.student_id)
        .order_by(models.ServiceRequest.id.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "student_id": row.student_id,
            "type": row.type,
            "status": row.status,
            "request_date": row.request_date,
            "attachment_filename": row.attachment_filename,
            "attachment_path": row.attachment_path,
            "student": {
                "username": row.student_username,
                "full_name": row.student_full_name,
            },
        }
        for row in services
    ]


@app.post("/admin/services", response_model=schemas.ServiceRequestWithStudent, summary="Crear tramite", tags=["Administracion"])
def create_service(service: schemas.ServiceRequestCreate, current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    db_student = db.query(models.User).filter(models.User.username == service.student_username).first()
    if not db_student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    new_service = models.ServiceRequest(
        student_id=db_student.id,
        type=service.type,
        status=service.status,
        request_date=service.request_date,
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@app.post("/users/me/services", response_model=schemas.ServiceRequest, summary="Solicitar tramite", tags=["Usuario"])
def create_user_service(
    service: schemas.ServiceRequestSelfCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    new_service = models.ServiceRequest(
        student_id=current_user.id,
        type=service.type,
        status=models.ServiceRequestStatus.EN_PROCESO,
        request_date=service.request_date,
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@app.post("/users/me/services/with-document", response_model=schemas.ServiceRequest, summary="Solicitar tramite con documento", tags=["Usuario"])
async def create_user_service_with_document(
    type: str = Form(...),
    request_date: str = Form(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    service_payload = schemas.ServiceRequestSelfCreate(type=type, request_date=request_date)
    original_filename, stored_relative_path = _store_service_attachment(
        student_username=current_user.username,
        file=file,
    )
    new_service = models.ServiceRequest(
        student_id=current_user.id,
        type=service_payload.type,
        status=models.ServiceRequestStatus.EN_PROCESO,
        request_date=service_payload.request_date,
        attachment_filename=original_filename,
        attachment_path=stored_relative_path,
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@app.get("/users/me/services/{service_id}/attachment", summary="Descargar adjunto de tramite propio", tags=["Usuario"])
def download_user_service_attachment(
    service_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    service = (
        db.query(models.ServiceRequest)
        .filter(
            models.ServiceRequest.id == service_id,
            models.ServiceRequest.student_id == current_user.id,
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")
    file_path = _service_attachment_absolute_path(service.attachment_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(path=file_path, filename=service.attachment_filename or file_path.name)


@app.put("/admin/services/{service_id}", response_model=schemas.ServiceRequest, summary="Actualizar tramite", tags=["Administracion"])
def update_service(service_id: int, service_update: schemas.ServiceRequestUpdate, current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    db_service = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == service_id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")

    if service_update.type is not None:
        db_service.type = service_update.type
    if service_update.status is not None:
        db_service.status = service_update.status
    if service_update.request_date is not None:
        db_service.request_date = service_update.request_date

    db.commit()
    db.refresh(db_service)
    return db_service


@app.delete("/admin/services/{service_id}", status_code=204, summary="Eliminar tramite", tags=["Administracion"])
def delete_service(service_id: int, current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    db_service = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == service_id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")
    db.delete(db_service)
    db.commit()


@app.get("/admin/academic-services", summary="Listar tramites academicos enriquecidos", tags=["Administracion"])
def read_admin_academic_services(current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    rows = db.execute(text("""
        SELECT
            sr.id,
            sr.student_id,
            u.username AS student_username,
            u.full_name AS student_name,
            sr.type,
            sr.subject,
            sr.description,
            sr.status,
            sr.request_date,
            sr.attachment_filename,
            sr.admin_response,
            sr.updated_at,
            sr.closed_at,
            sr.history_json
        FROM service_requests sr
        JOIN users u ON u.id = sr.student_id
        WHERE COALESCE(sr.is_support_ticket, FALSE) = FALSE
        ORDER BY sr.request_date DESC, sr.id DESC
    """)).fetchall()
    return [_serialize_ticket_row(row) for row in rows]


@app.get("/admin/support-tickets", summary="Listar tickets de soporte", tags=["Administracion"])
def read_admin_support_tickets(current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    rows = db.execute(text("""
        SELECT
            sr.id,
            sr.student_id,
            u.username AS student_username,
            u.full_name AS student_name,
            sr.type,
            sr.subject,
            sr.description,
            sr.source_system,
            sr.status,
            sr.request_date,
            sr.attachment_filename,
            sr.admin_response,
            sr.updated_at,
            sr.closed_at,
            sr.history_json
        FROM service_requests sr
        JOIN users u ON u.id = sr.student_id
        WHERE COALESCE(sr.is_support_ticket, FALSE) = TRUE
        ORDER BY sr.request_date DESC, sr.id DESC
    """)).fetchall()
    return [_serialize_ticket_row(row) for row in rows]


@app.put("/admin/support-tickets/{ticket_id}", summary="Responder ticket de soporte", tags=["Administracion"])
def update_admin_support_ticket(ticket_id: int, payload: dict, current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    row = db.execute(text("""
        SELECT id, status, history_json
        FROM service_requests
        WHERE id = :ticket_id AND COALESCE(is_support_ticket, FALSE) = TRUE
    """), {"ticket_id": ticket_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    status_value = payload.get("status") or row._mapping.get("status") or models.ServiceRequestStatus.EN_PROCESO.value
    admin_response = payload.get("admin_response")
    close_ticket = bool(payload.get("close_ticket"))
    closed_at = datetime.utcnow() if close_ticket else None
    if close_ticket:
        status_value = models.ServiceRequestStatus.ENTREGADO.value

    history_json = row._mapping.get("history_json")
    if admin_response:
        history_json = _append_ticket_history(
            history_json,
            actor=current_user.username,
            action="admin_response",
            message=admin_response,
            status_value=status_value,
        )
    if close_ticket:
        history_json = _append_ticket_history(
            history_json,
            actor=current_user.username,
            action="close_ticket",
            message="Ticket cerrado por administracion",
            status_value=status_value,
        )

    db.execute(text("""
        UPDATE service_requests
        SET status = :status,
            admin_response = COALESCE(:admin_response, admin_response),
            closed_at = COALESCE(:closed_at, closed_at),
            updated_at = :updated_at,
            history_json = :history_json
        WHERE id = :ticket_id
    """), {
        "ticket_id": ticket_id,
        "status": status_value,
        "admin_response": admin_response,
        "closed_at": closed_at,
        "updated_at": datetime.utcnow(),
        "history_json": history_json,
    })
    db.commit()

    updated = db.execute(text("""
        SELECT
            sr.id,
            sr.student_id,
            u.username AS student_username,
            u.full_name AS student_name,
            sr.type,
            sr.subject,
            sr.description,
            sr.source_system,
            sr.status,
            sr.request_date,
            sr.attachment_filename,
            sr.admin_response,
            sr.updated_at,
            sr.closed_at,
            sr.history_json
        FROM service_requests sr
        JOIN users u ON u.id = sr.student_id
        WHERE sr.id = :ticket_id
    """), {"ticket_id": ticket_id}).fetchone()
    return _serialize_ticket_row(updated)


@app.get("/admin/notifications", summary="Notificaciones del administrador", tags=["Administracion"])
def read_admin_notifications(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    _ensure_notification_schema(db)
    notifications: list[dict] = []

    pending_services = db.query(models.ServiceRequest).filter(models.ServiceRequest.status == models.ServiceRequestStatus.EN_PROCESO).count()
    if pending_services:
        _push_notification(
            notifications,
            notif_type="services",
            title="Tramites pendientes",
            message=f"Hay {pending_services} tramite(s) en proceso.",
            level="warning",
            source="Servicios Escolares",
        )

    overdue_charges = db.query(models.Charge).filter(models.Charge.status == models.PaymentStatus.VENCIDO).count()
    if overdue_charges:
        _push_notification(
            notifications,
            notif_type="finance",
            title="Cartera vencida",
            message=f"Existen {overdue_charges} cargo(s) vencido(s) por revisar.",
            level="danger",
            source="Tesoreria",
        )

    support_open = db.execute(text("""
        SELECT COUNT(*) AS total
        FROM service_requests
        WHERE COALESCE(is_support_ticket, FALSE) = TRUE
          AND status != :closed_status
    """), {"closed_status": models.ServiceRequestStatus.ENTREGADO.value}).fetchone()
    support_total = int((support_open._mapping.get("total") if support_open else 0) or 0)
    if support_total:
        _push_notification(
            notifications,
            notif_type="support",
            title="Tickets de soporte abiertos",
            message=f"Hay {support_total} ticket(s) de soporte activos.",
            level="warning",
            source="Soporte",
        )

    recent_admin_messages = (
        db.query(models.NotificationMessage)
        .order_by(models.NotificationMessage.created_at.desc(), models.NotificationMessage.id.desc())
        .limit(10)
        .all()
    )
    for item in recent_admin_messages:
        if item.recipient_user:
            target = item.recipient_user.username
        elif item.recipient_group:
            target = f"Grupo {item.recipient_group.name}"
        else:
            target = "Todos los alumnos" if item.recipient_role == models.UserRole.STUDENT else "Todos los docentes"
        _push_notification(
            notifications,
            notif_type="admin_message",
            title=item.title,
            message=f"{item.message} · Destino: {target}",
            level=item.level or "info",
            source="Administracion",
            action_url=item.action_url,
            created_at=item.created_at,
        )

    notifications.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"count": len(notifications), "items": notifications[:20]}


@app.get("/admin/notifications/messages", response_model=list[schemas.NotificationMessageOut], summary="Mensajes de notificacion enviados", tags=["Administracion"])
def list_admin_notification_messages(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    _ensure_notification_schema(db)
    rows = (
        db.query(models.NotificationMessage)
        .order_by(models.NotificationMessage.created_at.desc(), models.NotificationMessage.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": row.id,
            "recipient_role": row.recipient_role,
            "recipient_user_id": row.recipient_user_id,
            "recipient_username": row.recipient_user.username if row.recipient_user else None,
            "recipient_group_id": row.recipient_group_id,
            "recipient_group_name": row.recipient_group.name if row.recipient_group else None,
            "target_scope": row.target_scope or "role",
            "category": row.category or "general",
            "title": row.title,
            "message": row.message,
            "level": row.level,
            "source": row.created_by_user.full_name if row.created_by_user and row.created_by_user.full_name else "Administracion",
            "action_url": row.action_url,
            "is_active": row.is_active,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.post("/admin/notifications/messages", response_model=schemas.NotificationMessageOut, summary="Enviar notificacion a alumnos o docentes", tags=["Administracion"])
def create_admin_notification_message(
    payload: schemas.NotificationMessageCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    _ensure_notification_schema(db)
    recipient_user = None
    recipient_group = None
    if payload.target_scope == "user":
        if not payload.recipient_username:
            raise HTTPException(status_code=400, detail="Debes indicar un usuario destinatario")
        recipient_user = (
            db.query(models.User)
            .filter(
                models.User.username == payload.recipient_username,
                models.User.role == payload.recipient_role,
            )
            .first()
        )
        if not recipient_user:
            raise HTTPException(status_code=404, detail="Usuario destinatario no encontrado para el rol indicado")
    elif payload.target_scope == "group":
        if payload.recipient_role != models.UserRole.STUDENT:
            raise HTTPException(status_code=400, detail="Las notificaciones por grupo solo aplican para alumnos")
        if not payload.recipient_group_id:
            raise HTTPException(status_code=400, detail="Debes indicar el grupo destinatario")
        recipient_group = db.query(models.Group).filter(models.Group.id == payload.recipient_group_id).first()
        if not recipient_group:
            raise HTTPException(status_code=404, detail="Grupo destinatario no encontrado")

    notification = models.NotificationMessage(
        recipient_role=payload.recipient_role,
        recipient_user_id=recipient_user.id if recipient_user else None,
        recipient_group_id=recipient_group.id if recipient_group else None,
        created_by_user_id=current_user.id,
        target_scope=payload.target_scope,
        category=payload.category or "general",
        title=payload.title.strip(),
        message=payload.message.strip(),
        level=(payload.level or "info").strip().lower()[:20] or "info",
        action_url=(payload.action_url or "").strip() or None,
        is_active=True,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return {
        "id": notification.id,
        "recipient_role": notification.recipient_role,
        "recipient_user_id": notification.recipient_user_id,
        "recipient_username": recipient_user.username if recipient_user else None,
        "recipient_group_id": notification.recipient_group_id,
        "recipient_group_name": recipient_group.name if recipient_group else None,
        "target_scope": notification.target_scope or "role",
        "category": notification.category or "general",
        "title": notification.title,
        "message": notification.message,
        "level": notification.level,
        "source": current_user.full_name or current_user.username,
        "action_url": notification.action_url,
        "is_active": notification.is_active,
        "created_at": notification.created_at,
    }


@app.put("/admin/students/{username}/advisor", summary="Asignar asesor academico directo a un alumno", tags=["Administracion"])
def assign_student_advisor(
    username: str,
    payload: schemas.StudentAdvisorAssign,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    advisor = None
    if payload.teacher_id is not None:
        advisor = (
            db.query(models.User)
            .filter(models.User.id == payload.teacher_id, models.User.role == models.UserRole.TEACHER)
            .first()
        )
        if not advisor:
            raise HTTPException(status_code=404, detail="Docente asesor no encontrado")

    student.academic_advisor_id = advisor.id if advisor else None
    db.commit()
    db.refresh(student)

    if advisor:
        _ensure_notification_schema(db)
        db.add(models.NotificationMessage(
            recipient_role=models.UserRole.STUDENT,
            recipient_user_id=student.id,
            created_by_user_id=current_user.id,
            target_scope="user",
            category="advisor",
            title="Asesor académico asignado",
            message=f"Tu asesor académico actual es {advisor.full_name or advisor.username}.",
            level="info",
            is_active=True,
        ))
        db.commit()

    return {
        "ok": True,
        "student_username": student.username,
        "academic_advisor_id": student.academic_advisor_id,
        "advisor_name": advisor.full_name if advisor else None,
    }


@app.get("/admin/moodle/health", summary="Estado de conectividad con Moodle", tags=["Administracion"])
async def read_admin_moodle_health(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    site_info = await moodle_client.get_site_info() if settings.MOODLE_REST_TOKEN else None
    students_total = db.query(models.User).filter(models.User.role == models.UserRole.STUDENT).count()
    teachers_total = db.query(models.User).filter(models.User.role == models.UserRole.TEACHER).count()
    subjects_total = db.query(models.Subject).count()
    linked_students = db.query(models.User).filter(models.User.role == models.UserRole.STUDENT, models.User.moodle_id.isnot(None)).count()
    linked_teachers = db.query(models.User).filter(models.User.role == models.UserRole.TEACHER, models.User.moodle_id.isnot(None)).count()
    linked_subjects = db.query(models.Subject).filter(models.Subject.moodle_course_id.isnot(None)).count()
    enabled = bool(settings.MOODLE_REST_TOKEN and settings.MOODLE_BASE_URL)
    connected = bool(site_info)
    return {
        "enabled": enabled,
        "connected": connected,
        "base_url": settings.MOODLE_BASE_URL if settings.MOODLE_BASE_URL else "",
        "public_url": settings.MOODLE_PUBLIC_URL if settings.MOODLE_PUBLIC_URL else "",
        "auto_login_enabled": bool(settings.MOODLE_AUTO_LOGIN_ENABLED),
        "students_total": students_total,
        "teachers_total": teachers_total,
        "subjects_total": subjects_total,
        "students_linked": linked_students,
        "teachers_linked": linked_teachers,
        "subjects_linked": linked_subjects,
        "site_name": site_info.get("sitename") if isinstance(site_info, dict) else None,
        "site_url": site_info.get("siteurl") if isinstance(site_info, dict) else None,
        "functions_count": len(site_info.get("functions", [])) if isinstance(site_info, dict) else 0,
        "last_error": _latest_moodle_error(),
        "message": "Conexion Moodle activa." if connected else (_latest_moodle_error() or "Moodle configurado localmente, sin respuesta remota."),
    }


@app.get("/admin/moodle/reconciliation", summary="Resumen local para Moodle", tags=["Administracion"])
async def read_admin_moodle_reconciliation(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    students_without_link = db.query(models.User).filter(
        models.User.role == models.UserRole.STUDENT,
        models.User.moodle_id.is_(None),
    ).order_by(models.User.id.asc()).limit(25).all()
    teachers_without_link = db.query(models.User).filter(
        models.User.role == models.UserRole.TEACHER,
        models.User.moodle_id.is_(None),
    ).order_by(models.User.id.asc()).limit(25).all()
    subjects_without_link = db.query(models.Subject).filter(
        models.Subject.moodle_course_id.is_(None),
    ).order_by(models.Subject.id.asc()).limit(25).all()

    linked_subjects = db.query(models.Subject).filter(models.Subject.moodle_course_id.isnot(None)).order_by(models.Subject.id.asc()).limit(25).all()
    remote_checks = []
    for subject in linked_subjects:
        remote_exists = await moodle_client.check_course_exists(int(subject.moodle_course_id)) if subject.moodle_course_id and settings.MOODLE_REST_TOKEN else False
        remote_checks.append(
            {
                "subject_id": subject.id,
                "subject_name": subject.name,
                "moodle_course_id": subject.moodle_course_id,
                "remote_exists": remote_exists if settings.MOODLE_REST_TOKEN else None,
            }
        )

    return {
        "enabled": bool(settings.MOODLE_REST_TOKEN),
        "summary": {
            "students_without_moodle_id": db.query(models.User).filter(models.User.role == models.UserRole.STUDENT, models.User.moodle_id.is_(None)).count(),
            "teachers_without_moodle_id": db.query(models.User).filter(models.User.role == models.UserRole.TEACHER, models.User.moodle_id.is_(None)).count(),
            "subjects_without_moodle_course_id": db.query(models.Subject).filter(models.Subject.moodle_course_id.is_(None)).count(),
        },
        "students": [
            {"id": user.id, "username": user.username, "full_name": user.full_name, "email": user.email}
            for user in students_without_link
        ],
        "teachers": [
            {"id": user.id, "username": user.username, "full_name": user.full_name, "email": user.email}
            for user in teachers_without_link
        ],
        "subjects": [
            {"id": subject.id, "name": subject.name, "career": subject.career, "semester": subject.semester}
            for subject in subjects_without_link
        ],
        "linked_subjects": remote_checks,
        "message": "Tablero de reconciliacion listo.",
    }


@app.post("/admin/students/{username}/moodle-sync", summary="Sincronizar alumno con Moodle", tags=["Administracion"])
async def sync_student_moodle(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    evidence = await _sync_student_to_moodle(db, user=db_user)
    if not evidence.get("success"):
        raise HTTPException(status_code=502, detail={"message": "No fue posible sincronizar el alumno con Moodle", "moodle_error": _latest_moodle_error(), "evidence": evidence})
    return {"message": "Alumno sincronizado exitosamente con Moodle", "moodle_id": db_user.moodle_id, "evidence": evidence}


@app.post("/admin/teachers/{username}/moodle-sync", summary="Sincronizar docente con Moodle", tags=["Administracion"])
async def sync_teacher_moodle(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.TEACHER).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    evidence = await _sync_teacher_to_moodle(db, user=db_user)
    if not evidence.get("success"):
        raise HTTPException(status_code=502, detail={"message": "No fue posible sincronizar el docente con Moodle", "moodle_error": _latest_moodle_error(), "evidence": evidence})
    return {"message": "Docente sincronizado exitosamente con Moodle", "moodle_id": db_user.moodle_id, "evidence": evidence}


@app.post("/admin/subjects/{subject_id}/moodle-sync", summary="Sincronizar materia con Moodle", tags=["Administracion"])
async def sync_subject_moodle(subject_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not db_subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")
    result = await _sync_subject_to_moodle_internal(db, subject=db_subject, category_id=1)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail={"message": result.get("message") or "No fue posible sincronizar la materia con Moodle", "moodle_error": result.get("moodle_error") or _latest_moodle_error(), "evidence": result.get("evidence")})
    return result


@app.get("/admin/moodle/users", summary="Buscar usuarios en Moodle", tags=["Administracion"])
async def admin_moodle_users(q: str = "", limit: int = 25, current_user: models.User = Depends(admin_required)):
    users = await moodle_client.get_users(q, max(1, min(limit, 100)))
    if users is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar usuarios en Moodle", "moodle_error": _latest_moodle_error()})
    return {
        "query": q,
        "count": len(users),
        "users": [
            {
                "id": user.get("id"),
                "username": user.get("username"),
                "fullname": user.get("fullname") or f"{user.get('firstname', '')} {user.get('lastname', '')}".strip(),
                "email": user.get("email"),
            }
            for user in users
        ],
    }


@app.get("/admin/moodle/courses", summary="Buscar cursos en Moodle", tags=["Administracion"])
async def admin_moodle_courses(q: str = "", current_user: models.User = Depends(admin_required)):
    courses = await moodle_client.search_courses(q)
    if courses is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar cursos en Moodle", "moodle_error": _latest_moodle_error()})
    return {"query": q, "count": len(courses), "courses": [_serialize_moodle_course(course) for course in courses]}


@app.get("/admin/moodle/courses/{course_id}/contents", summary="Contenidos de curso Moodle", tags=["Administracion"])
async def admin_moodle_course_contents(course_id: int, current_user: models.User = Depends(admin_required)):
    contents = await moodle_client.get_course_contents(course_id)
    if contents is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar contenidos del curso en Moodle", "moodle_error": _latest_moodle_error()})
    return {"course_id": course_id, "sections": contents}


@app.get("/admin/services/{service_id}/attachment", summary="Descargar adjunto de tramite", tags=["Administracion"])
def download_admin_service_attachment(
    service_id: int,
    current_user: models.User = Depends(services_or_admin),
    db: Session = Depends(get_db),
):
    service = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")
    file_path = _service_attachment_absolute_path(service.attachment_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(path=file_path, filename=service.attachment_filename or file_path.name)


# ----------------------------
# Endpoints de usuario
# ----------------------------

@app.get("/users/me/grades", summary="Mis calificaciones", tags=["Usuario"])
def read_user_grades(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.carrera:
        _assign_curriculum_to_student(db, current_user.id, current_user.carrera)
        db.commit()

    result = []
    seen_grade_ids = set()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == current_user.id)
        .all()
    )
    for course_enrollment in course_enrollments:
        grade = _get_grade_for_course_enrollment(course_enrollment)
        if grade:
            seen_grade_ids.add(grade.id)
        result.append(_serialize_grade_row(grade=grade, course_enrollment=course_enrollment))

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == current_user.id).all()
    for grade in legacy_grades:
        if grade.id in seen_grade_ids:
            continue
        result.append(_serialize_grade_row(grade=grade))

    result.sort(
        key=lambda item: (
            _parse_semester_num(item.get("period")),
            (item.get("description") or "").lower(),
            item.get("grade_id") or 0,
        )
    )
    return _effective_student_grade_rows(result)


@app.get("/users/me/academic-history", response_model=list[schemas.AcademicHistoryItem], summary="Mi historial academico", tags=["Usuario"])
def read_user_academic_history(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    history = _get_academic_history_for_student(db, current_user.id)
    return [
        item for item in history
        if item["course_enrollment_id"] or item["assignment_id"] or item["final_score"] is not None
    ]


@app.put("/users/me", summary="Actualizar perfil", tags=["Usuario"])
def update_user_me(user_update: schemas.UserUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    if user_update.email is not None:
        current_user.email = user_update.email
    if user_update.password:
        current_user.hashed_password = auth.get_password_hash(user_update.password)

    db.commit()
    db.refresh(current_user)
    return current_user


@app.post("/upload-document", summary="Subir documento", tags=["Usuario"])
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "otro",
    current_user: models.User = Depends(auth.get_current_user),
):
    _validate_upload_file(file)
    upload_dir = f"{settings.UPLOAD_DIR}/{current_user.username}"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {"filename": file.filename, "status": "success", "message": f"Documento {document_type} subido correctamente"}


@app.get("/users/me/payments", summary="Mis pagos", tags=["Usuario"])
def read_user_payments(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Payment).filter(models.Payment.student_id == current_user.id).all()


@app.get("/users/me/charges", response_model=list[schemas.Charge], summary="Mis cargos", tags=["Usuario"])
def read_user_charges(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Charge).filter(models.Charge.student_id == current_user.id).order_by(models.Charge.id.desc()).all()


@app.get("/users/me/services", summary="Mis tramites", tags=["Usuario"])
def read_user_services(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.ServiceRequest).filter(models.ServiceRequest.student_id == current_user.id).all()


@app.post("/users/me/academic-services", summary="Solicitar tramite academico enriquecido", tags=["Usuario"])
def create_user_academic_service(payload: dict, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    service_type = (payload.get("type") or "").strip()
    subject = (payload.get("subject") or "").strip()
    description = (payload.get("description") or "").strip()
    if not service_type or not subject or not description:
        raise HTTPException(status_code=400, detail="type, subject y description son requeridos")

    history_json = _append_ticket_history(
        None,
        actor=current_user.username,
        action="create_academic_service",
        message="Tramite academico creado por el alumno",
        status_value=models.ServiceRequestStatus.EN_PROCESO.value,
    )
    request_date = datetime.utcnow()
    result = db.execute(text("""
        INSERT INTO service_requests (
            student_id, type, status, request_date, subject, description,
            source_system, admin_response, history_json, is_support_ticket, updated_at
        )
        VALUES (
            :student_id, :type, :status, :request_date, :subject, :description,
            :source_system, NULL, :history_json, FALSE, :updated_at
        )
        RETURNING id, student_id, type, status, request_date, subject, description,
                  source_system, admin_response, attachment_filename, updated_at, closed_at, history_json
    """), {
        "student_id": current_user.id,
        "type": service_type,
        "status": models.ServiceRequestStatus.EN_PROCESO.value,
        "request_date": request_date,
        "subject": subject,
        "description": description,
        "source_system": "Portal del Alumno",
        "history_json": history_json,
        "updated_at": request_date,
    }).fetchone()
    db.commit()
    return _serialize_ticket_row(result)


@app.post("/users/me/support-tickets", summary="Crear ticket de soporte", tags=["Usuario"])
def create_user_support_ticket(payload: dict, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    category = (payload.get("category") or payload.get("type") or "").strip()
    subject = (payload.get("subject") or "").strip()
    description = (payload.get("description") or "").strip()
    source_system = (payload.get("source_system") or "Plataforma").strip()
    if not category or not subject or not description:
        raise HTTPException(status_code=400, detail="category, subject y description son requeridos")

    request_date = datetime.utcnow()
    history_json = _append_ticket_history(
        None,
        actor=current_user.username,
        action="create_support_ticket",
        message=f"Ticket levantado desde {source_system}",
        status_value=models.ServiceRequestStatus.EN_PROCESO.value,
    )
    result = db.execute(text("""
        INSERT INTO service_requests (
            student_id, type, status, request_date, subject, description,
            source_system, admin_response, history_json, is_support_ticket, updated_at
        )
        VALUES (
            :student_id, :type, :status, :request_date, :subject, :description,
            :source_system, NULL, :history_json, TRUE, :updated_at
        )
        RETURNING id, student_id, type, status, request_date, subject, description,
                  source_system, admin_response, attachment_filename, updated_at, closed_at, history_json
    """), {
        "student_id": current_user.id,
        "type": category,
        "status": models.ServiceRequestStatus.EN_PROCESO.value,
        "request_date": request_date,
        "subject": subject,
        "description": description,
        "source_system": source_system,
        "history_json": history_json,
        "updated_at": request_date,
    }).fetchone()
    db.commit()
    return _serialize_ticket_row(result)


@app.get("/users/me/support-tickets", summary="Mis tickets de soporte", tags=["Usuario"])
def read_user_support_tickets(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    rows = db.execute(text("""
        SELECT
            id, student_id, type, status, request_date, subject, description,
            source_system, admin_response, attachment_filename, updated_at, closed_at, history_json
        FROM service_requests
        WHERE student_id = :student_id
          AND COALESCE(is_support_ticket, FALSE) = TRUE
        ORDER BY request_date DESC, id DESC
    """), {"student_id": current_user.id}).fetchall()
    return [_serialize_ticket_row(row) for row in rows]


@app.get("/users/me/notifications", summary="Notificaciones del alumno", tags=["Usuario"])
def read_user_notifications(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _ensure_portal_extensions(db)
    notifications: list[dict] = _get_custom_notifications_for_user(db, current_user)

    pending_charges = db.query(models.Charge).filter(
        models.Charge.student_id == current_user.id,
        models.Charge.status != models.PaymentStatus.PAGADO,
    ).count()
    if pending_charges:
        _push_notification(
            notifications,
            notif_type="charges",
            title="Pagos pendientes",
            message=f"Tienes {pending_charges} cargo(s) pendiente(s).",
            level="warning",
            source="Tesoreria",
        )

    pending_services = db.query(models.ServiceRequest).filter(
        models.ServiceRequest.student_id == current_user.id,
        models.ServiceRequest.status == models.ServiceRequestStatus.EN_PROCESO,
    ).count()
    if pending_services:
        _push_notification(
            notifications,
            notif_type="services",
            title="Tramites en proceso",
            message=f"Tienes {pending_services} tramite(s) en seguimiento.",
            level="info",
            source="Servicios",
        )

    support_rows = db.execute(text("""
        SELECT id, subject, status, updated_at, request_date
        FROM service_requests
        WHERE student_id = :student_id
          AND COALESCE(is_support_ticket, FALSE) = TRUE
          AND status != :closed_status
        ORDER BY COALESCE(updated_at, request_date) DESC
    """), {
        "student_id": current_user.id,
        "closed_status": models.ServiceRequestStatus.ENTREGADO.value,
    }).fetchall()
    for row in support_rows:
        row_data = row._mapping
        _push_notification(
            notifications,
            notif_type="support",
            title=f"Ticket #{row_data.get('id')} activo",
            message=f"{row_data.get('subject') or 'Soporte tecnico'} · Estatus: {row_data.get('status')}",
            level="warning",
            source="Soporte",
            created_at=row_data.get("updated_at") or row_data.get("request_date") or datetime.utcnow(),
        )

    if settings.MOODLE_BASE_URL:
        _push_notification(
            notifications,
            notif_type="moodle",
            title="Aula virtual disponible",
            message="Tu acceso a Moodle esta listo para abrirse desde el portal.",
            level="success",
            source="Moodle",
            action_url=_build_moodle_url("/my/"),
        )
    else:
        _push_notification(
            notifications,
            notif_type="moodle",
            title="Aula virtual no configurada",
            message="Moodle aun no esta configurado en este entorno.",
            level="secondary",
            source="Moodle",
        )

    advisor = read_user_advisor(current_user=current_user, db=db)
    advisor_data = advisor.get("advisor")
    if advisor_data:
        advisor_name = advisor_data.get("teacher_full_name") or advisor_data.get("teacher_username") or "Tutor"
        _push_notification(
            notifications,
            notif_type="advisor",
            title="Asesoria activa",
            message=f"Tu asesor actual es {advisor_name}.",
            level="info",
            source="Asesoria",
        )

    notifications.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"count": len(notifications), "items": notifications[:20]}


@app.post("/users/me/notifications/{notification_id}/read", summary="Marcar notificacion como leida", tags=["Usuario"])
def mark_user_notification_read(
    notification_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    notification = _get_user_manageable_notification(db, notification_id=notification_id, user=current_user)
    if not notification:
        raise HTTPException(status_code=404, detail="Notificacion no encontrada")
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.commit()
    db.refresh(notification)
    return {"ok": True, "id": notification.id, "is_read": True, "read_at": notification.read_at.isoformat() if notification.read_at else None}


@app.delete("/users/me/notifications/{notification_id}", summary="Ocultar notificacion del alumno", tags=["Usuario"])
def delete_user_notification(
    notification_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    notification = _get_user_manageable_notification(db, notification_id=notification_id, user=current_user)
    if not notification:
        raise HTTPException(status_code=404, detail="Notificacion no encontrada")
    notification.is_active = False
    db.commit()
    return {"ok": True, "id": notification_id}


@app.get("/users/me/advisor", summary="Tutor o asesor actual del alumno", tags=["Usuario"])
def read_user_advisor(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    advisor = _get_effective_student_advisor(db, current_user)
    active_enrollment = _get_active_student_enrollment(db, current_user.id)
    if not advisor:
        return {"advisor": None, "messages": []}

    advisor_messages = (
        db.query(models.NotificationMessage)
        .filter(
            models.NotificationMessage.category == "advisor",
            models.NotificationMessage.recipient_user_id == current_user.id,
            models.NotificationMessage.created_by_user_id == advisor.id,
            models.NotificationMessage.is_active == True,
        )
        .order_by(models.NotificationMessage.created_at.desc(), models.NotificationMessage.id.desc())
        .limit(10)
        .all()
    )
    return {
        "advisor": {
            "teacher_id": advisor.id,
            "teacher_username": advisor.username,
            "teacher_full_name": advisor.full_name,
            "teacher_email": advisor.email,
            "period_label": active_enrollment.cycle.period if active_enrollment.cycle else None,
            "notes": current_user.academic_advisor_id
                and "Seguimiento academico directo asignado por administracion."
                or (f"Seguimiento academico del grupo {active_enrollment.group.name}." if active_enrollment and active_enrollment.group else "Seguimiento academico activo."),
        },
        "messages": [
            {
                "id": message.id,
                "title": message.title,
                "message": message.message,
                "created_at": message.created_at,
            }
            for message in advisor_messages
        ],
    }


@app.get("/users/me/pasaporte", response_model=schemas.PasaporteOut, summary="Pasaporte digital del alumno", tags=["Usuario"])
def read_pasaporte(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    active_enrollment = _get_active_student_enrollment(db, current_user.id)
    career_name = ""
    if active_enrollment and active_enrollment.career:
        career_name = active_enrollment.career.name or ""
    if not career_name:
        career_name = current_user.carrera or ""
    is_university = "preparatoria" not in career_name.lower() and "prepa" not in career_name.lower()

    thesis = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == current_user.id).first()
    ss_records = db.query(models.SocialServiceRecord).filter(models.SocialServiceRecord.student_id == current_user.id).all()

    return schemas.PasaporteOut(
        is_university=is_university,
        thesis=schemas.ThesisOut.model_validate(thesis) if thesis else None,
        social_services=[schemas.SocialServiceOut.model_validate(r) for r in ss_records],
    )


@app.get("/admin/students/{username}/pasaporte", response_model=schemas.PasaporteOut, summary="Pasaporte digital de alumno (admin)", tags=["Administracion"])
def admin_read_student_pasaporte(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(models.User.username == username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    active_enrollment = _get_active_student_enrollment(db, student.id)
    career_name = ""
    if active_enrollment and active_enrollment.career:
        career_name = active_enrollment.career.name or ""
    if not career_name:
        career_name = student.carrera or ""
    is_university = "preparatoria" not in career_name.lower() and "prepa" not in career_name.lower()
    thesis = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student.id).first()
    ss_records = db.query(models.SocialServiceRecord).filter(models.SocialServiceRecord.student_id == student.id).all()
    return schemas.PasaporteOut(
        is_university=is_university,
        thesis=schemas.ThesisOut.model_validate(thesis) if thesis else None,
        social_services=[schemas.SocialServiceOut.model_validate(r) for r in ss_records],
    )


@app.put("/admin/students/{student_id}/pasaporte/thesis", summary="Actualizar tesis de alumno (admin)", tags=["Admin"])
def admin_update_thesis(
    student_id: int,
    data: schemas.ThesisAdminUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.SERVICES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")
    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    record = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student_id).first()
    if not record:
        record = models.ThesisRecord(student_id=student_id)
        db.add(record)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(record, field, value)
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return schemas.ThesisOut.model_validate(record)


@app.put("/admin/students/{student_id}/pasaporte/social-service/{service_type}", summary="Actualizar servicio social de alumno (admin)", tags=["Admin"])
def admin_update_social_service(
    student_id: int,
    service_type: str,
    data: schemas.SocialServiceAdminUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.SERVICES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")
    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    valid_types = [e.value for e in models.SocialServiceType]
    if service_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {valid_types}")
    record = (
        db.query(models.SocialServiceRecord)
        .filter(models.SocialServiceRecord.student_id == student_id, models.SocialServiceRecord.service_type == service_type)
        .first()
    )
    if not record:
        record = models.SocialServiceRecord(student_id=student_id, service_type=service_type)
        db.add(record)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(record, field, value)
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return schemas.SocialServiceOut.model_validate(record)


@app.get("/users/me/moodle-url", summary="Estado y URL base de Moodle", tags=["Usuario"])
async def read_user_moodle_url(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    credentials = _get_moodle_credentials_for_user(db, current_user)
    remote_courses = await moodle_client.get_user_courses(int(current_user.moodle_id)) if current_user.moodle_id and settings.MOODLE_REST_TOKEN else None
    serialized_courses = [_serialize_moodle_course(course) for course in (remote_courses or [])]
    if not serialized_courses:
        local_courses = await read_user_courses(current_user=current_user, db=db)
        serialized_courses = [
            {
                "id": item.get("id"),
                "displayname": item.get("name"),
                "fullname": item.get("name"),
                "teacher": item.get("teacher"),
                "view_url": _build_moodle_public_url("/my/"),
            }
            for item in local_courses[:6]
        ]
    return {
        "enabled": bool(settings.MOODLE_BASE_URL),
        "linked": bool(current_user.moodle_id),
        "moodle_id": current_user.moodle_id,
        "launch_url": _build_moodle_public_url("/my/"),
        "login_url": _build_moodle_public_url("/login/index.php"),
        "courses_url": _build_moodle_public_url("/my/courses.php"),
        "moodle_username": credentials.get("moodle_username"),
        "password_configured": bool(credentials.get("moodle_password")),
        "has_courses": bool(serialized_courses),
        "courses_count": len(serialized_courses),
        "courses": serialized_courses,
    }


@app.get("/users/me/moodle-launch", summary="Preparar apertura de Moodle", tags=["Usuario"])
async def read_user_moodle_launch(target_url: Optional[str] = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    credentials = _get_moodle_credentials_for_user(db, current_user)
    base_target = target_url or _build_moodle_public_url("/my/")
    can_auto_login = bool(
        settings.MOODLE_AUTO_LOGIN_ENABLED
        and current_user.moodle_id
        and credentials.get("moodle_username")
        and credentials.get("moodle_password")
    )
    return {
        "enabled": bool(settings.MOODLE_BASE_URL),
        "can_auto_login": can_auto_login,
        "reason": None if can_auto_login else "auto_login_not_available",
        "url": base_target,
        "target_url": base_target,
        "login_url": _build_moodle_public_url("/login/index.php"),
        "moodle_username": credentials.get("moodle_username"),
        "username": credentials.get("moodle_username"),
        "password": credentials.get("moodle_password") if can_auto_login else None,
        "login_post_url": _build_moodle_public_url("/login/index.php"),
    }


@app.get("/users/me/moodle-courses/{course_id}/contents", summary="Contenido de curso Moodle", tags=["Usuario"])
async def read_user_moodle_course_contents(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.moodle_id and settings.MOODLE_REST_TOKEN:
        user_courses = await moodle_client.get_user_courses(int(current_user.moodle_id))
        allowed_ids = {int(course.get("id")) for course in (user_courses or []) if course.get("id")}
        if int(course_id) not in allowed_ids:
            raise HTTPException(status_code=404, detail="Curso no encontrado para este alumno")
        contents = await moodle_client.get_course_contents(course_id)
        if contents is None:
            raise HTTPException(status_code=502, detail={"message": "No fue posible obtener modulos del curso en Moodle", "moodle_error": _latest_moodle_error()})
        return {"course_id": course_id, "sections": contents}

    courses = await read_user_courses(current_user=current_user, db=db)
    course = next((item for item in courses if int(item.get("id") or 0) == int(course_id)), None)
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    return {"course_id": course_id, "sections": [], "modules": [], "message": "Moodle no esta disponible en este entorno.", "course": course}


@app.get("/users/me/documents", summary="Mis documentos", tags=["Usuario"])
async def list_documents(current_user: models.User = Depends(auth.get_current_user)):
    upload_dir = f"{settings.UPLOAD_DIR}/{current_user.username}"
    if not os.path.exists(upload_dir):
        return []

    files = []
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        if os.path.isfile(file_path):
            stats = os.stat(file_path)
            files.append(
                {
                    "filename": filename,
                    "size": stats.st_size,
                    "date": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    return files


@app.get("/users/me/courses", summary="Mis cursos", tags=["Usuario"])
async def read_user_courses(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.carrera:
        _assign_curriculum_to_student(db, current_user.id, current_user.carrera)
        db.commit()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == current_user.id)
        .all()
    )
    courses = []
    seen_grade_ids = set()

    for ce in course_enrollments:
        grade = _get_grade_for_course_enrollment(ce)
        if grade:
            seen_grade_ids.add(grade.id)
        subject = ce.assignment.subject if ce.assignment and ce.assignment.subject else (grade.subject if grade else None)
        if not _subject_is_virtual_classroom_enabled(subject):
            continue
        payload = _serialize_course_card(ce, grade)
        payload["modality"] = subject.modality if subject else None
        courses.append(payload)

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == current_user.id).all()
    for g in legacy_grades:
        if g.id in seen_grade_ids:
            continue
        if not _subject_is_virtual_classroom_enabled(g.subject):
            continue
        if g.assignment and g.assignment.teacher:
            professor_name = g.assignment.teacher.full_name or g.assignment.teacher.username
        else:
            professor_name = "Docente no asignado"
        courses.append(
            {
                "id": g.subject.id if g.subject else None,
                "name": g.subject.name if g.subject else None,
                "progress": 100 if g.status == models.GradeStatus.APROBADA else (40 if g.status == models.GradeStatus.CURSANDO else 0),
                "score": g.score if g.score is not None else 0,
                "professor": professor_name,
                "semester": g.subject.semester if g.subject else None,
                "credits": g.subject.credits if g.subject else None,
                "status": g.status,
                "moodle_course_id": g.subject.moodle_course_id if g.subject else None,
                "modality": g.subject.modality if g.subject else None,
            }
        )
    courses.sort(
        key=lambda item: (
            _parse_semester_num(item.get("semester")),
            (item.get("name") or "").lower(),
            item.get("id") or 0,
        )
    )
    return courses


# ----------------------------
# Endpoints de docente
# ----------------------------

@app.get("/teacher/subjects", summary="Asignaciones del docente en ciclo activo", tags=["Docente"])
def get_teacher_subjects(current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    """Devuelve las asignaciones (materia + ciclo) del docente en el ciclo activo.
    El campo 'id' de cada resultado es el assignment_id para usar en /teacher/students/{id}.
    """
    active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
    query = db.query(models.SubjectAssignment)
    if current_user.role == models.UserRole.TEACHER:
        query = query.filter(models.SubjectAssignment.teacher_id == current_user.id)
    if active_cycle:
        query = query.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    assignments = query.all()
    result = []
    for a in assignments:
        result.append({
            "id": a.id,                       # assignment_id (usar en /teacher/students/{id})
            "subject_id": a.subject_id,
            "name": a.subject.name if a.subject else None,
            "credits": a.subject.credits if a.subject else None,
            "semester": a.subject.semester if a.subject else None,
            "career": a.subject.career if a.subject else None,
            "cycle_id": a.cycle_id,
            "group_id": a.group_id,
            "group_name": a.group.name if a.group else None,
        })
    return result


@app.get("/teacher/notifications", summary="Notificaciones del docente", tags=["Docente"])
def read_teacher_notifications(current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    notifications: list[dict] = _get_custom_notifications_for_user(db, current_user)

    active_cycle = _get_active_cycle(db)
    assignments_query = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.teacher_id == current_user.id)
    if active_cycle:
        assignments_query = assignments_query.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    assignments = assignments_query.all()

    if assignments:
        _push_notification(
            notifications,
            notif_type="assignments",
            title="Materias asignadas",
            message=f"Tienes {len(assignments)} materia(s) asignada(s) en el ciclo activo.",
            level="info",
            source="Administracion",
        )

    unlocked_grades = (
        db.query(models.Grade)
        .join(models.SubjectAssignment, models.SubjectAssignment.id == models.Grade.assignment_id)
        .filter(
            models.SubjectAssignment.teacher_id == current_user.id,
            models.Grade.teacher_locked == False,
        )
    )
    if active_cycle:
        unlocked_grades = unlocked_grades.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    unlocked_total = unlocked_grades.count()
    if unlocked_total:
        _push_notification(
            notifications,
            notif_type="grades_pending",
            title="Calificaciones pendientes",
            message=f"Aun tienes {unlocked_total} calificacion(es) sin captura final.",
            level="warning",
            source="Control Escolar",
        )

    if settings.MOODLE_BASE_URL:
        _push_notification(
            notifications,
            notif_type="moodle",
            title="Moodle docente disponible",
            message="Puedes entrar a Moodle desde tu panel docente.",
            level="success",
            source="Moodle",
            action_url=_build_moodle_url("/my/courses.php"),
        )

    notifications.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"count": len(notifications), "items": notifications[:20]}


@app.get("/teacher/students/{assignment_id}", summary="Alumnos por asignación", tags=["Docente"])
def get_students_by_assignment(assignment_id: int, current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    """Devuelve todos los alumnos inscritos en una asignación (REGULAR y EXTEMPORANEO)."""
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if current_user.role == models.UserRole.TEACHER and assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes asignada esta materia")

    result = []
    seen_grade_ids = set()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .filter(models.CourseEnrollment.assignment_id == assignment_id)
        .all()
    )
    for course_enrollment in course_enrollments:
        student = course_enrollment.student_enrollment.student if course_enrollment.student_enrollment else None
        if not student:
            continue
        active_enrollment = _get_active_student_enrollment(db, student.id)
        active_group_name = active_enrollment.group.name if active_enrollment and active_enrollment.group else None
        grade = _get_grade_for_course_enrollment(course_enrollment)
        if grade:
            seen_grade_ids.add(grade.id)
        result.append({
            "grade_id": grade.id if grade else None,
            "course_enrollment_id": course_enrollment.id,
            "student_id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "score": grade.score if grade else None,
            "status": grade.status if grade else course_enrollment.status,
            "attempt_type": grade.attempt_type if grade else course_enrollment.attempt_type,
            "teacher_locked": grade.teacher_locked if grade else False,
            "document_filename": grade.document_filename if grade else None,
            "has_document": bool(grade and grade.document_path),
            "group_name": (
                active_group_name
                or (
                    course_enrollment.student_enrollment.group.name
                    if course_enrollment.student_enrollment and course_enrollment.student_enrollment.group
                    else None
                )
                or student.grupo
                or (assignment.group.name if assignment.group else None)
            ),
        })

    grades = db.query(models.Grade).filter(models.Grade.assignment_id == assignment_id).all()
    for grade in grades:
        if grade.id in seen_grade_ids:
            continue
        active_enrollment = _get_active_student_enrollment(db, grade.student.id) if grade.student else None
        active_group_name = active_enrollment.group.name if active_enrollment and active_enrollment.group else None
        result.append({
            "grade_id": grade.id,
            "course_enrollment_id": grade.course_enrollment_id,
            "student_id": grade.student.id,
            "username": grade.student.username,
            "full_name": grade.student.full_name,
            "score": grade.score,
            "status": grade.status,
            "attempt_type": grade.attempt_type,
            "teacher_locked": grade.teacher_locked,
            "document_filename": grade.document_filename,
            "has_document": bool(grade.document_path),
            "group_name": active_group_name or grade.student.grupo or (assignment.group.name if assignment.group else None),
        })

    result.sort(key=lambda item: (((item["group_name"] or "Sin grupo")).lower(), (item["full_name"] or "").lower(), item["username"]))
    return result


@app.post("/teacher/assignments/{assignment_id}/extemporaneo/{student_id}", summary="Crear calificación extemporánea", tags=["Docente"])
def create_extemporaneo_grade(
    assignment_id: int,
    student_id: int,
    grade_data: schemas.ExtemporaneGradeCreate,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    """Agrega un intento de examen extemporáneo para un alumno que reprobó el ordinario.
    El alumno debe tener una calificación REPROBADA en el mismo assignment.
    """
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if current_user.role == models.UserRole.TEACHER and assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permisos sobre esta asignación")

    # Verificar que el alumno tiene una calificación reprobada previa en esta misma asignación.
    failed_grade = db.query(models.Grade).filter(
        models.Grade.assignment_id == assignment_id,
        models.Grade.student_id == student_id,
        models.Grade.attempt_type.in_([models.AttemptType.REGULAR, models.AttemptType.RECURSA]),
        models.Grade.status == models.GradeStatus.REPROBADA,
    ).first()
    if not failed_grade:
        raise HTTPException(status_code=400, detail="El alumno debe tener una calificación reprobada previa para registrar un extemporáneo")

    # Verificar que no existe ya un extemporáneo
    existing = db.query(models.Grade).filter(
        models.Grade.assignment_id == assignment_id,
        models.Grade.student_id == student_id,
        models.Grade.attempt_type == models.AttemptType.EXTEMPORANEO,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe una calificación extemporánea para este alumno en esta asignación")

    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    new_grade = models.Grade(
        student_id=student_id,
        subject_id=assignment.subject_id,
        assignment_id=assignment_id,
        course_enrollment_id=_get_or_create_course_enrollment(
            db,
            student=student,
            assignment=assignment,
            attempt_type=models.AttemptType.EXTEMPORANEO,
            status=grade_data.status,
        ).id,
        attempt_type=models.AttemptType.EXTEMPORANEO,
        score=grade_data.score,
        status=grade_data.status,
    )
    if current_user.role == models.UserRole.TEACHER and (
        grade_data.score is not None or grade_data.status != models.GradeStatus.CURSANDO
    ):
        new_grade.recorded_at = datetime.utcnow()
        new_grade.teacher_locked = True
    db.add(new_grade)
    db.commit()
    db.refresh(new_grade)
    return new_grade


@app.put("/teacher/grades/{grade_id}", summary="Actualizar calificacion", tags=["Docente"])
def update_student_grade(grade_id: int, grade_update: schemas.GradeUpdate, current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")

    # Verificar que el docente tiene permiso sobre esta calificación
    if current_user.role == models.UserRole.TEACHER:
        if db_grade.assignment and db_grade.assignment.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permisos sobre esta calificacion")
        if db_grade.teacher_locked:
            raise HTTPException(
                status_code=403,
                detail="La calificacion ya fue capturada por el docente y solo el administrador puede corregirla",
            )

    if grade_update.score is not None:
        _apply_grade_payload(
            db_grade,
            grade_update,
            lock_for_teacher=current_user.role == models.UserRole.TEACHER,
        )
        # Estatus calculado automáticamente: ≥6 aprobatoria, <6 reprobatoria
    elif grade_update.status is not None:
        _apply_grade_payload(
            db_grade,
            grade_update,
            lock_for_teacher=current_user.role == models.UserRole.TEACHER,
        )

    db.commit()
    db.refresh(db_grade)
    return db_grade


@app.post("/teacher/grades/{grade_id}/document", summary="Subir comprobante fisico de calificacion", tags=["Docente"])
async def upload_grade_document(
    grade_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")
    if current_user.role == models.UserRole.TEACHER:
        if db_grade.assignment and db_grade.assignment.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permiso sobre esta calificacion")
    _validate_upload_file(
        file,
        allowed_types=["image/jpeg", "image/png", "image/webp", "application/pdf"],
        max_size_bytes=10 * 1024 * 1024,
    )
    safe_name = Path(file.filename or "comprobante").name
    relative_dir = Path("grades") / str(grade_id)
    absolute_dir = Path(settings.UPLOAD_DIR) / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}_{safe_name}"
    absolute_path = absolute_dir / stored_name
    with absolute_path.open("wb") as buf:
        buf.write(await file.read())
    db_grade.document_filename = safe_name
    db_grade.document_path = str(relative_dir / stored_name)
    db.commit()
    return {"ok": True, "filename": safe_name}


@app.get("/teacher/grades/{grade_id}/document", summary="Ver comprobante fisico de calificacion", tags=["Docente"])
def download_grade_document(
    grade_id: int,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    from fastapi.responses import FileResponse
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade or not db_grade.document_path:
        raise HTTPException(status_code=404, detail="Sin comprobante adjunto")
    if current_user.role == models.UserRole.TEACHER:
        if db_grade.assignment and db_grade.assignment.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permiso sobre esta calificacion")
    abs_path = (Path(settings.UPLOAD_DIR) / db_grade.document_path).resolve()
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en servidor")
    return FileResponse(str(abs_path), filename=db_grade.document_filename or "comprobante")


# ── Página Web: endpoints públicos ──────────────────────────────────────────

@app.get("/public/projects", response_model=List[schemas.ProjectOut], tags=["Web Pública"])
def public_get_projects(category: Optional[str] = None, db: Session = Depends(get_db)):
    """Devuelve proyectos/eventos activos. Filtrable por category=portfolio|evento."""
    q = db.query(models.Project).filter(models.Project.is_active == True)
    if category:
        q = q.filter(models.Project.category == category)
    return q.order_by(models.Project.created_at.desc()).all()


@app.post("/public/contacts", response_model=schemas.ContactOut, status_code=201, tags=["Web Pública"])
def public_create_contact(data: schemas.ContactCreate, db: Session = Depends(get_db)):
    """Recibe un lead del formulario de contacto de la landing page."""
    contact = models.Contact(**data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


# ── Página Web: endpoints de administración ──────────────────────────────────

@app.get("/admin/projects", response_model=List[schemas.ProjectOut], tags=["Admin Web"])
def admin_get_projects(category: Optional[str] = None, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    q = db.query(models.Project)
    if category:
        q = q.filter(models.Project.category == category)
    return q.order_by(models.Project.created_at.desc()).all()


@app.post("/admin/projects", response_model=schemas.ProjectOut, status_code=201, tags=["Admin Web"])
def admin_create_project(data: schemas.ProjectCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = models.Project(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.put("/admin/projects/{project_id}", response_model=schemas.ProjectOut, tags=["Admin Web"])
def admin_update_project(project_id: int, data: schemas.ProjectUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@app.delete("/admin/projects/{project_id}", status_code=204, tags=["Admin Web"])
def admin_delete_project(project_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    db.delete(project)
    db.commit()


@app.get("/admin/contacts", response_model=List[schemas.ContactOut], tags=["Admin Web"])
def admin_get_contacts(status: Optional[str] = None, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    q = db.query(models.Contact)
    if status:
        q = q.filter(models.Contact.status == status)
    return q.order_by(models.Contact.created_at.desc()).all()


@app.put("/admin/contacts/{contact_id}/status", response_model=schemas.ContactOut, tags=["Admin Web"])
def admin_update_contact_status(contact_id: int, data: schemas.ContactStatusUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    valid = {e.value for e in models.ContactStatus}
    if data.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status inválido. Opciones: {valid}")
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    contact.status = data.status
    db.commit()
    db.refresh(contact)
    return contact


@app.delete("/admin/contacts/{contact_id}", status_code=204, tags=["Admin Web"])
def admin_delete_contact(contact_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    db.delete(contact)
    db.commit()


# ── Historias de Éxito: endpoints públicos ──────────────────────────────────

@app.get("/public/success-stories", response_model=List[schemas.SuccessStoryOut], tags=["Web Pública"])
def public_get_success_stories(db: Session = Depends(get_db)):
    return db.query(models.SuccessStory).filter(models.SuccessStory.is_active == True).order_by(models.SuccessStory.sort_order, models.SuccessStory.id).all()

@app.get("/admin/success-stories", response_model=List[schemas.SuccessStoryOut], tags=["Admin Web"])
def admin_get_success_stories(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.SuccessStory).order_by(models.SuccessStory.sort_order, models.SuccessStory.id).all()

@app.post("/admin/success-stories", response_model=schemas.SuccessStoryOut, status_code=201, tags=["Admin Web"])
def admin_create_success_story(data: schemas.SuccessStoryCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = models.SuccessStory(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item

@app.put("/admin/success-stories/{item_id}", response_model=schemas.SuccessStoryOut, tags=["Admin Web"])
def admin_update_success_story(item_id: int, data: schemas.SuccessStoryUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.SuccessStory).filter(models.SuccessStory.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item

@app.delete("/admin/success-stories/{item_id}", status_code=204, tags=["Admin Web"])
def admin_delete_success_story(item_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.SuccessStory).filter(models.SuccessStory.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(item); db.commit()


# ── Reels Testimoniales: endpoints públicos ──────────────────────────────────

@app.get("/public/testimonial-reels", response_model=List[schemas.TestimonialReelOut], tags=["Web Pública"])
def public_get_testimonial_reels(db: Session = Depends(get_db)):
    return db.query(models.TestimonialReel).filter(models.TestimonialReel.is_active == True).order_by(models.TestimonialReel.sort_order, models.TestimonialReel.id).all()

@app.get("/admin/testimonial-reels", response_model=List[schemas.TestimonialReelOut], tags=["Admin Web"])
def admin_get_testimonial_reels(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.TestimonialReel).order_by(models.TestimonialReel.sort_order, models.TestimonialReel.id).all()

@app.post("/admin/testimonial-reels", response_model=schemas.TestimonialReelOut, status_code=201, tags=["Admin Web"])
def admin_create_testimonial_reel(data: schemas.TestimonialReelCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = models.TestimonialReel(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item

@app.put("/admin/testimonial-reels/{item_id}", response_model=schemas.TestimonialReelOut, tags=["Admin Web"])
def admin_update_testimonial_reel(item_id: int, data: schemas.TestimonialReelUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.TestimonialReel).filter(models.TestimonialReel.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item

@app.delete("/admin/testimonial-reels/{item_id}", status_code=204, tags=["Admin Web"])
def admin_delete_testimonial_reel(item_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.TestimonialReel).filter(models.TestimonialReel.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(item); db.commit()


# ── Cursos Extracurriculares: endpoints públicos ────────────────────────────

@app.get("/public/extracurricular-courses", response_model=List[schemas.ExtracurricularCourseOut], tags=["Web Pública"])
def public_get_extracurricular_courses(db: Session = Depends(get_db)):
    """Devuelve cursos extracurriculares activos ordenados por sort_order."""
    return (
        db.query(models.ExtracurricularCourse)
        .filter(models.ExtracurricularCourse.is_active == True)
        .order_by(models.ExtracurricularCourse.sort_order, models.ExtracurricularCourse.id)
        .all()
    )


# ── Cursos Extracurriculares: endpoints de administración ───────────────────

@app.get("/admin/extracurricular-courses", response_model=List[schemas.ExtracurricularCourseOut], tags=["Admin Web"])
def admin_get_extracurricular_courses(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.ExtracurricularCourse).order_by(models.ExtracurricularCourse.sort_order, models.ExtracurricularCourse.id).all()


@app.post("/admin/extracurricular-courses", response_model=schemas.ExtracurricularCourseOut, status_code=201, tags=["Admin Web"])
def admin_create_extracurricular_course(data: schemas.ExtracurricularCourseCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    course = models.ExtracurricularCourse(**data.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@app.put("/admin/extracurricular-courses/{course_id}", response_model=schemas.ExtracurricularCourseOut, tags=["Admin Web"])
def admin_update_extracurricular_course(course_id: int, data: schemas.ExtracurricularCourseUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    course = db.query(models.ExtracurricularCourse).filter(models.ExtracurricularCourse.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


@app.delete("/admin/extracurricular-courses/{course_id}", status_code=204, tags=["Admin Web"])
def admin_delete_extracurricular_course(course_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    course = db.query(models.ExtracurricularCourse).filter(models.ExtracurricularCourse.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    db.delete(course)
    db.commit()


# ── Comunidades: endpoints públicos ─────────────────────────────────────────

@app.get("/public/communities", response_model=List[schemas.CommunityOut], tags=["Web Pública"])
def public_get_communities(db: Session = Depends(get_db)):
    """Devuelve comunidades activas ordenadas por sort_order."""
    return (
        db.query(models.Community)
        .filter(models.Community.is_active == True)
        .order_by(models.Community.sort_order, models.Community.id)
        .all()
    )


# ── Comunidades: endpoints de administración ─────────────────────────────────

@app.get("/admin/communities", response_model=List[schemas.CommunityOut], tags=["Admin Web"])
def admin_get_communities(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Community).order_by(models.Community.sort_order, models.Community.id).all()


@app.post("/admin/communities", response_model=schemas.CommunityOut, status_code=201, tags=["Admin Web"])
def admin_create_community(data: schemas.CommunityCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = models.Community(**data.model_dump())
    db.add(community)
    db.commit()
    db.refresh(community)
    return community


@app.put("/admin/communities/{community_id}", response_model=schemas.CommunityOut, tags=["Admin Web"])
def admin_update_community(community_id: int, data: schemas.CommunityUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = db.query(models.Community).filter(models.Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(community, field, value)
    db.commit()
    db.refresh(community)
    return community


@app.delete("/admin/communities/{community_id}", status_code=204, tags=["Admin Web"])
def admin_delete_community(community_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = db.query(models.Community).filter(models.Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    db.delete(community)
    db.commit()


@app.get("/teacher/advisor/students", summary="Alumnos asignados en asesoria", tags=["Docente"])
def read_teacher_advisor_students(current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    active_cycle = _get_active_cycle(db)
    rows = []
    seen_student_ids = set()

    direct_students = (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.STUDENT,
            models.User.academic_advisor_id == current_user.id,
        )
        .order_by(models.User.full_name.asc(), models.User.username.asc())
        .all()
    )
    def _grade_stats(student_id):
        grades = db.query(models.Grade).filter(models.Grade.student_id == student_id).all()
        approved = sum(1 for g in grades if g.status == models.GradeStatus.APROBADA)
        risk = sum(1 for g in grades if g.status == models.GradeStatus.REPROBADA)
        in_progress = sum(1 for g in grades if g.status == models.GradeStatus.CURSANDO)
        scores = [g.score for g in grades if g.score is not None]
        avg = round(sum(scores) / len(scores), 1) if scores else None
        return {"approved": approved, "risk": risk, "in_progress": in_progress, "avg": avg, "total": len(grades)}

    for student in direct_students:
        enrollment = _get_active_student_enrollment(db, student.id)
        rows.append({
            "student_id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "carrera": enrollment.career.name if enrollment and enrollment.career else student.carrera,
            "period_label": enrollment.cycle.period if enrollment and enrollment.cycle else "Asignacion directa",
            "group_name": enrollment.group.name if enrollment and enrollment.group else student.grupo,
            "source": "direct",
            **_grade_stats(student.id),
        })
        seen_student_ids.add(student.id)

    group_enrollments_query = (
        db.query(models.StudentEnrollment)
        .join(models.Group, models.Group.id == models.StudentEnrollment.group_id)
        .filter(
            models.StudentEnrollment.is_active == True,
            models.Group.tutor_id == current_user.id,
        )
    )
    if active_cycle:
        group_enrollments_query = group_enrollments_query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)
    for enrollment in group_enrollments_query.all():
        student = enrollment.student
        if not student or student.id in seen_student_ids:
            continue
        rows.append({
            "student_id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "carrera": enrollment.career.name if enrollment.career else student.carrera,
            "period_label": enrollment.cycle.period if enrollment.cycle else "Ciclo activo",
            "group_name": enrollment.group.name if enrollment.group else student.grupo,
            "source": "group",
            **_grade_stats(student.id),
        })
        seen_student_ids.add(student.id)

    def _thesis_data(student_id: int) -> dict:
        thesis = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student_id).first()
        if not thesis:
            return {"status": "Sin Iniciar", "title": None, "director": None}
        return {
            "status": thesis.status if isinstance(thesis.status, str) else thesis.status.value,
            "title": thesis.title,
            "director": thesis.director,
        }

    for row in rows:
        row["pasaporte"] = {"thesis": _thesis_data(row["student_id"])}

    rows.sort(key=lambda item: ((item.get("full_name") or "").lower(), item.get("username") or ""))
    return {"students": rows}


@app.put("/teacher/advisor/students/{username}/thesis-status", summary="Actualizar estado de tesis (director)", tags=["Docente"])
def teacher_update_thesis_status(
    username: str,
    payload: dict,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if not _teacher_can_advise_student(db, current_user.id, student):
        raise HTTPException(status_code=403, detail="No tienes permiso para actualizar este alumno")
    new_status = (payload.get("status") or "").strip()
    valid = [e.value for e in models.ThesisStatus]
    if new_status not in valid:
        raise HTTPException(status_code=400, detail=f"Estatus inválido. Use: {valid}")
    record = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student.id).first()
    if not record:
        record = models.ThesisRecord(student_id=student.id)
        db.add(record)
    record.status = new_status
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return {"ok": True, "status": record.status if isinstance(record.status, str) else record.status.value}


@app.post("/teacher/advisor/messages", summary="Enviar mensaje de asesoria a un alumno", tags=["Docente"])
def create_teacher_advisor_message(
    payload: dict,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    student_username = (payload.get("student_username") or "").strip()
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or "").strip()
    if not student_username or not title or not message:
        raise HTTPException(status_code=400, detail="Alumno, titulo y mensaje son obligatorios")

    student = (
        db.query(models.User)
        .filter(models.User.username == student_username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if not _teacher_can_advise_student(db, current_user.id, student):
        raise HTTPException(status_code=403, detail="No tienes asignada la asesoria de este alumno")

    _ensure_notification_schema(db)
    notification = models.NotificationMessage(
        recipient_role=models.UserRole.STUDENT,
        recipient_user_id=student.id,
        created_by_user_id=current_user.id,
        target_scope="user",
        category="advisor",
        title=title[:180],
        message=message[:2000],
        level="info",
        is_active=True,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return {"ok": True, "id": notification.id}


@app.post("/teacher/advisor/sessions", summary="Agendar sesion de asesoria", tags=["Docente"])
def create_advisor_session(
    payload: schemas.AdvisorySessionCreate,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == payload.student_username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if not _teacher_can_advise_student(db, current_user.id, student):
        raise HTTPException(status_code=403, detail="No tienes asignada la asesoria de este alumno")
    session = models.AdvisorySession(
        teacher_id=current_user.id,
        student_id=student.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        topic=payload.topic,
        notes=payload.notes,
    )
    db.add(session)
    _ensure_notification_schema(db)
    notif = models.NotificationMessage(
        recipient_role=models.UserRole.STUDENT,
        recipient_user_id=student.id,
        created_by_user_id=current_user.id,
        target_scope="user",
        category="advisor",
        title=f"Asesoría programada: {payload.topic[:80]}",
        message=(
            f"Tu asesor ha agendado una sesión para el "
            f"{payload.scheduled_at.strftime('%d/%m/%Y a las %H:%M')} "
            f"({payload.duration_minutes} min). Tema: {payload.topic}"
        ),
        level="info",
        is_active=True,
    )
    db.add(notif)
    db.commit()
    db.refresh(session)
    return {"ok": True, "id": session.id}


@app.get("/teacher/advisor/sessions", summary="Sesiones de asesoria del docente", tags=["Docente"])
def get_teacher_advisor_sessions(
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(models.AdvisorySession)
        .filter(models.AdvisorySession.teacher_id == current_user.id)
        .order_by(models.AdvisorySession.scheduled_at.asc())
        .all()
    )
    result = []
    for s in sessions:
        student = db.query(models.User).filter(models.User.id == s.student_id).first()
        result.append({
            "id": s.id,
            "student_id": s.student_id,
            "student_username": student.username if student else "-",
            "student_name": student.full_name if student else "-",
            "scheduled_at": s.scheduled_at.isoformat(),
            "duration_minutes": s.duration_minutes,
            "topic": s.topic,
            "notes": s.notes,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "created_at": s.created_at.isoformat(),
        })
    return {"sessions": result}


@app.get("/users/me/advisor/sessions", summary="Sesiones de asesoria del alumno", tags=["Usuario"])
def get_student_advisor_sessions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Solo alumnos")
    sessions = (
        db.query(models.AdvisorySession)
        .filter(models.AdvisorySession.student_id == current_user.id)
        .order_by(models.AdvisorySession.scheduled_at.asc())
        .all()
    )
    result = []
    for s in sessions:
        teacher = db.query(models.User).filter(models.User.id == s.teacher_id).first()
        result.append({
            "id": s.id,
            "teacher_name": teacher.full_name if teacher else "-",
            "scheduled_at": s.scheduled_at.isoformat(),
            "duration_minutes": s.duration_minutes,
            "topic": s.topic,
            "notes": s.notes,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
        })
    return {"sessions": result}


@app.patch("/teacher/advisor/sessions/{session_id}", summary="Actualizar estado de sesion de asesoria", tags=["Docente"])
def update_advisor_session(
    session_id: int,
    payload: schemas.AdvisorySessionStatusUpdate,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    session = (
        db.query(models.AdvisorySession)
        .filter(
            models.AdvisorySession.id == session_id,
            models.AdvisorySession.teacher_id == current_user.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    try:
        session.status = models.AdvisorySessionStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {payload.status}")
    if payload.notes is not None:
        session.notes = payload.notes.strip() or None
    db.commit()
    return {"ok": True}


@app.get("/")
def read_root():
    return {"message": "Bienvenido a la API de la Plataforma Escolar Unives"}
