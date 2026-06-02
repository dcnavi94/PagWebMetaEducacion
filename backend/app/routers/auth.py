from typing import List, Optional, Any, Dict
import os
import app.main
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response, Request, Security
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, moodle_client, import_csv, curriculum_credits
from app.database import get_db
from app.dependencies import admin_required, teacher_or_admin, services_or_admin, oauth2_scheme
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import csv
from io import StringIO
import io
from fastapi.security import OAuth2PasswordRequestForm
from app.main import _get_client_ip, _enforce_login_rate_limit, _reset_login_attempts
from app.config import settings

router = APIRouter()
@router.post("/token", response_model=schemas.TokenPair, summary="Iniciar sesion", tags=["Autenticacion"])
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Autentica con username (matricula) y password. Devuelve tokens JWT (access y refresh)."""
    client_ip = app.main._get_client_ip(request)
    app.main._enforce_login_rate_limit(client_ip)

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
            detail="Acceso bloqueado. Consulta a servicios escolares, es posible que tengas alg├║n pago pendiente.",
        )
    app.main._reset_login_attempts(client_ip)
    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
    refresh_token = auth.create_refresh_token(data={"sub": user.username, "role": user.role})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/token/refresh", response_model=schemas.TokenPair, summary="Refrescar access token", tags=["Autenticacion"])
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


