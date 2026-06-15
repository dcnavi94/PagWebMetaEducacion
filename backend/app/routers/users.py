from typing import List, Optional, Any, Dict
import hashlib
import hmac
import os
import time
import httpx
from urllib.parse import quote, urlparse
import app.main
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response, Request, Security
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, import_csv, curriculum_credits
from app.moodle_client import moodle_client
from app.config import settings
from app.database import get_db
from app.dependencies import admin_required, teacher_or_admin, services_or_admin, oauth2_scheme
from sqlalchemy.orm import joinedload
from sqlalchemy import func, text
import logging
import csv
from io import StringIO
import io

router = APIRouter()

@router.get("/users/me", response_model=schemas.User, summary="Perfil del usuario", tags=["Usuario"])
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    valid_service_types = {item.value for item in schemas.ServiceRequestType}
    filtered_service_requests = [
        service_request
        for service_request in (current_user.service_requests or [])
        if (service_request.type in valid_service_types)
    ]
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "moodle_id": current_user.moodle_id,
        "user_status": current_user.user_status,
        "enrollment_status": current_user.enrollment_status,
        "career_id": current_user.career_id,
        "carrera": current_user.carrera,
        "modality_id": current_user.modality_id,
        "modalidad": current_user.modalidad,
        "semestre": current_user.semestre,
        "grupo": current_user.grupo,
        "academic_advisor_id": current_user.academic_advisor_id,
        "payments": current_user.payments or [],
        "grades": current_user.grades or [],
        "service_requests": filtered_service_requests,
    }


@router.get("/users/me/profile", response_model=schemas.UserProfileOut, summary="Perfil completo del alumno", tags=["Usuario"])
def read_user_profile(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # Buscar inscripción activa del alumno en el ciclo vigente
    active_enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == current_user.id,
            models.StudentEnrollment.is_active == True,
        )
        .order_by(models.StudentEnrollment.id.desc())
        .first()
    )

    career_name = None
    modality_name = None
    semester = None
    group_name = None
    cycle_period = None

    if active_enrollment:
        if active_enrollment.career:
            career_name = active_enrollment.career.name
        if active_enrollment.modality:
            modality_name = active_enrollment.modality.name
        semester = active_enrollment.semester
        if active_enrollment.group:
            group_name = active_enrollment.group.name
        if active_enrollment.cycle:
            cycle_period = active_enrollment.cycle.period

    # Fallback a campos legacy si la inscripción no tiene relaciones
    if not career_name:
        career_name = (
            current_user.career_rel.name if current_user.career_rel else current_user.carrera
        )
    if not modality_name:
        modality_name = (
            current_user.modality_rel.name if current_user.modality_rel else current_user.modalidad
        )
    if not semester:
        semester = current_user.semestre
    if not group_name:
        group_name = current_user.grupo

    return schemas.UserProfileOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        user_status=current_user.user_status,
        enrollment_status=current_user.enrollment_status,
        career_name=career_name,
        modality_name=modality_name,
        semester=semester,
        group_name=group_name,
        cycle_period=cycle_period,
    )


# ----------------------------
# Admin
# ----------------------------


