from typing import List, Optional, Any, Dict
import os
import app.main
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response, Request, Security
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, import_csv, curriculum_credits
from app.config import settings
from app.database import get_db
from app.dependencies import admin_required, teacher_or_admin, services_or_admin, oauth2_scheme
from app.moodle_client import moodle_client
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import csv
from io import StringIO
import io
import hashlib
import hmac
import time
from urllib.parse import quote

router = APIRouter()

MOODLE_REQUIRED_FUNCTIONS = {
    "core_webservice_get_site_info": "Verifica el sitio y las funciones habilitadas para el token.",
    "core_user_create_users": "Crea cuentas de alumnos y docentes.",
    "core_user_update_users": "Actualiza datos y contraseñas de las cuentas.",
    "core_user_get_users": "Busca usuarios mediante criterios.",
    "core_user_get_users_by_field": "Localiza usuarios por ID, username o correo.",
    "core_course_create_courses": "Crea cursos desde las materias locales.",
    "core_course_update_courses": "Actualiza cursos existentes.",
    "core_course_delete_courses": "Elimina cursos existentes.",
    "core_course_get_courses_by_field": "Localiza cursos existentes.",
    "core_course_search_courses": "Busca y lista cursos de Moodle.",
    "core_course_get_contents": "Consulta secciones y recursos del curso.",
    "core_enrol_get_users_courses": "Consulta los cursos de un usuario.",
    "core_enrol_get_enrolled_users": "Consulta participantes de un curso.",
    "core_role_assign_roles": "Asigna roles de alumno y docente.",
    "enrol_manual_enrol_users": "Inscribe usuarios en cursos.",
    "core_group_get_course_groups": "Consulta los grupos de un curso.",
    "core_group_create_groups": "Crea grupos dentro de un curso.",
    "core_group_update_groups": "Actualiza grupos existentes.",
    "core_group_delete_groups": "Elimina grupos existentes.",
    "core_group_add_group_members": "Agrega usuarios enrolados a un grupo.",
}


def _moodle_function_rows(site_info: Optional[dict]) -> list[dict]:
    enabled_names = {
        item.get("name")
        for item in (site_info or {}).get("functions", [])
        if isinstance(item, dict) and item.get("name")
    }
    return [
        {
            "name": name,
            "description": description,
            "enabled": name in enabled_names,
        }
        for name, description in MOODLE_REQUIRED_FUNCTIONS.items()
    ]


@router.get("/admin/moodle/health", summary="Estado de conectividad con Moodle", tags=["Administracion"])
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
        "last_error": app.main._latest_moodle_error(),
        "message": "Conexion Moodle activa." if connected else (app.main._latest_moodle_error() or "Moodle configurado localmente, sin respuesta remota."),
    }


