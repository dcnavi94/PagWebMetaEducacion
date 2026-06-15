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

@router.get("/public/projects", response_model=List[schemas.ProjectOut], tags=["Web Pública"])
def public_get_projects(category: Optional[str] = None, db: Session = Depends(get_db)):
    """Devuelve proyectos/eventos activos. Filtrable por category=portfolio|evento."""
    q = db.query(models.Project).filter(models.Project.is_active == True)
    if category:
        q = q.filter(models.Project.category == category)
    return q.order_by(models.Project.created_at.desc()).all()


@router.get("/public/projects/{project_id}", response_model=schemas.ProjectOut, tags=["Web Publica"])
def public_get_project(project_id: int, db: Session = Depends(get_db)):
    project = (
        db.query(models.Project)
        .filter(models.Project.id == project_id, models.Project.is_active == True)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return project


@router.post("/public/contacts", response_model=schemas.ContactOut, status_code=201, tags=["Web Pública"])
def public_create_contact(data: schemas.ContactCreate, db: Session = Depends(get_db)):
    """Recibe un lead del formulario de contacto de la landing page."""
    contact = models.Contact(**data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


# ── Página Web: endpoints de administración ──────────────────────────────────


@router.get("/public/success-stories", response_model=List[schemas.SuccessStoryOut], tags=["Web Pública"])
def public_get_success_stories(db: Session = Depends(get_db)):
    return db.query(models.SuccessStory).filter(models.SuccessStory.is_active == True).order_by(models.SuccessStory.sort_order, models.SuccessStory.id).all()


@router.get("/public/testimonial-reels", response_model=List[schemas.TestimonialReelOut], tags=["Web Pública"])
def public_get_testimonial_reels(db: Session = Depends(get_db)):
    return db.query(models.TestimonialReel).filter(models.TestimonialReel.is_active == True).order_by(models.TestimonialReel.sort_order, models.TestimonialReel.id).all()


@router.get("/public/extracurricular-courses", response_model=List[schemas.ExtracurricularCourseOut], tags=["Web Pública"])
def public_get_extracurricular_courses(db: Session = Depends(get_db)):
    """Devuelve cursos extracurriculares activos ordenados por sort_order."""
    return (
        db.query(models.ExtracurricularCourse)
        .filter(models.ExtracurricularCourse.is_active == True)
        .order_by(models.ExtracurricularCourse.sort_order, models.ExtracurricularCourse.id)
        .all()
    )


# ── Cursos Extracurriculares: endpoints de administración ───────────────────


@router.get("/public/communities", response_model=List[schemas.CommunityOut], tags=["Web Pública"])
def public_get_communities(db: Session = Depends(get_db)):
    """Devuelve comunidades activas ordenadas por sort_order."""
    return (
        db.query(models.Community)
        .filter(models.Community.is_active == True)
        .order_by(models.Community.sort_order, models.Community.id)
        .all()
    )


# ── Comunidades: endpoints de administración ─────────────────────────────────