@router.post("/users/me/services", response_model=schemas.ServiceRequest, summary="Solicitar tramite", tags=["Usuario"])
def create_user_service(
    service: schemas.ServiceRequestSelfCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    new_service = models.ServiceRequest(
        student_id=current_user.id,
        type=service.type,
        status=models.ServiceRequestStatus.EN_PROCESO,
        request_date=service.request_date,
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@router.post("/users/me/services/with-document", response_model=schemas.ServiceRequest, summary="Solicitar tramite con documento", tags=["Usuario"])
async def create_user_service_with_document(
    type: str = Form(...),
    request_date: str = Form(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    service_payload = schemas.ServiceRequestSelfCreate(type=type, request_date=request_date)
    original_filename, stored_relative_path = app.main._store_service_attachment(
        student_username=current_user.username,
        file=file,
    )
    new_service = models.ServiceRequest(
        student_id=current_user.id,
        type=service_payload.type,
        status=models.ServiceRequestStatus.EN_PROCESO,
        request_date=service_payload.request_date,
        attachment_filename=original_filename,
        attachment_path=stored_relative_path,
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@router.get("/users/me/services/{service_id}/attachment", summary="Descargar adjunto de tramite propio", tags=["Usuario"])
def download_user_service_attachment(
    service_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    service = (
        db.query(models.ServiceRequest)
        .filter(
            models.ServiceRequest.id == service_id,
            models.ServiceRequest.student_id == current_user.id,
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")
    file_path = app.main._service_attachment_absolute_path(service.attachment_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(path=file_path, filename=service.attachment_filename or file_path.name)


@router.get("/users/me/grades", summary="Mis calificaciones", tags=["Usuario"])
def read_user_grades(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.carrera:
        app.main._assign_curriculum_to_student(db, current_user.id, current_user.carrera)
        db.commit()

    result = []
    seen_grade_ids = set()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == current_user.id)
        .all()
    )
    for course_enrollment in course_enrollments:
        grade = app.main._get_grade_for_course_enrollment(course_enrollment)
        if grade:
            seen_grade_ids.add(grade.id)
        result.append(app.main._serialize_grade_row(grade=grade, course_enrollment=course_enrollment))

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == current_user.id).all()
    for grade in legacy_grades:
        if grade.id in seen_grade_ids:
            continue
        result.append(app.main._serialize_grade_row(grade=grade))

    result.sort(
        key=lambda item: (
            app.main._parse_semester_num(item.get("period")),
            (item.get("description") or "").lower(),
            item.get("grade_id") or 0,
        )
    )
    return app.main._effective_student_grade_rows(result)


@router.get("/users/me/academic-history", response_model=list[schemas.AcademicHistoryItem], summary="Mi historial academico", tags=["Usuario"])
def read_user_academic_history(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    history = app.main._get_academic_history_for_student(db, current_user.id)
    return [
        item for item in history
        if item["course_enrollment_id"] or item["assignment_id"] or item["final_score"] is not None
    ]


@router.get("/users/me/kardex-summary", response_model=schemas.KardexSummaryOut, summary="Resumen completo del Kardex", tags=["Usuario"])
def read_user_kardex_summary(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    from app.curriculum_credits import CURRICULUM_CREDITS

    history = app.main._get_academic_history_for_student(db, current_user.id)
    history_items = [
        item for item in history
        if item["course_enrollment_id"] or item["assignment_id"] or item["final_score"] is not None
    ]

    gpa_sum = 0.0
    gpa_count = 0
    earned_credits = 0

    for item in history_items:
        score = item.get("final_score")
        if score is not None and score > 0:
            gpa_sum += score
            gpa_count += 1
            if item.get("status") == models.GradeStatus.APROBADA or score >= 6.0:
                earned_credits += item.get("credits") or 8

    gpa = round(gpa_sum / gpa_count, 2) if gpa_count > 0 else 0.0

    total_career_credits = 0
    career_name = current_user.carrera or ""
    matched_career = None
    for k in CURRICULUM_CREDITS.keys():
        if k.lower() in career_name.lower() or career_name.lower() in k.lower():
            matched_career = k
            break
            
    if matched_career:
        for semester_subjects in CURRICULUM_CREDITS[matched_career].values():
            for subject in semester_subjects:
                total_career_credits += subject.get("credits") or 8
    else:
        total_career_credits = 350  # Fallback

    progress_percentage = round((earned_credits / total_career_credits) * 100, 1) if total_career_credits > 0 else 0.0
    if progress_percentage > 100:
        progress_percentage = 100.0

    return {
        "gpa": gpa,
        "earned_credits": earned_credits,
        "total_career_credits": total_career_credits,
        "progress_percentage": progress_percentage,
        "history": history_items
    }


@router.get("/users/me/calendar", response_model=list[schemas.CalendarEventOut], summary="Calendario Academico", tags=["Usuario"])
def read_user_calendar(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    # Mock data for 2026 Academic Year
    # categories: exam, payment, enrollment, holiday
    return [
        {"id": 1, "title": "Inicio de Clases - Cuatrimestre Enero-Abril", "date": "2026-01-05", "category": "enrollment", "description": "Inicio de todas las clases regulares."},
        {"id": 2, "title": "Día de la Constitución", "date": "2026-02-02", "category": "holiday", "description": "Suspensión de labores institucionales."},
        {"id": 3, "title": "Límite de pago 1ra Mensualidad", "date": "2026-02-15", "category": "payment", "description": "Último día para pago sin recargos."},
        {"id": 4, "title": "Exámenes Parciales", "date": "2026-02-23", "category": "exam", "description": "Inicio de periodo de evaluación parcial."},
        {"id": 5, "title": "Límite de pago 2da Mensualidad", "date": "2026-03-15", "category": "payment", "description": "Último día para pago sin recargos."},
        {"id": 6, "title": "Natalicio de Benito Juárez", "date": "2026-03-16", "category": "holiday", "description": "Suspensión de labores institucionales."},
        {"id": 7, "title": "Semana Santa", "date": "2026-03-30", "category": "holiday", "description": "Vacaciones de primavera."},
        {"id": 8, "title": "Exámenes Finales", "date": "2026-04-13", "category": "exam", "description": "Evaluaciones ordinarias finales."},
        {"id": 9, "title": "Día del Trabajo", "date": "2026-05-01", "category": "holiday", "description": "Suspensión de labores."},
        {"id": 10, "title": "Inicio de Clases - Cuatrimestre Mayo-Agosto", "date": "2026-05-04", "category": "enrollment", "description": "Inicio de clases nuevo cuatrimestre."},
        {"id": 11, "title": "Límite de pago 1ra Mensualidad", "date": "2026-06-15", "category": "payment", "description": "Pago sin recargos."},
        {"id": 12, "title": "Exámenes Parciales", "date": "2026-06-22", "category": "exam", "description": "Evaluaciones de medio término."},
        {"id": 13, "title": "Día de la Independencia", "date": "2026-09-16", "category": "holiday", "description": "Suspensión de labores."},
        {"id": 14, "title": "Exámenes Parciales", "date": "2026-10-19", "category": "exam", "description": "Periodo de evaluación parcial Otoño."},
        {"id": 15, "title": "Día de Muertos", "date": "2026-11-02", "category": "holiday", "description": "Suspensión de labores."},
        {"id": 16, "title": "Revolución Mexicana", "date": "2026-11-16", "category": "holiday", "description": "Día feriado oficial."},
        {"id": 17, "title": "Exámenes Finales", "date": "2026-12-07", "category": "exam", "description": "Evaluaciones finales de diciembre."},
        {"id": 18, "title": "Vacaciones de Invierno", "date": "2026-12-21", "category": "holiday", "description": "Periodo vacacional decembrino."},
    ]


@router.put("/users/me", summary="Actualizar perfil", tags=["Usuario"])
def update_user_me(user_update: schemas.UserUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    if user_update.email is not None:
        current_user.email = user_update.email
    if user_update.password:
        current_user.hashed_password = auth.get_password_hash(user_update.password)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/upload-document", summary="Subir documento", tags=["Usuario"])
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "otro",
    current_user: models.User = Depends(auth.get_current_user),
):
    app.main._validate_upload_file(file)
    upload_dir = f"{settings.UPLOAD_DIR}/{current_user.username}"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {"filename": file.filename, "status": "success", "message": f"Documento {document_type} subido correctamente"}


@router.get("/users/me/payments", summary="Mis pagos", tags=["Usuario"])
def read_user_payments(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Payment).filter(models.Payment.student_id == current_user.id).all()


@router.get("/users/me/charges", response_model=list[schemas.Charge], summary="Mis cargos", tags=["Usuario"])
def read_user_charges(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Charge).filter(models.Charge.student_id == current_user.id).order_by(models.Charge.id.desc()).all()


def _mercado_pago_headers() -> dict:
    if not settings.MERCADO_PAGO_ACCESS_TOKEN:
        raise HTTPException(status_code=503, detail="Mercado Pago no esta configurado")
    return {
        "Authorization": f"Bearer {settings.MERCADO_PAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _mp_external_reference(charge: models.Charge) -> str:
    return f"unives-charge-{charge.id}-student-{charge.student_id}"


def _mp_charge_id_from_reference(reference: Optional[str]) -> Optional[int]:
    if not reference:
        return None
    parts = reference.split("-")
    if len(parts) >= 3 and parts[0] == "unives" and parts[1] == "charge":
        try:
            return int(parts[2])
        except ValueError:
            return None
    return None


async def _mp_get_payment(payment_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"https://api.mercadopago.com/v1/payments/{quote(str(payment_id))}",
            headers=_mercado_pago_headers(),
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Pago no encontrado en Mercado Pago")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="No fue posible consultar el pago en Mercado Pago")
    return response.json()


def _register_approved_mp_payment(db: Session, charge: models.Charge, payment_data: dict) -> Optional[models.Payment]:
    if payment_data.get("status") != "approved":
        return None

    payment_id = str(payment_data.get("id") or "")
    if not payment_id:
        return None

    existing = (
        db.query(models.Payment)
        .filter(
            models.Payment.charge_id == charge.id,
            models.Payment.reference == f"MP-{payment_id}",
        )
        .first()
    )
    if existing:
        return existing

    amount = float(payment_data.get("transaction_amount") or charge.amount or 0)
    paid_at = payment_data.get("date_approved") or payment_data.get("date_created")
    payment_date = None
    if paid_at:
        try:
            payment_date = datetime.fromisoformat(str(paid_at).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            payment_date = datetime.utcnow()

    db_payment = models.Payment(
        student_id=charge.student_id,
        charge_id=charge.id,
        concept=charge.concept,
        amount=amount,
        due_date=charge.due_date,
        status=models.PaymentStatus.PAGADO,
        payment_date=payment_date or datetime.utcnow(),
        payment_method=models.PaymentMethod.TARJETA,
        reference=f"MP-{payment_id}",
        is_conciliated=True,
        receipt_url=payment_data.get("transaction_details", {}).get("external_resource_url"),
    )
    db.add(db_payment)
    charge.status = models.PaymentStatus.PAGADO
    db.commit()
    db.refresh(db_payment)
    return db_payment


@router.get("/users/me/payments/mercadopago/config", tags=["Usuario"], summary="Estado de Mercado Pago")
def read_mercado_pago_config(current_user: models.User = Depends(auth.get_current_user)):
    return {
        "enabled": bool(settings.MERCADO_PAGO_ACCESS_TOKEN),
        "public_key_configured": bool(settings.MERCADO_PAGO_PUBLIC_KEY),
        "sandbox": settings.MERCADO_PAGO_SANDBOX,
        "currency_id": settings.MERCADO_PAGO_CURRENCY_ID,
    }


@router.post("/users/me/charges/{charge_id}/mercadopago/preference", tags=["Usuario"], summary="Crear preferencia Mercado Pago")
async def create_mercado_pago_preference(
    charge_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    charge = (
        db.query(models.Charge)
        .filter(models.Charge.id == charge_id, models.Charge.student_id == current_user.id)
        .first()
    )
    if not charge:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    if charge.status == models.PaymentStatus.PAGADO:
        raise HTTPException(status_code=400, detail="Este cargo ya esta pagado")
    if charge.amount <= 0:
        raise HTTPException(status_code=400, detail="El cargo no tiene un monto valido")

    external_reference = _mp_external_reference(charge)
    back_url = f"{settings.PORTAL_PUBLIC_URL}/campus-virtual?mp_charge_id={charge.id}"
    payload = {
        "items": [{
            "id": str(charge.id),
            "title": f"UNIVES - {charge.concept}",
            "description": charge.period_label or "Cargo escolar",
            "quantity": 1,
            "currency_id": settings.MERCADO_PAGO_CURRENCY_ID or "MXN",
            "unit_price": round(float(charge.amount), 2),
        }],
        "payer": {
            "name": current_user.full_name or current_user.username,
            "email": current_user.email,
        },
        "external_reference": external_reference,
        "back_urls": {
            "success": f"{back_url}&mp_result=success",
            "pending": f"{back_url}&mp_result=pending",
            "failure": f"{back_url}&mp_result=failure",
        },
        "auto_return": "approved",
        "notification_url": f"{settings.API_PUBLIC_URL}/payments/mercadopago/webhook",
        "statement_descriptor": "UNIVES",
        "metadata": {
            "charge_id": charge.id,
            "student_id": current_user.id,
            "student_username": current_user.username,
        },
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.mercadopago.com/checkout/preferences",
            headers=_mercado_pago_headers(),
            json=payload,
        )
    if response.status_code >= 400:
        logging.error("Mercado Pago preference error %s: %s", response.status_code, response.text)
        raise HTTPException(status_code=502, detail="No se pudo crear el enlace de pago")
    preference = response.json()
    return {
        "preference_id": preference.get("id"),
        "init_point": preference.get("init_point"),
        "sandbox_init_point": preference.get("sandbox_init_point"),
        "external_reference": external_reference,
    }


@router.post("/users/me/charges/{charge_id}/mercadopago/confirm", tags=["Usuario"], summary="Confirmar pago Mercado Pago")
async def confirm_mercado_pago_charge(
    charge_id: int,
    payload: dict,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    payment_id = str(payload.get("payment_id") or payload.get("collection_id") or "").strip()
    if not payment_id:
        raise HTTPException(status_code=400, detail="payment_id es requerido")
    charge = (
        db.query(models.Charge)
        .filter(models.Charge.id == charge_id, models.Charge.student_id == current_user.id)
        .first()
    )
    if not charge:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")

    payment_data = await _mp_get_payment(payment_id)
    reference_charge_id = _mp_charge_id_from_reference(payment_data.get("external_reference"))
    metadata_charge_id = payment_data.get("metadata", {}).get("charge_id")
    if reference_charge_id != charge.id and int(metadata_charge_id or 0) != charge.id:
        raise HTTPException(status_code=400, detail="El pago no corresponde a este cargo")

    db_payment = _register_approved_mp_payment(db, charge, payment_data)
    return {
        "status": payment_data.get("status"),
        "status_detail": payment_data.get("status_detail"),
        "approved": bool(db_payment),
        "payment_id": payment_id,
        "charge_id": charge.id,
    }


@router.post("/payments/mercadopago/webhook", tags=["Pagos"], summary="Webhook Mercado Pago")
async def mercado_pago_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    payment_id = (
        payload.get("data", {}).get("id")
        or payload.get("id")
        or request.query_params.get("data.id")
        or request.query_params.get("id")
    )
    event_type = payload.get("type") or request.query_params.get("type")
    if event_type and event_type not in {"payment", "topic_payment"}:
        return {"ok": True, "ignored": event_type}
    if not payment_id:
        return {"ok": True, "ignored": "missing_payment_id"}

    try:
        payment_data = await _mp_get_payment(str(payment_id))
    except HTTPException as exc:
        logging.warning("No se pudo procesar webhook Mercado Pago %s: %s", payment_id, exc.detail)
        return {"ok": False, "detail": exc.detail}

    charge_id = _mp_charge_id_from_reference(payment_data.get("external_reference"))
    charge_id = charge_id or int(payment_data.get("metadata", {}).get("charge_id") or 0)
    charge = db.query(models.Charge).filter(models.Charge.id == charge_id).first() if charge_id else None
    if not charge:
        return {"ok": False, "detail": "charge_not_found"}

    db_payment = _register_approved_mp_payment(db, charge, payment_data)
    return {
        "ok": True,
        "status": payment_data.get("status"),
        "approved": bool(db_payment),
        "charge_id": charge.id,
        "payment_id": str(payment_id),
    }


@router.get("/users/me/services", summary="Mis tramites", tags=["Usuario"])
def read_user_services(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.ServiceRequest).filter(models.ServiceRequest.student_id == current_user.id).all()


@router.post("/users/me/academic-services", summary="Solicitar tramite academico enriquecido", tags=["Usuario"])
def create_user_academic_service(payload: dict, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
    service_type = (payload.get("type") or "").strip()
    subject = (payload.get("subject") or "").strip()
    description = (payload.get("description") or "").strip()
    if not service_type or not subject or not description:
        raise HTTPException(status_code=400, detail="type, subject y description son requeridos")

    history_json = app.main._append_ticket_history(
        None,
        actor=current_user.username,
        action="create_academic_service",
        message="Tramite academico creado por el alumno",
        status_value=models.ServiceRequestStatus.EN_PROCESO.value,
    )
    request_date = datetime.utcnow()
    result = db.execute(text("""
        INSERT INTO service_requests (
            student_id, type, status, request_date, subject, description,
            source_system, admin_response, history_json, is_support_ticket, updated_at
        )
        VALUES (
            :student_id, :type, :status, :request_date, :subject, :description,
            :source_system, NULL, :history_json, FALSE, :updated_at
        )
        RETURNING id, student_id, type, status, request_date, subject, description,
                  source_system, admin_response, attachment_filename, updated_at, closed_at, history_json
    """), {
        "student_id": current_user.id,
        "type": service_type,
        "status": models.ServiceRequestStatus.EN_PROCESO.value,
        "request_date": request_date,
        "subject": subject,
        "description": description,
        "source_system": "Portal del Alumno",
        "history_json": history_json,
        "updated_at": request_date,
    }).fetchone()
    db.commit()
    return app.main._serialize_ticket_row(result)


@router.post("/users/me/support-tickets", summary="Crear ticket de soporte", tags=["Usuario"])
def create_user_support_ticket(payload: dict, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
    category = (payload.get("category") or payload.get("type") or "").strip()
    subject = (payload.get("subject") or "").strip()
    description = (payload.get("description") or "").strip()
    source_system = (payload.get("source_system") or "Plataforma").strip()
    if not category or not subject or not description:
        raise HTTPException(status_code=400, detail="category, subject y description son requeridos")

    request_date = datetime.utcnow()
    history_json = app.main._append_ticket_history(
        None,
        actor=current_user.username,
        action="create_support_ticket",
        message=f"Ticket levantado desde {source_system}",
        status_value=models.ServiceRequestStatus.EN_PROCESO.value,
    )
    result = db.execute(text("""
        INSERT INTO service_requests (
            student_id, type, status, request_date, subject, description,
            source_system, admin_response, history_json, is_support_ticket, updated_at
        )
        VALUES (
            :student_id, :type, :status, :request_date, :subject, :description,
            :source_system, NULL, :history_json, TRUE, :updated_at
        )
        RETURNING id, student_id, type, status, request_date, subject, description,
                  source_system, admin_response, attachment_filename, updated_at, closed_at, history_json
    """), {
        "student_id": current_user.id,
        "type": category,
        "status": models.ServiceRequestStatus.EN_PROCESO.value,
        "request_date": request_date,
        "subject": subject,
        "description": description,
        "source_system": source_system,
        "history_json": history_json,
        "updated_at": request_date,
    }).fetchone()
    db.commit()
    return app.main._serialize_ticket_row(result)


@router.get("/users/me/support-tickets", summary="Mis tickets de soporte", tags=["Usuario"])
def read_user_support_tickets(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
    rows = db.execute(text("""
        SELECT
            id, student_id, type, status, request_date, subject, description,
            source_system, admin_response, attachment_filename, updated_at, closed_at, history_json
        FROM service_requests
        WHERE student_id = :student_id
          AND COALESCE(is_support_ticket, FALSE) = TRUE
        ORDER BY request_date DESC, id DESC
    """), {"student_id": current_user.id}).fetchall()
    return [app.main._serialize_ticket_row(row) for row in rows]


@router.get("/users/me/notifications", summary="Notificaciones del alumno", tags=["Usuario"])
def read_user_notifications(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    app.main._ensure_portal_extensions(db)
    notifications: list[dict] = app.main._get_custom_notifications_for_user(db, current_user)

    pending_charges = db.query(models.Charge).filter(
        models.Charge.student_id == current_user.id,
        models.Charge.status != models.PaymentStatus.PAGADO,
    ).count()
    if pending_charges:
        app.main._push_notification(
            notifications,
            notif_type="charges",
            title="Pagos pendientes",
            message=f"Tienes {pending_charges} cargo(s) pendiente(s).",
            level="warning",
            source="Tesoreria",
        )

    pending_services = db.query(models.ServiceRequest).filter(
        models.ServiceRequest.student_id == current_user.id,
        models.ServiceRequest.status == models.ServiceRequestStatus.EN_PROCESO,
    ).count()
    if pending_services:
        app.main._push_notification(
            notifications,
            notif_type="services",
            title="Tramites en proceso",
            message=f"Tienes {pending_services} tramite(s) en seguimiento.",
            level="info",
            source="Servicios",
        )

    support_rows = db.execute(text("""
        SELECT id, subject, status, updated_at, request_date
        FROM service_requests
        WHERE student_id = :student_id
          AND COALESCE(is_support_ticket, FALSE) = TRUE
          AND status != :closed_status
        ORDER BY COALESCE(updated_at, request_date) DESC
    """), {
        "student_id": current_user.id,
        "closed_status": models.ServiceRequestStatus.ENTREGADO.value,
    }).fetchall()
    for row in support_rows:
        row_data = row._mapping
        app.main._push_notification(
            notifications,
            notif_type="support",
            title=f"Ticket #{row_data.get('id')} activo",
            message=f"{row_data.get('subject') or 'Soporte tecnico'} · Estatus: {row_data.get('status')}",
            level="warning",
            source="Soporte",
            created_at=row_data.get("updated_at") or row_data.get("request_date") or datetime.utcnow(),
        )

    if settings.MOODLE_BASE_URL:
        app.main._push_notification(
            notifications,
            notif_type="moodle",
            title="Aula virtual disponible",
            message="Tu acceso a Moodle esta listo para abrirse desde el portal.",
            level="success",
            source="Moodle",
            action_url=app.main._build_moodle_url("/my/"),
        )
    else:
        app.main._push_notification(
            notifications,
            notif_type="moodle",
            title="Aula virtual no configurada",
            message="Moodle aun no esta configurado en este entorno.",
            level="secondary",
            source="Moodle",
        )

    advisor = read_user_advisor(current_user=current_user, db=db)
    advisor_data = advisor.get("advisor")
    if advisor_data:
        advisor_name = advisor_data.get("teacher_full_name") or advisor_data.get("teacher_username") or "Tutor"
        app.main._push_notification(
            notifications,
            notif_type="advisor",
            title="Asesoria activa",
            message=f"Tu asesor actual es {advisor_name}.",
            level="info",
            source="Asesoria",
        )

    notifications.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"count": len(notifications), "items": notifications[:20]}


@router.post("/users/me/notifications/{notification_id}/read", summary="Marcar notificacion como leida", tags=["Usuario"])
def mark_user_notification_read(
    notification_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    notification = app.main._get_user_manageable_notification(db, notification_id=notification_id, user=current_user)
    if not notification:
        raise HTTPException(status_code=404, detail="Notificacion no encontrada")
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.commit()
    db.refresh(notification)
    return {"ok": True, "id": notification.id, "is_read": True, "read_at": notification.read_at.isoformat() if notification.read_at else None}


@router.delete("/users/me/notifications/{notification_id}", summary="Ocultar notificacion del alumno", tags=["Usuario"])
def delete_user_notification(
    notification_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    notification = app.main._get_user_manageable_notification(db, notification_id=notification_id, user=current_user)
    if not notification:
        raise HTTPException(status_code=404, detail="Notificacion no encontrada")
    
    if notification.target_scope == "user":
        notification.deleted_by_recipient = True
        notification.deleted_at = datetime.utcnow()
    else:
        # Prevent hiding broadcast messages for everyone
        raise HTTPException(status_code=400, detail="Las notificaciones generales no se pueden eliminar")
        
    db.commit()
    return {"ok": True, "id": notification_id}


@router.get("/users/me/advisor", summary="Tutor o asesor actual del alumno", tags=["Usuario"])
def read_user_advisor(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    advisor = app.main._get_effective_student_advisor(db, current_user)
    active_enrollment = app.main._get_active_student_enrollment(db, current_user.id)
    if not advisor:
        return {"advisor": None, "messages": []}

    advisor_messages = (
        db.query(models.NotificationMessage)
        .filter(
            models.NotificationMessage.category == "advisor",
            models.NotificationMessage.recipient_user_id == current_user.id,
            models.NotificationMessage.created_by_user_id == advisor.id,
            models.NotificationMessage.is_active == True,
        )
        .order_by(models.NotificationMessage.created_at.desc(), models.NotificationMessage.id.desc())
        .limit(10)
        .all()
    )
    return {
        "advisor": {
            "teacher_id": advisor.id,
            "teacher_username": advisor.username,
            "teacher_full_name": advisor.full_name,
            "teacher_email": advisor.email,
            "period_label": active_enrollment.cycle.period if active_enrollment.cycle else None,
            "notes": current_user.academic_advisor_id
                and "Seguimiento academico directo asignado por administracion."
                or (f"Seguimiento academico del grupo {active_enrollment.group.name}." if active_enrollment and active_enrollment.group else "Seguimiento academico activo."),
        },
        "messages": [
            {
                "id": message.id,
                "title": message.title,
                "message": message.message,
                "created_at": message.created_at,
            }
            for message in advisor_messages
        ],
    }


@router.get("/users/me/pasaporte", response_model=schemas.PasaporteOut, summary="Pasaporte digital del alumno", tags=["Usuario"])
def read_pasaporte(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    active_enrollment = app.main._get_active_student_enrollment(db, current_user.id)
    career_name = ""
    if active_enrollment and active_enrollment.career:
        career_name = active_enrollment.career.name or ""
    if not career_name:
        career_name = current_user.carrera or ""
    is_university = "preparatoria" not in career_name.lower() and "prepa" not in career_name.lower()

    thesis = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == current_user.id).first()
    ss_records = db.query(models.SocialServiceRecord).filter(models.SocialServiceRecord.student_id == current_user.id).all()

    return schemas.PasaporteOut(
        is_university=is_university,
        thesis=schemas.ThesisOut.model_validate(thesis) if thesis else None,
        social_services=[schemas.SocialServiceOut.model_validate(r) for r in ss_records],
    )


@router.get("/users/me/moodle-url", summary="Estado y URL base de Moodle", tags=["Usuario"])
async def read_user_moodle_url(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    credentials = app.main._get_moodle_credentials_for_user(db, current_user)
    remote_courses = (
        await moodle_client.get_user_courses(int(current_user.moodle_id))
        if current_user.moodle_id and settings.MOODLE_REST_TOKEN
        else []
    )
    serialized_courses = [app.main._serialize_moodle_course(course) for course in (remote_courses or [])]
    return {
        "enabled": bool(settings.MOODLE_BASE_URL),
        "linked": bool(current_user.moodle_id),
        "moodle_id": current_user.moodle_id,
        "launch_url": app.main._build_moodle_public_url("/my/"),
        "login_url": app.main._build_moodle_public_url("/login/index.php"),
        "courses_url": app.main._build_moodle_public_url("/my/courses.php"),
        "moodle_username": credentials.get("moodle_username"),
        "password_configured": bool(credentials.get("moodle_password")),
        "has_courses": bool(serialized_courses),
        "courses_count": len(serialized_courses),
        "courses": serialized_courses,
    }


@router.get("/users/me/moodle-badges", summary="Mis insignias Moodle", tags=["Usuario"])
async def read_user_moodle_badges(
    current_user: models.User = Depends(auth.get_current_user),
):
    if not current_user.moodle_id:
        return {"count": 0, "badges": []}
    result = await moodle_client.badge_action("user", user_id=int(current_user.moodle_id))
    if result is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar las insignias Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    styles = {
        "Excelencia Académica": {"icon": "bi-trophy-fill", "color": "warning"},
        "Participación Destacada": {"icon": "bi-megaphone-fill", "color": "primary"},
        "Trabajo en Equipo": {"icon": "bi-people-fill", "color": "success"},
        "Constancia": {"icon": "bi-fire", "color": "danger"},
    }
    badges = []
    for badge in result.get("badges") or []:
        badge["style"] = styles.get(badge.get("name"), {"icon": "bi-award-fill", "color": "info"})
        badges.append(badge)
    return {"count": len(badges), "badges": badges}


@router.get("/users/me/moodle-launch", summary="Preparar apertura de Moodle", tags=["Usuario"])
async def read_user_moodle_launch(target_url: Optional[str] = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    sync_error = None
    if (
        not current_user.moodle_id
        and settings.MOODLE_REST_TOKEN
        and current_user.role in (models.UserRole.TEACHER, models.UserRole.STUDENT)
    ):
        sync = (
            app.main._sync_teacher_to_moodle
            if current_user.role == models.UserRole.TEACHER
            else app.main._sync_student_to_moodle
        )
        evidence = await sync(db, user=current_user)
        if not evidence.get("success"):
            sync_error = app.main._latest_moodle_error() or "No fue posible vincular la cuenta con Moodle"

    credentials = app.main._get_moodle_credentials_for_user(db, current_user)
    base_target = target_url or app.main._build_moodle_public_url("/my/")
    parsed_target = urlparse(base_target)
    target_path = parsed_target.path or "/my/"
    if parsed_target.query:
        target_path += f"?{parsed_target.query}"
    can_auto_login = bool(
        settings.MOODLE_AUTO_LOGIN_ENABLED
        and settings.MOODLE_SSO_SECRET
        and current_user.moodle_id
    )
    sso_url = None
    if can_auto_login:
        expires = int(time.time()) + 60
        payload = f"{int(current_user.moodle_id)}|{expires}|{target_path}"
        signature = hmac.new(
            settings.MOODLE_SSO_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        sso_url = app.main._build_moodle_public_url(
            f"/local/univessso/login.php?userid={int(current_user.moodle_id)}"
            f"&expires={expires}&target={quote(target_path, safe='')}&signature={signature}"
        )
    return {
        "enabled": bool(settings.MOODLE_BASE_URL),
        "can_auto_login": can_auto_login,
        "reason": None if can_auto_login else ("moodle_sync_failed" if sync_error else "auto_login_not_available"),
        "sync_error": sync_error,
        "url": base_target,
        "target_url": base_target,
        "sso_url": sso_url,
        "login_url": app.main._build_moodle_public_url("/login/index.php"),
        "moodle_username": credentials.get("moodle_username"),
        "username": credentials.get("moodle_username"),
        "password": None,
        "login_post_url": app.main._build_moodle_public_url("/login/index.php"),
    }


@router.get("/users/me/moodle-courses/{course_id}/contents", summary="Contenido de curso Moodle", tags=["Usuario"])
async def read_user_moodle_course_contents(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.moodle_id and settings.MOODLE_REST_TOKEN:
        user_courses = await moodle_client.get_user_courses(int(current_user.moodle_id))
        allowed_ids = {int(course.get("id")) for course in (user_courses or []) if course.get("id")}
        if int(course_id) not in allowed_ids:
            raise HTTPException(status_code=404, detail="Curso no encontrado para este alumno")
        contents = await moodle_client.get_course_contents(course_id)
        if contents is None:
            raise HTTPException(status_code=502, detail={"message": "No fue posible obtener modulos del curso en Moodle", "moodle_error": app.main._latest_moodle_error()})
        return {"course_id": course_id, "sections": contents}

    courses = await read_user_courses(current_user=current_user, db=db)
    course = next((item for item in courses if int(item.get("id") or 0) == int(course_id)), None)
    if not course:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    return {"course_id": course_id, "sections": [], "modules": [], "message": "Moodle no esta disponible en este entorno.", "course": course}


@router.get("/users/me/documents", summary="Mis documentos", tags=["Usuario"])
async def list_documents(current_user: models.User = Depends(auth.get_current_user)):
    upload_dir = f"{settings.UPLOAD_DIR}/{current_user.username}"
    if not os.path.exists(upload_dir):
        return []

    files = []
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        if os.path.isfile(file_path):
            stats = os.stat(file_path)
            files.append(
                {
                    "filename": filename,
                    "size": stats.st_size,
                    "date": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    return files


@router.get("/users/me/courses", summary="Mis cursos", tags=["Usuario"])
async def read_user_courses(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.carrera:
        app.main._assign_curriculum_to_student(db, current_user.id, current_user.carrera)
        db.commit()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == current_user.id)
        .all()
    )
    courses = []
    seen_grade_ids = set()

    for ce in course_enrollments:
        grade = app.main._get_grade_for_course_enrollment(ce)
        if grade:
            seen_grade_ids.add(grade.id)
        subject = ce.assignment.subject if ce.assignment and ce.assignment.subject else (grade.subject if grade else None)
        if not app.main._subject_is_virtual_classroom_enabled(subject):
            continue
        payload = app.main._serialize_course_card(ce, grade)
        payload["modality"] = subject.modality if subject else None
        courses.append(payload)

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == current_user.id).all()
    for g in legacy_grades:
        if g.id in seen_grade_ids:
            continue
        if not app.main._subject_is_virtual_classroom_enabled(g.subject):
            continue
        if g.assignment and g.assignment.teacher:
            professor_name = g.assignment.teacher.full_name or g.assignment.teacher.username
        else:
            professor_name = "Docente no asignado"
        courses.append(
            {
                "id": g.subject.id if g.subject else None,
                "name": g.subject.name if g.subject else None,
                "progress": 100 if g.status == models.GradeStatus.APROBADA else (40 if g.status == models.GradeStatus.CURSANDO else 0),
                "score": g.score if g.score is not None else 0,
                "professor": professor_name,
                "semester": g.subject.semester if g.subject else None,
                "credits": g.subject.credits if g.subject else None,
                "status": g.status,
                "moodle_course_id": g.subject.moodle_course_id if g.subject else None,
                "modality": g.subject.modality if g.subject else None,
            }
        )
    courses.sort(
        key=lambda item: (
            app.main._parse_semester_num(item.get("semester")),
            (item.get("name") or "").lower(),
            item.get("id") or 0,
        )
    )
    return courses


# ----------------------------
# Endpoints de docente
# ----------------------------


@router.get("/users/me/advisor/sessions", summary="Sesiones de asesoria del alumno", tags=["Usuario"])
def get_student_advisor_sessions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != models.UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Solo alumnos")
    sessions = (
        db.query(models.AdvisorySession)
        .filter(models.AdvisorySession.student_id == current_user.id)
        .order_by(models.AdvisorySession.scheduled_at.asc())
        .all()
    )
    result = []
    for s in sessions:
        teacher = db.query(models.User).filter(models.User.id == s.teacher_id).first()
        result.append({
            "id": s.id,
            "teacher_name": teacher.full_name if teacher else "-",
            "scheduled_at": s.scheduled_at.isoformat(),
            "duration_minutes": s.duration_minutes,
            "topic": s.topic,
            "notes": s.notes,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
        })
    return {"sessions": result}