@router.get("/admin/moodle/launch", summary="Iniciar sesion como administrador de Moodle", tags=["Administracion"])
async def launch_moodle_admin(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    site_info = await moodle_client.get_site_info()
    moodle_admin_id = int((site_info or {}).get("userid") or 0)
    moodle_username = str((site_info or {}).get("username") or "").strip().lower()
    if not moodle_admin_id or moodle_username != "admin":
        raise HTTPException(
            status_code=502,
            detail={
                "message": "El token REST no pertenece al administrador de Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    if not settings.MOODLE_AUTO_LOGIN_ENABLED or not settings.MOODLE_SSO_SECRET:
        raise HTTPException(status_code=503, detail="El inicio de sesion automatico de Moodle no esta habilitado")

    linked_user = db.query(models.User).filter(
        models.User.moodle_id == moodle_admin_id,
        models.User.id != current_user.id,
    ).first()
    if linked_user:
        raise HTTPException(status_code=409, detail="La cuenta administradora de Moodle ya esta vinculada a otro usuario local")

    if current_user.moodle_id != moodle_admin_id:
        current_user.moodle_id = moodle_admin_id
        db.add(current_user)
        db.commit()

    target_path = "/admin/"
    expires = int(time.time()) + 60
    payload = f"{moodle_admin_id}|{expires}|{target_path}"
    signature = hmac.new(
        settings.MOODLE_SSO_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    sso_url = app.main._build_moodle_public_url(
        f"/local/univessso/login.php?userid={moodle_admin_id}"
        f"&expires={expires}&target={quote(target_path, safe='')}&signature={signature}"
    )
    return {
        "can_auto_login": True,
        "moodle_id": moodle_admin_id,
        "moodle_username": moodle_username,
        "target": target_path,
        "sso_url": sso_url,
    }


@router.get("/admin/moodle/configuration", summary="Diagnostico seguro de configuracion Moodle", tags=["Administracion"])
async def read_admin_moodle_configuration(current_user: models.User = Depends(admin_required)):
    token_configured = bool(settings.MOODLE_REST_TOKEN)
    site_info = await moodle_client.get_site_info() if token_configured else None
    functions = _moodle_function_rows(site_info)
    enabled_count = sum(1 for item in functions if item["enabled"])
    return {
        "token_configured": token_configured,
        "token_display": "Configurado (oculto)" if token_configured else "No configurado",
        "connected": bool(site_info),
        "base_url": settings.MOODLE_BASE_URL or "",
        "public_url": settings.MOODLE_PUBLIC_URL or "",
        "auto_login_enabled": bool(settings.MOODLE_AUTO_LOGIN_ENABLED),
        "role_context_level": settings.MOODLE_ROLE_CONTEXT_LEVEL,
        "role_instance_id": settings.MOODLE_ROLE_INSTANCE_ID,
        "student_role_id": settings.MOODLE_STUDENT_ROLE_ID,
        "teacher_role_id": settings.MOODLE_TEACHER_ROLE_ID,
        "site_name": site_info.get("sitename") if isinstance(site_info, dict) else None,
        "moodle_release": site_info.get("release") if isinstance(site_info, dict) else None,
        "token_username": site_info.get("username") if isinstance(site_info, dict) else None,
        "required_functions": functions,
        "required_count": len(functions),
        "enabled_required_count": enabled_count,
        "missing_functions": [item["name"] for item in functions if not item["enabled"]],
        "last_error": app.main._latest_moodle_error(),
    }


@router.get("/admin/moodle/functions", summary="Funciones Moodle requeridas y habilitadas", tags=["Administracion"])
async def read_admin_moodle_functions(current_user: models.User = Depends(admin_required)):
    site_info = await moodle_client.get_site_info() if settings.MOODLE_REST_TOKEN else None
    functions = _moodle_function_rows(site_info)
    return {
        "count": sum(1 for item in functions if item["enabled"]),
        "required_count": len(functions),
        "functions": functions,
        "connected": bool(site_info),
        "last_error": app.main._latest_moodle_error(),
    }


@router.get("/admin/moodle/reconciliation", summary="Resumen local para Moodle", tags=["Administracion"])
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


@router.get("/admin/moodle/users", summary="Buscar usuarios en Moodle", tags=["Administracion"])
async def admin_moodle_users(q: str = "", limit: int = 25, current_user: models.User = Depends(admin_required)):
    users = await moodle_client.get_users(q, max(1, min(limit, 100)))
    if users is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar usuarios en Moodle", "moodle_error": app.main._latest_moodle_error()})
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


@router.get("/admin/moodle/user-credentials", summary="Listar usuarios locales configurables en Moodle", tags=["Administracion"])
def list_admin_moodle_user_credentials(
    limit: int = 300,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    users = (
        db.query(models.User)
        .filter(models.User.role.in_([models.UserRole.STUDENT, models.UserRole.TEACHER]))
        .order_by(models.User.role.asc(), models.User.full_name.asc(), models.User.username.asc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    items = []
    for user in users:
        credentials = app.main._get_moodle_credentials_for_user(db, user)
        items.append({
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "moodle_id": user.moodle_id,
            "moodle_username": credentials.get("moodle_username"),
            "moodle_password": credentials.get("moodle_password"),
            "password_configured": credentials.get("password_configured", False),
        })
    return {"count": len(items), "items": items}


@router.put("/admin/moodle/user-credentials/{username}", summary="Crear o actualizar cuenta Moodle de un usuario local", tags=["Administracion"])
async def update_admin_moodle_user_credentials(
    username: str,
    payload: Dict[str, Any],
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(
        models.User.username == username,
        models.User.role.in_([models.UserRole.STUDENT, models.UserRole.TEACHER]),
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Alumno o docente local no encontrado")

    moodle_username = str(payload.get("moodle_username") or "").strip().lower()
    requested_password = str(payload.get("moodle_password") or "").strip()
    moodle_password = requested_password or app.main._build_temp_moodle_password(user.username)
    sync_if_missing = bool(payload.get("sync_if_missing", True))
    create_if_missing = bool(payload.get("create_if_missing", True))
    if not moodle_username:
        raise HTTPException(status_code=400, detail="Usuario y contraseña Moodle son obligatorios")

    moodle_id = user.moodle_id
    if moodle_id and not await moodle_client.check_user_exists(int(moodle_id)):
        user.moodle_id = None
        db.commit()
        moodle_id = None

    if not moodle_id:
        moodle_id = await moodle_client.get_user_by_username(moodle_username)
        if not moodle_id and user.email:
            moodle_id = await moodle_client.get_user_by_email(user.email)

    if not moodle_id and sync_if_missing and create_if_missing:
        sync = app.main._sync_student_to_moodle if user.role == models.UserRole.STUDENT else app.main._sync_teacher_to_moodle
        evidence = await sync(db, user=user, password=moodle_password)
        if not evidence.get("success"):
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "No fue posible crear el usuario en Moodle",
                    "moodle_error": app.main._latest_moodle_error(),
                    "evidence": evidence,
                },
            )
        moodle_id = user.moodle_id

    if not moodle_id:
        raise HTTPException(
            status_code=404,
            detail="No existe una cuenta Moodle para vincular y la creación automática está desactivada",
        )

    first_name, last_name = app.main._split_full_name(user.full_name)
    updated = await moodle_client.update_user_account(
        user_id=int(moodle_id),
        username=moodle_username,
        password=moodle_password,
        firstname=first_name,
        lastname=last_name,
        email=user.email or f"{user.username}@portal.local",
    )
    if not updated:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible actualizar la cuenta en Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )

    role_id = settings.MOODLE_STUDENT_ROLE_ID if user.role == models.UserRole.STUDENT else settings.MOODLE_TEACHER_ROLE_ID
    # Student and teacher roles belong to a course context and are applied on enrolment.
    role_assigned = True
    if not role_assigned:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "La cuenta se actualizó, pero no fue posible asignar su rol Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )

    user.moodle_id = int(moodle_id)
    db.add(user)
    db.commit()
    app.main._upsert_moodle_credentials(
        db,
        user_id=user.id,
        moodle_username=moodle_username,
        moodle_password=moodle_password,
        updated_by=current_user.username,
        overwrite_password=True,
    )
    return {
        "message": "Cuenta Moodle creada o actualizada correctamente",
        "username": user.username,
        "role": user.role.value,
        "moodle_id": user.moodle_id,
        "moodle_username": moodle_username,
        "moodle_password": moodle_password,
        "password_generated": not bool(requested_password),
    }


@router.get("/admin/moodle/courses", summary="Buscar cursos en Moodle", tags=["Administracion"])
async def admin_moodle_courses(q: str = "", current_user: models.User = Depends(admin_required)):
    courses = await moodle_client.search_courses(q)
    if courses is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar cursos en Moodle", "moodle_error": app.main._latest_moodle_error()})
    return {"query": q, "count": len(courses), "courses": [app.main._serialize_moodle_course(course) for course in courses]}


@router.post("/admin/moodle/courses", status_code=201, summary="Crear curso en Moodle", tags=["Administracion"])
async def create_admin_moodle_course(payload: Dict[str, Any], current_user: models.User = Depends(admin_required)):
    fullname = str(payload.get("fullname") or "").strip()
    shortname = str(payload.get("shortname") or "").strip()
    requested_category_id = int(payload.get("categoryid") or 1)
    if not fullname or not shortname:
        raise HTTPException(status_code=400, detail="Nombre completo y shortname son obligatorios")

    categories = await moodle_client.get_course_categories()
    valid_category_ids = {
        int(category.get("id"))
        for category in (categories or [])
        if category.get("id") is not None
    }
    category_id = (
        requested_category_id
        if requested_category_id in valid_category_ids
        else (min(valid_category_ids) if valid_category_ids else 1)
    )

    created = await moodle_client.create_course_admin(
        fullname=fullname,
        shortname=shortname,
        category_id=category_id,
        summary=payload.get("summary"),
        format_name=payload.get("format"),
        visible=payload.get("visible"),
    )
    if not created:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible crear el curso en Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {
        "message": "Curso creado correctamente en Moodle",
        "course": app.main._serialize_moodle_course(created),
        "category_id": category_id,
        "category_adjusted": category_id != requested_category_id,
    }


@router.get("/admin/moodle/categories", summary="Listar categorias de cursos Moodle", tags=["Administracion"])
async def admin_moodle_categories(current_user: models.User = Depends(admin_required)):
    categories = await moodle_client.get_course_categories()
    if categories is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar las categorias de Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {
        "count": len(categories),
        "categories": [
            {
                "id": category.get("id"),
                "name": category.get("name"),
                "parent": category.get("parent"),
                "visible": category.get("visible"),
            }
            for category in categories
        ],
    }


@router.put("/admin/moodle/courses/{course_id}", summary="Actualizar curso en Moodle", tags=["Administracion"])
async def update_admin_moodle_course(course_id: int, payload: Dict[str, Any], current_user: models.User = Depends(admin_required)):
    updated = await moodle_client.update_course_admin(
        course_id=course_id,
        fullname=payload.get("fullname"),
        shortname=payload.get("shortname"),
        category_id=payload.get("categoryid"),
        summary=payload.get("summary"),
    )
    if not updated:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible actualizar el curso en Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"message": "Curso actualizado correctamente en Moodle", "course_id": course_id}


@router.delete("/admin/moodle/courses/{course_id}", summary="Eliminar curso de Moodle", tags=["Administracion"])
async def delete_admin_moodle_course(course_id: int, current_user: models.User = Depends(admin_required)):
    deleted = await moodle_client.delete_course_admin(course_id)
    if not deleted:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible eliminar el curso de Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"message": "Curso eliminado correctamente de Moodle", "course_id": course_id}


@router.get("/admin/moodle/courses/{course_id}/contents", summary="Contenidos de curso Moodle", tags=["Administracion"])
async def admin_moodle_course_contents(course_id: int, current_user: models.User = Depends(admin_required)):
    contents = await moodle_client.get_course_contents(course_id)
    if contents is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar contenidos del curso en Moodle", "moodle_error": app.main._latest_moodle_error()})
    return {"course_id": course_id, "sections": contents}


@router.get("/admin/moodle/courses/{course_id}/groups", summary="Listar grupos de un curso Moodle", tags=["Administracion"])
async def admin_moodle_course_groups(course_id: int, current_user: models.User = Depends(admin_required)):
    groups = await moodle_client.get_course_groups(course_id)
    if groups is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar los grupos del curso",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"course_id": course_id, "count": len(groups), "groups": groups}


@router.post("/admin/moodle/groups", status_code=201, summary="Crear grupo Moodle", tags=["Administracion"])
async def create_admin_moodle_group(
    payload: Dict[str, Any],
    current_user: models.User = Depends(admin_required),
):
    course_id = int(payload.get("courseid") or 0)
    name = str(payload.get("name") or "").strip()
    if not course_id or not name:
        raise HTTPException(status_code=400, detail="Curso y nombre del grupo son obligatorios")
    if not await moodle_client.check_course_exists(course_id):
        raise HTTPException(status_code=404, detail="Curso Moodle no encontrado")

    created = await moodle_client.create_group(
        course_id=course_id,
        name=name,
        description=str(payload.get("description") or "").strip(),
        idnumber=str(payload.get("idnumber") or "").strip() or None,
        enrolment_key=str(payload.get("enrolmentkey") or "").strip() or None,
    )
    if not created:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible crear el grupo en Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"message": "Grupo creado correctamente en Moodle", "group": created}


@router.put("/admin/moodle/groups/{group_id}", summary="Actualizar grupo Moodle", tags=["Administracion"])
async def update_admin_moodle_group(
    group_id: int,
    payload: Dict[str, Any],
    current_user: models.User = Depends(admin_required),
):
    updated = await moodle_client.update_group(
        group_id=group_id,
        name=str(payload["name"]).strip() if "name" in payload else None,
        description=str(payload["description"]).strip() if "description" in payload else None,
        idnumber=str(payload["idnumber"]).strip() if "idnumber" in payload else None,
    )
    if not updated:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible actualizar el grupo Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"message": "Grupo actualizado correctamente", "group_id": group_id}


@router.delete("/admin/moodle/groups/{group_id}", summary="Eliminar grupo Moodle", tags=["Administracion"])
async def delete_admin_moodle_group(group_id: int, current_user: models.User = Depends(admin_required)):
    deleted = await moodle_client.delete_group(group_id)
    if not deleted:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible eliminar el grupo Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"message": "Grupo eliminado correctamente", "group_id": group_id}


@router.post("/admin/moodle/groups/{group_id}/members", summary="Agregar integrantes a grupo Moodle", tags=["Administracion"])
async def add_admin_moodle_group_members(
    group_id: int,
    payload: Dict[str, Any],
    current_user: models.User = Depends(admin_required),
):
    user_ids = [
        int(user_id)
        for user_id in (payload.get("user_ids") or [])
        if str(user_id).strip().isdigit() and int(user_id) > 0
    ]
    if not user_ids:
        raise HTTPException(status_code=400, detail="Selecciona al menos un integrante")
    added = await moodle_client.add_group_members(group_id, user_ids)
    if not added:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible agregar integrantes al grupo Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"message": "Integrantes agregados correctamente", "group_id": group_id, "count": len(set(user_ids))}


