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

@router.get("/admin/payments", response_model=list[schemas.PaymentListItem], summary="Listar pagos", tags=["Administracion"])
def get_all_payments(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    payments = (
        db.query(
            models.Payment.id,
            models.Payment.student_id,
            models.Payment.charge_id,
            models.Payment.concept,
            models.Payment.amount,
            models.Payment.due_date,
            models.Payment.status,
            models.User.username.label("student_username"),
            models.User.full_name.label("student_full_name"),
        )
        .join(models.User, models.User.id == models.Payment.student_id)
        .order_by(models.Payment.id.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "student_id": row.student_id,
            "charge_id": row.charge_id,
            "concept": row.concept,
            "amount": row.amount,
            "due_date": row.due_date,
            "status": row.status,
            "student": {
                "username": row.student_username,
                "full_name": row.student_full_name,
            },
        }
        for row in payments
    ]


@router.get("/admin/charges", response_model=list[schemas.ChargeListItem], summary="Listar cargos", tags=["Administracion"])
def get_all_charges(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    charges = (
        db.query(
            models.Charge.id,
            models.Charge.student_id,
            models.Charge.student_enrollment_id,
            models.StudentEnrollment.cycle_id.label("cycle_id"),
            models.SchoolCycle.period.label("cycle_period"),
            models.Charge.charge_type,
            models.Charge.concept,
            models.Charge.period_label,
            models.Charge.amount,
            models.Charge.due_date,
            models.Charge.status,
            models.Charge.created_at,
            models.User.username.label("student_username"),
            models.User.full_name.label("student_full_name"),
        )
        .join(models.User, models.User.id == models.Charge.student_id)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
        .outerjoin(models.SchoolCycle, models.SchoolCycle.id == models.StudentEnrollment.cycle_id)
        .order_by(models.Charge.id.desc())
    )
    if cycle_id:
        charges = charges.filter(models.StudentEnrollment.cycle_id == cycle_id)
    charges = charges.all()
    return [
        {
            "id": row.id,
            "student_id": row.student_id,
            "student_enrollment_id": row.student_enrollment_id,
            "cycle_id": row.cycle_id,
            "cycle_period": row.cycle_period,
            "charge_type": row.charge_type,
            "concept": row.concept,
            "period_label": row.period_label,
            "amount": row.amount,
            "due_date": row.due_date,
            "status": row.status,
            "created_at": row.created_at,
            "student": {
                "username": row.student_username,
                "full_name": row.student_full_name,
            },
        }
        for row in charges
    ]


@router.post("/admin/charges", response_model=schemas.ChargeWithStudent, summary="Crear cargo", tags=["Administracion"])
def create_charge(charge: schemas.ChargeCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(models.User.username == charge.student_username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    enrollment = app.main._get_student_enrollment_for_charge(
        db,
        student=student,
        cycle_id=charge.cycle_id,
        student_enrollment_id=charge.student_enrollment_id,
    )

    app.main._ensure_unique_charge_for_enrollment_period(
        db,
        student_enrollment_id=enrollment.id if enrollment else None,
        concept=charge.concept,
        period_label=charge.period_label,
    )

    new_charge = models.Charge(
        student_id=student.id,
        student_enrollment_id=enrollment.id if enrollment else None,
        charge_type=charge.charge_type,
        concept=charge.concept,
        period_label=charge.period_label,
        amount=charge.amount,
        due_date=charge.due_date,
        status=charge.status,
    )
    db.add(new_charge)
    db.flush()
    app.main._ensure_payment_for_charge(db, new_charge)
    db.commit()
    db.refresh(new_charge)
    return new_charge


@router.put("/admin/charges/{charge_id}", response_model=schemas.Charge, summary="Actualizar cargo", tags=["Administracion"])
def update_charge(charge_id: int, charge_update: schemas.ChargeUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_charge = db.query(models.Charge).filter(models.Charge.id == charge_id).first()
    if not db_charge:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")

    next_concept = charge_update.concept if charge_update.concept is not None else db_charge.concept
    next_period_label = charge_update.period_label if charge_update.period_label is not None else db_charge.period_label
    app.main._ensure_unique_charge_for_enrollment_period(
        db,
        student_enrollment_id=db_charge.student_enrollment_id,
        concept=next_concept,
        period_label=next_period_label,
        current_charge_id=db_charge.id,
    )

    if charge_update.charge_type is not None:
        db_charge.charge_type = charge_update.charge_type
    if charge_update.concept is not None:
        db_charge.concept = charge_update.concept
    if charge_update.period_label is not None:
        db_charge.period_label = charge_update.period_label
    if charge_update.amount is not None:
        db_charge.amount = charge_update.amount
    if charge_update.due_date is not None:
        db_charge.due_date = charge_update.due_date
    if charge_update.status is not None:
        db_charge.status = charge_update.status

    app.main._ensure_payment_for_charge(db, db_charge)
    db.commit()
    db.refresh(db_charge)
    return db_charge


@router.delete("/admin/charges/{charge_id}", tags=["Administracion"], summary="Eliminar cargo")
def delete_charge(charge_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_charge = db.query(models.Charge).filter(models.Charge.id == charge_id).first()
    if not db_charge:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")
    try:
        db.query(models.Payment).filter(models.Payment.charge_id == db_charge.id).delete(synchronize_session=False)
        db.delete(db_charge)
        db.commit()
        return {"ok": True, "deleted_charge_id": charge_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo eliminar el cargo: {exc}")


@router.post("/admin/payments", response_model=schemas.PaymentWithStudent, summary="Crear pago", tags=["Administracion"])
def create_payment(payment: schemas.PaymentCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_student = db.query(models.User).filter(models.User.username == payment.student_username).first()
    if not db_student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    new_payment = models.Payment(
        student_id=db_student.id,
        concept=payment.concept,
        amount=payment.amount,
        due_date=payment.due_date,
        status=payment.status,
    )
    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)
    return new_payment


@router.put("/admin/payments/{payment_id}", response_model=schemas.Payment, summary="Actualizar pago", tags=["Administracion"])
def update_payment(payment_id: int, payment_update: schemas.PaymentUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not db_payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    if payment_update.concept is not None:
        db_payment.concept = payment_update.concept
    if payment_update.amount is not None:
        db_payment.amount = payment_update.amount
    if payment_update.due_date is not None:
        db_payment.due_date = payment_update.due_date
    if payment_update.status is not None:
        db_payment.status = payment_update.status
        if db_payment.charge:
            db_payment.charge.status = payment_update.status

    db.commit()
    db.refresh(db_payment)
    return db_payment


