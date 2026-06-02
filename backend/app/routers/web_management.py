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

@router.post("/admin/web/upload", summary="Sube una imagen para la gestion web", tags=["Admin Web Management"])
async def upload_web_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Sube una imagen para la gestion web y la guarda en el directorio de assets publicos."""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")

    app.main._validate_upload_file(file, allowed_types=["image/jpeg", "image/png", "image/webp", "image/gif"])

    assets_dir = Path(settings.PUBLIC_ASSETS_DIR)
    assets_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix or ".jpg"
    safe_name = f"web_{uuid4().hex}{ext}"
    file_path = assets_dir / safe_name

    try:
        with file_path.open("wb") as buffer:
            buffer.write(await file.read())
    except Exception as e:
        logger.error(f"Error al guardar imagen web: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo guardar la imagen")

    return {"image_url": f"assets/{safe_name}", "filename": safe_name}


