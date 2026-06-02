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

@router.get("/admin/notifications", summary="Notificaciones del administrador", tags=["Administracion"])
def read_admin_notifications(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
    app.main._ensure_notification_schema(db)
    notifications: list[dict] = []

    pending_services = db.query(models.ServiceRequest).filter(models.ServiceRequest.status == models.ServiceRequestStatus.EN_PROCESO).count()
    if pending_services:
        app.main._push_notification(
            notifications,
            notif_type="services",
            title="Tramites pendientes",
            message=f"Hay {pending_services} tramite(s) en proceso.",
            level="warning",
            source="Servicios Escolares",
        )

    overdue_charges = db.query(models.Charge).filter(models.Charge.status == models.PaymentStatus.VENCIDO).count()
    if overdue_charges:
        app.main._push_notification(
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
        app.main._push_notification(
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
        app.main._push_notification(
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


@router.get("/admin/notifications/messages", response_model=list[schemas.NotificationMessageOut], summary="Mensajes de notificacion enviados", tags=["Administracion"])
def list_admin_notification_messages(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    app.main._ensure_notification_schema(db)
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


@router.post("/admin/notifications/messages", response_model=schemas.NotificationMessageOut, summary="Enviar notificacion a alumnos o docentes", tags=["Administracion"])
def create_admin_notification_message(
    payload: schemas.NotificationMessageCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    app.main._ensure_notification_schema(db)
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


