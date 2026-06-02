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

@router.get("/admin/projects", response_model=List[schemas.ProjectOut], tags=["Admin Web"])
def admin_get_projects(category: Optional[str] = None, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    q = db.query(models.Project)
    if category:
        q = q.filter(models.Project.category == category)
    return q.order_by(models.Project.created_at.desc()).all()


@router.post("/admin/projects", response_model=schemas.ProjectOut, status_code=201, tags=["Admin Web"])
def admin_create_project(data: schemas.ProjectCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = models.Project(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.put("/admin/projects/{project_id}", response_model=schemas.ProjectOut, tags=["Admin Web"])
def admin_update_project(project_id: int, data: schemas.ProjectUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/admin/projects/{project_id}", status_code=204, tags=["Admin Web"])
def admin_delete_project(project_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    db.delete(project)
    db.commit()


@router.get("/admin/contacts", response_model=List[schemas.ContactOut], tags=["Admin Web"])
def admin_get_contacts(status: Optional[str] = None, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    q = db.query(models.Contact)
    if status:
        q = q.filter(models.Contact.status == status)
    return q.order_by(models.Contact.created_at.desc()).all()


@router.put("/admin/contacts/{contact_id}/status", response_model=schemas.ContactOut, tags=["Admin Web"])
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


@router.delete("/admin/contacts/{contact_id}", status_code=204, tags=["Admin Web"])
def admin_delete_contact(contact_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    db.delete(contact)
    db.commit()


# ── Historias de Éxito: endpoints públicos ──────────────────────────────────


@router.get("/admin/success-stories", response_model=List[schemas.SuccessStoryOut], tags=["Admin Web"])
def admin_get_success_stories(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.SuccessStory).order_by(models.SuccessStory.sort_order, models.SuccessStory.id).all()


@router.post("/admin/success-stories", response_model=schemas.SuccessStoryOut, status_code=201, tags=["Admin Web"])
def admin_create_success_story(data: schemas.SuccessStoryCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = models.SuccessStory(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item


@router.put("/admin/success-stories/{item_id}", response_model=schemas.SuccessStoryOut, tags=["Admin Web"])
def admin_update_success_story(item_id: int, data: schemas.SuccessStoryUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.SuccessStory).filter(models.SuccessStory.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item


@router.delete("/admin/success-stories/{item_id}", status_code=204, tags=["Admin Web"])
def admin_delete_success_story(item_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.SuccessStory).filter(models.SuccessStory.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(item); db.commit()


# ── Reels Testimoniales: endpoints públicos ──────────────────────────────────


@router.get("/admin/testimonial-reels", response_model=List[schemas.TestimonialReelOut], tags=["Admin Web"])
def admin_get_testimonial_reels(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.TestimonialReel).order_by(models.TestimonialReel.sort_order, models.TestimonialReel.id).all()


@router.post("/admin/testimonial-reels", response_model=schemas.TestimonialReelOut, status_code=201, tags=["Admin Web"])
def admin_create_testimonial_reel(data: schemas.TestimonialReelCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = models.TestimonialReel(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item


@router.put("/admin/testimonial-reels/{item_id}", response_model=schemas.TestimonialReelOut, tags=["Admin Web"])
def admin_update_testimonial_reel(item_id: int, data: schemas.TestimonialReelUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.TestimonialReel).filter(models.TestimonialReel.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item


@router.delete("/admin/testimonial-reels/{item_id}", status_code=204, tags=["Admin Web"])
def admin_delete_testimonial_reel(item_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.TestimonialReel).filter(models.TestimonialReel.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(item); db.commit()


# ── Cursos Extracurriculares: endpoints públicos ────────────────────────────


@router.get("/admin/extracurricular-courses", response_model=List[schemas.ExtracurricularCourseOut], tags=["Admin Web"])
def admin_get_extracurricular_courses(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.ExtracurricularCourse).order_by(models.ExtracurricularCourse.sort_order, models.ExtracurricularCourse.id).all()


@router.post("/admin/extracurricular-courses", response_model=schemas.ExtracurricularCourseOut, status_code=201, tags=["Admin Web"])
def admin_create_extracurricular_course(data: schemas.ExtracurricularCourseCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    course = models.ExtracurricularCourse(**data.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.put("/admin/extracurricular-courses/{course_id}", response_model=schemas.ExtracurricularCourseOut, tags=["Admin Web"])
def admin_update_extracurricular_course(course_id: int, data: schemas.ExtracurricularCourseUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    course = db.query(models.ExtracurricularCourse).filter(models.ExtracurricularCourse.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/admin/extracurricular-courses/{course_id}", status_code=204, tags=["Admin Web"])
def admin_delete_extracurricular_course(course_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    course = db.query(models.ExtracurricularCourse).filter(models.ExtracurricularCourse.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    db.delete(course)
    db.commit()


# ── Comunidades: endpoints públicos ─────────────────────────────────────────


@router.get("/admin/communities", response_model=List[schemas.CommunityOut], tags=["Admin Web"])
def admin_get_communities(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Community).order_by(models.Community.sort_order, models.Community.id).all()


@router.post("/admin/communities", response_model=schemas.CommunityOut, status_code=201, tags=["Admin Web"])
def admin_create_community(data: schemas.CommunityCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = models.Community(**data.model_dump())
    db.add(community)
    db.commit()
    db.refresh(community)
    return community


@router.put("/admin/communities/{community_id}", response_model=schemas.CommunityOut, tags=["Admin Web"])
def admin_update_community(community_id: int, data: schemas.CommunityUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = db.query(models.Community).filter(models.Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(community, field, value)
    db.commit()
    db.refresh(community)
    return community


@router.delete("/admin/communities/{community_id}", status_code=204, tags=["Admin Web"])
def admin_delete_community(community_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = db.query(models.Community).filter(models.Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    db.delete(community)
    db.commit()


