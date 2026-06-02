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

@router.get("/catalogs/careers", response_model=list[schemas.Career], summary="Catalogo de carreras", tags=["Catalogos"])
def list_careers(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las carreras almacenadas en la base de datos."""
    return db.query(models.Career).order_by(models.Career.name).all()


@router.post("/admin/catalogs/careers", response_model=schemas.Career, summary="Crear carrera", tags=["Catalogos"])
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


@router.get("/catalogs/modalities", response_model=list[schemas.Modality], summary="Catalogo de modalidades", tags=["Catalogos"])
def list_modalities(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las modalidades disponibles."""
    return db.query(models.Modality).order_by(models.Modality.name).all()


@router.post("/admin/catalogs/modalities", response_model=schemas.Modality, summary="Crear modalidad", tags=["Catalogos"])
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


