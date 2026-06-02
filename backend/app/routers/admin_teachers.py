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

@router.get("/admin/teachers", response_model=list[schemas.UserListItem], summary="Listar docentes", tags=["Administracion"])
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


@router.put("/admin/teachers/{username}", response_model=schemas.User, summary="Actualizar docente", tags=["Administracion"])
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


@router.post("/admin/teachers", response_model=schemas.User, summary="Crear docente", tags=["Administracion"])
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


@router.post("/admin/teachers/{username}/moodle-sync", summary="Sincronizar docente con Moodle", tags=["Administracion"])
async def sync_teacher_moodle(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.TEACHER).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    evidence = await app.main._sync_teacher_to_moodle(db, user=db_user)
    if not evidence.get("success"):
        raise HTTPException(status_code=502, detail={"message": "No fue posible sincronizar el docente con Moodle", "moodle_error": app.main._latest_moodle_error(), "evidence": evidence})
    return {"message": "Docente sincronizado exitosamente con Moodle", "moodle_id": db_user.moodle_id, "evidence": evidence}


