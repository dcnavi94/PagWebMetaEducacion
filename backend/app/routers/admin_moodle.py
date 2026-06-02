from typing import List, Optional, Any, Dict
import os
import app.main
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response, Request, Security
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, moodle_client, import_csv, curriculum_credits
from app.config import settings
from app.database import get_db
from app.dependencies import admin_required, teacher_or_admin, services_or_admin, oauth2_scheme
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import csv
from io import StringIO
import io

router = APIRouter()

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


@router.get("/admin/moodle/courses", summary="Buscar cursos en Moodle", tags=["Administracion"])
async def admin_moodle_courses(q: str = "", current_user: models.User = Depends(admin_required)):
    courses = await moodle_client.search_courses(q)
    if courses is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar cursos en Moodle", "moodle_error": app.main._latest_moodle_error()})
    return {"query": q, "count": len(courses), "courses": [app.main._serialize_moodle_course(course) for course in courses]}


@router.get("/admin/moodle/courses/{course_id}/contents", summary="Contenidos de curso Moodle", tags=["Administracion"])
async def admin_moodle_course_contents(course_id: int, current_user: models.User = Depends(admin_required)):
    contents = await moodle_client.get_course_contents(course_id)
    if contents is None:
        raise HTTPException(status_code=502, detail={"message": "No fue posible consultar contenidos del curso en Moodle", "moodle_error": app.main._latest_moodle_error()})
    return {"course_id": course_id, "sections": contents}