async def _ensure_student_moodle_link(db: Session, student: models.User) -> int:
    if student.moodle_id and await moodle_client.check_user_exists(int(student.moodle_id)):
        return int(student.moodle_id)
    evidence = await app.main._sync_student_to_moodle(db, user=student)
    if not evidence.get("success") or not student.moodle_id:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"No fue posible sincronizar a {student.username} con Moodle",
                "moodle_error": app.main._latest_moodle_error(),
                "evidence": evidence,
            },
        )
    return int(student.moodle_id)


async def _ensure_teacher_moodle_link(db: Session, teacher: models.User) -> int:
    if teacher.moodle_id and await moodle_client.check_user_exists(int(teacher.moodle_id)):
        return int(teacher.moodle_id)
    evidence = await app.main._sync_teacher_to_moodle(db, user=teacher)
    if not evidence.get("success") or not teacher.moodle_id:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"No fue posible sincronizar a {teacher.username} con Moodle",
                "moodle_error": app.main._latest_moodle_error(),
                "evidence": evidence,
            },
        )
    return int(teacher.moodle_id)


@router.post("/admin/moodle/enrol-student", summary="Inscribir alumno local en curso Moodle", tags=["Administracion"])
async def enrol_local_student_in_moodle_course(
    payload: Dict[str, Any],
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    username = str(payload.get("username") or "").strip()
    course_id = int(payload.get("course_id") or 0)
    if not username or not course_id:
        raise HTTPException(status_code=400, detail="Alumno y curso Moodle son obligatorios")

    student = db.query(models.User).filter(
        models.User.username == username,
        models.User.role == models.UserRole.STUDENT,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno local no encontrado")
    if not await moodle_client.check_course_exists(course_id):
        raise HTTPException(status_code=404, detail="Curso Moodle no encontrado")

    moodle_id = await _ensure_student_moodle_link(db, student)
    enrolled = await moodle_client.enrol_user(moodle_id, course_id, settings.MOODLE_STUDENT_ROLE_ID)
    if not enrolled:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible inscribir al alumno en el curso Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {
        "message": f"{student.full_name or student.username} fue inscrito correctamente",
        "username": student.username,
        "moodle_id": moodle_id,
        "course_id": course_id,
    }


@router.post("/admin/moodle/enrol-teacher", summary="Inscribir docente local en curso Moodle", tags=["Administracion"])
async def enrol_local_teacher_in_moodle_course(
    payload: Dict[str, Any],
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    username = str(payload.get("username") or "").strip()
    course_id = int(payload.get("course_id") or 0)
    if not username or not course_id:
        raise HTTPException(status_code=400, detail="Docente y curso Moodle son obligatorios")

    teacher = db.query(models.User).filter(
        models.User.username == username,
        models.User.role == models.UserRole.TEACHER,
    ).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Docente local no encontrado")
    if not await moodle_client.check_course_exists(course_id):
        raise HTTPException(status_code=404, detail="Curso Moodle no encontrado")

    moodle_id = await _ensure_teacher_moodle_link(db, teacher)
    enrolled = await moodle_client.enrol_user(moodle_id, course_id, settings.MOODLE_TEACHER_ROLE_ID)
    if not enrolled:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible inscribir al docente en el curso Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {
        "message": f"{teacher.full_name or teacher.username} fue asignado como profesor",
        "username": teacher.username,
        "moodle_id": moodle_id,
        "course_id": course_id,
        "role_id": settings.MOODLE_TEACHER_ROLE_ID,
    }


@router.post("/admin/moodle/local-groups/{group_id}/enrol", summary="Sincronizar grupo local con curso Moodle", tags=["Administracion"])
async def enrol_local_group_in_moodle_course(
    group_id: int,
    payload: Dict[str, Any],
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    course_id = int(payload.get("course_id") or 0)
    if not course_id:
        raise HTTPException(status_code=400, detail="Selecciona un curso Moodle")

    group = db.query(models.Group).filter(models.Group.id == group_id, models.Group.is_active == True).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo administrativo no encontrado")
    if not await moodle_client.check_course_exists(course_id):
        raise HTTPException(status_code=404, detail="Curso Moodle no encontrado")

    active_cycle = app.main._get_active_cycle(db)
    enrollment_query = (
        db.query(models.StudentEnrollment)
        .options(joinedload(models.StudentEnrollment.student))
        .filter(
            models.StudentEnrollment.group_id == group.id,
            models.StudentEnrollment.is_active == True,
        )
    )
    if active_cycle:
        enrollment_query = enrollment_query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)
    enrollments = enrollment_query.order_by(models.StudentEnrollment.id.asc()).all()

    course_groups = await moodle_client.get_course_groups(course_id)
    if course_groups is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar los grupos existentes del curso",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    moodle_group = next(
        (
            item
            for item in course_groups
            if str(item.get("name") or "").strip().casefold() == group.name.strip().casefold()
        ),
        None,
    )
    created_group = False
    if not moodle_group:
        moodle_group = await moodle_client.create_group(
            course_id=course_id,
            name=group.name,
            description=f"Sincronizado desde el grupo administrativo #{group.id}",
            idnumber=f"UNIVES-GROUP-{group.id}",
        )
        if not moodle_group:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "No fue posible crear el grupo administrativo en Moodle",
                    "moodle_error": app.main._latest_moodle_error(),
                },
            )
        created_group = True

    moodle_group_id = int(moodle_group.get("id") or 0)
    enrolled_ids: list[int] = []
    failures: list[dict] = []
    for enrollment in enrollments:
        student = enrollment.student
        if not student or student.role != models.UserRole.STUDENT:
            continue
        try:
            moodle_id = await _ensure_student_moodle_link(db, student)
            if not await moodle_client.enrol_user(moodle_id, course_id, settings.MOODLE_STUDENT_ROLE_ID):
                failures.append({"username": student.username, "error": app.main._latest_moodle_error() or "No se pudo enrolar"})
                continue
            enrolled_ids.append(moodle_id)
        except HTTPException as exc:
            failures.append({"username": student.username, "error": str(exc.detail)})

    if enrolled_ids and not await moodle_client.add_group_members(moodle_group_id, enrolled_ids):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Los alumnos fueron enrolados, pero no se pudieron agregar al grupo Moodle",
                "moodle_error": app.main._latest_moodle_error(),
                "enrolled": len(enrolled_ids),
            },
        )

    return {
        "message": f"Grupo {group.name} sincronizado con el curso Moodle",
        "local_group_id": group.id,
        "group_name": group.name,
        "moodle_group_id": moodle_group_id,
        "course_id": course_id,
        "group_created": created_group,
        "students_found": len(enrollments),
        "students_enrolled": len(enrolled_ids),
        "failures": failures,
    }


