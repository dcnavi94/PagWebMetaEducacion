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

@router.get("/admin/services", response_model=list[schemas.ServiceRequestListItem], summary="Listar tramites", tags=["Administracion"])
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


@router.post("/admin/services", response_model=schemas.ServiceRequestWithStudent, summary="Crear tramite", tags=["Administracion"])
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


@router.put("/admin/services/{service_id}", response_model=schemas.ServiceRequest, summary="Actualizar tramite", tags=["Administracion"])
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


@router.delete("/admin/services/{service_id}", status_code=204, summary="Eliminar tramite", tags=["Administracion"])
def delete_service(service_id: int, current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    db_service = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == service_id).first()
    if not db_service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")
    db.delete(db_service)
    db.commit()


@router.get("/admin/academic-services", summary="Listar tramites academicos enriquecidos", tags=["Administracion"])
def read_admin_academic_services(current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
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
    return [app.main._serialize_ticket_row(row) for row in rows]


@router.get("/admin/support-tickets", summary="Listar tickets de soporte", tags=["Administracion"])
def read_admin_support_tickets(current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
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
    return [app.main._serialize_ticket_row(row) for row in rows]


@router.put("/admin/support-tickets/{ticket_id}", summary="Responder ticket de soporte", tags=["Administracion"])
def update_admin_support_ticket(ticket_id: int, payload: dict, current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
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
        history_json = app.main._append_ticket_history(
            history_json,
            actor=current_user.username,
            action="admin_response",
            message=admin_response,
            status_value=status_value,
        )
    if close_ticket:
        history_json = app.main._append_ticket_history(
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
    return app.main._serialize_ticket_row(updated)


@router.get("/admin/services/{service_id}/attachment", summary="Descargar adjunto de tramite", tags=["Administracion"])
def download_admin_service_attachment(
    service_id: int,
    current_user: models.User = Depends(services_or_admin),
    db: Session = Depends(get_db),
):
    service = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")
    file_path = app.main._service_attachment_absolute_path(service.attachment_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(path=file_path, filename=service.attachment_filename or file_path.name)


# ----------------------------
# Endpoints de usuario
# ----------------------------


