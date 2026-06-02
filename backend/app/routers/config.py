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

@router.get("/admin/school-cycle", response_model=Optional[schemas.SchoolCycle], tags=["Configuracion"])
def get_active_school_cycle(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).order_by(models.SchoolCycle.id.desc()).first()


@router.post("/admin/school-cycle", response_model=schemas.SchoolCycle, tags=["Configuracion"])
def save_school_cycle(cycle: schemas.SchoolCycleCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    if not (cycle.period or "").strip():
        raise HTTPException(status_code=400, detail="El periodo del ciclo es obligatorio")
    if cycle.start_date >= cycle.end_date:
        raise HTTPException(status_code=400, detail="La fecha de inicio debe ser anterior a la fecha de fin")
    if not cycle.tuitions:
        raise HTTPException(status_code=400, detail="Debes capturar al menos un costo por carrera y modalidad")

    seen_pairs: set[tuple[int, int]] = set()
    for tuition in cycle.tuitions:
        key = (tuition.career_id, tuition.modality_id)
        if key in seen_pairs:
            raise HTTPException(status_code=400, detail="Hay costos duplicados para la misma carrera y modalidad")
        seen_pairs.add(key)

    try:
        db.query(models.SchoolCycle).update({"is_active": False})
        new_cycle = models.SchoolCycle(
            period=cycle.period.strip(),
            start_date=cycle.start_date,
            end_date=cycle.end_date,
            monthly_amount=cycle.monthly_amount,
            is_active=True,
        )
        db.add(new_cycle)
        db.flush()
        for t in cycle.tuitions:
            db.add(models.CycleTuition(
                cycle_id=new_cycle.id,
                career_id=t.career_id,
                modality_id=t.modality_id,
                amount=t.amount,
            ))
        db.commit()
        db.refresh(new_cycle)
        return new_cycle
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo guardar el ciclo escolar: {exc}")


@router.post("/admin/school-cycle/generate-payments", response_model=schemas.SchoolCyclePaymentResult, tags=["Configuracion"])
def generate_cycle_payments(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    import calendar
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).order_by(models.SchoolCycle.id.desc()).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="No hay ciclo escolar activo")

    # Generate monthly payment dates between start and end
    months = []
    current = cycle.start_date.replace(day=1)
    end = cycle.end_date
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        due = current.replace(day=min(15, last_day))
        month_name = due.strftime("%B %Y").capitalize()
        months.append({"month": month_name, "due_date": due})
        # Advance to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    # Tuition lookup: (career_id, modality_id) -> amount
    tuition_map = {(t.career_id, t.modality_id): t.amount for t in cycle.tuitions}

    payments_created = 0
    students_affected = set()
    enrollments = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.cycle_id == cycle.id,
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
            models.StudentEnrollment.is_active == True,
        )
        .all()
    )

    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        for month_info in months:
            concept = f"Colegiatura {month_info['month']}"
            existing_charge = db.query(models.Charge).filter(
                models.Charge.student_enrollment_id == enrollment.id,
                models.Charge.concept == concept,
            ).first()
            if existing_charge:
                continue
            # Amount: prefer per career+modality, fallback to cycle default
            amount = tuition_map.get(
                (enrollment.career_id or student.career_id, enrollment.modality_id or student.modality_id),
                cycle.monthly_amount or 0
            )
            if amount <= 0:
                continue
            due_date = datetime(
                month_info["due_date"].year,
                month_info["due_date"].month,
                month_info["due_date"].day,
                23, 59, 59,
            )
            charge = models.Charge(
                student_id=student.id,
                student_enrollment_id=enrollment.id,
                charge_type=models.ChargeType.TUITION,
                concept=concept,
                period_label=month_info["month"],
                amount=amount,
                due_date=due_date,
                status=models.PaymentStatus.PENDIENTE,
            )
            db.add(charge)
            db.flush()
            app.main._ensure_payment_for_charge(db, charge)
            payments_created += 1
            students_affected.add(student.id)

    db.commit()
    return {
        "payments_created": payments_created,
        "students_affected": len(students_affected),
        "months": [m["month"] for m in months],
    }


@router.post("/admin/school-cycles/{cycle_id}/recalculate-charges", tags=["Configuracion"])
def recalculate_cycle_charges(
    cycle_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    import calendar

    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")

    months = []
    current = cycle.start_date.replace(day=1)
    end = cycle.end_date
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        due = current.replace(day=min(15, last_day))
        month_name = due.strftime("%B %Y").capitalize()
        months.append({"month": month_name, "due_date": due})
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    tuition_map = {(t.career_id, t.modality_id): t.amount for t in cycle.tuitions}
    enrollments = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.cycle_id == cycle.id,
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
            models.StudentEnrollment.is_active == True,
        )
        .all()
    )

    updated_count = 0
    created_count = 0
    students_affected = set()

    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        target_amount = tuition_map.get(
            (enrollment.career_id or student.career_id, enrollment.modality_id or student.modality_id),
            cycle.monthly_amount or 0,
        )
        if target_amount <= 0:
            continue

        for month_info in months:
            concept = f"Colegiatura {month_info['month']}"
            due_date = datetime(
                month_info["due_date"].year,
                month_info["due_date"].month,
                month_info["due_date"].day,
                23, 59, 59,
            )
            existing_charge = (
                db.query(models.Charge)
                .filter(
                    models.Charge.student_enrollment_id == enrollment.id,
                    models.Charge.concept == concept,
                    models.Charge.period_label == month_info["month"],
                    models.Charge.charge_type == models.ChargeType.TUITION,
                )
                .first()
            )
            if existing_charge:
                if existing_charge.status != models.PaymentStatus.PAGADO and (
                    float(existing_charge.amount or 0) != float(target_amount)
                    or existing_charge.due_date != due_date
                ):
                    existing_charge.amount = target_amount
                    existing_charge.due_date = due_date
                    app.main._ensure_payment_for_charge(db, existing_charge)
                    updated_count += 1
                    students_affected.add(student.id)
                continue

            charge = models.Charge(
                student_id=student.id,
                student_enrollment_id=enrollment.id,
                charge_type=models.ChargeType.TUITION,
                concept=concept,
                period_label=month_info["month"],
                amount=target_amount,
                due_date=due_date,
                status=models.PaymentStatus.PENDIENTE,
            )
            db.add(charge)
            db.flush()
            app.main._ensure_payment_for_charge(db, charge)
            created_count += 1
            students_affected.add(student.id)

    db.commit()
    return {
        "ok": True,
        "cycle_id": cycle.id,
        "cycle_period": cycle.period,
        "created_count": created_count,
        "updated_count": updated_count,
        "students_affected": len(students_affected),
        "months": [m["month"] for m in months],
    }


@router.get("/admin/school-cycles/all", summary="Todos los ciclos escolares", tags=["Configuracion"])
def get_all_school_cycles(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    cycles = db.query(models.SchoolCycle).order_by(models.SchoolCycle.id.desc()).all()
    result = []
    for c in cycles:
        payment_count = db.query(models.Payment).filter(
            models.Payment.concept.like(f"%{c.period}%") if c.period else False
        ).count() if c.period else 0
        charges = (
            db.query(models.Charge)
            .join(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
            .filter(models.StudentEnrollment.cycle_id == c.id)
            .all()
        )
        total_amount = sum(float(charge.amount or 0) for charge in charges)
        pending_amount = sum(float(charge.amount or 0) for charge in charges if charge.status == models.PaymentStatus.PENDIENTE)
        paid_amount = sum(float(charge.amount or 0) for charge in charges if charge.status == models.PaymentStatus.PAGADO)
        students_affected = len({charge.student_id for charge in charges if charge.student_id})
        result.append({
            "id": c.id,
            "period": c.period,
            "start_date": str(c.start_date)[:10] if c.start_date else None,
            "end_date": str(c.end_date)[:10] if c.end_date else None,
            "is_active": c.is_active,
            "monthly_amount": c.monthly_amount,
            "payment_count": payment_count,
            "total_amount": total_amount,
            "pending_amount": pending_amount,
            "paid_amount": paid_amount,
            "students_affected": students_affected,
        })
    return result


@router.get("/admin/school-cycles/{cycle_id}", response_model=schemas.SchoolCycle, summary="Detalle de ciclo escolar", tags=["Configuracion"])
def get_school_cycle_detail(cycle_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")
    return cycle


@router.put("/admin/school-cycles/{cycle_id}", response_model=schemas.SchoolCycle, summary="Actualizar ciclo escolar", tags=["Configuracion"])
def update_school_cycle(
    cycle_id: int,
    payload: schemas.SchoolCycleCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")
    if not (payload.period or "").strip():
        raise HTTPException(status_code=400, detail="El periodo del ciclo es obligatorio")
    if payload.start_date >= payload.end_date:
        raise HTTPException(status_code=400, detail="La fecha de inicio debe ser anterior a la fecha de fin")
    if not payload.tuitions:
        raise HTTPException(status_code=400, detail="Debes capturar al menos un costo por carrera y modalidad")

    seen_pairs: set[tuple[int, int]] = set()
    for tuition in payload.tuitions:
        key = (tuition.career_id, tuition.modality_id)
        if key in seen_pairs:
            raise HTTPException(status_code=400, detail="Hay costos duplicados para la misma carrera y modalidad")
        seen_pairs.add(key)

    try:
        cycle.period = payload.period.strip()
        cycle.start_date = payload.start_date
        cycle.end_date = payload.end_date
        cycle.monthly_amount = payload.monthly_amount

        db.query(models.CycleTuition).filter(models.CycleTuition.cycle_id == cycle.id).delete()
        db.flush()
        for tuition in payload.tuitions:
            db.add(models.CycleTuition(
                cycle_id=cycle.id,
                career_id=tuition.career_id,
                modality_id=tuition.modality_id,
                amount=tuition.amount,
            ))
        db.commit()
        db.refresh(cycle)
        return cycle
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo actualizar el ciclo escolar: {exc}")


@router.delete("/admin/school-cycles/{cycle_id}", tags=["Configuracion"], summary="Eliminar ciclo escolar")
def delete_school_cycle(
    cycle_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")

    try:
        enrollment_ids = [
            row.id for row in db.query(models.StudentEnrollment.id)
            .filter(models.StudentEnrollment.cycle_id == cycle.id)
            .all()
        ]
        charge_ids = []
        if enrollment_ids:
            charge_ids = [
                row.id for row in db.query(models.Charge.id)
                .filter(models.Charge.student_enrollment_id.in_(enrollment_ids))
                .all()
            ]

        if charge_ids:
            db.query(models.Payment).filter(models.Payment.charge_id.in_(charge_ids)).delete(synchronize_session=False)
            db.query(models.Charge).filter(models.Charge.id.in_(charge_ids)).delete(synchronize_session=False)

        db.query(models.SubjectAssignment).filter(models.SubjectAssignment.cycle_id == cycle.id).update(
            {"cycle_id": None},
            synchronize_session=False,
        )
        db.query(models.StudentEnrollment).filter(models.StudentEnrollment.cycle_id == cycle.id).delete(synchronize_session=False)
        db.query(models.CycleTuition).filter(models.CycleTuition.cycle_id == cycle.id).delete(synchronize_session=False)
        was_active = bool(cycle.is_active)
        cycle_period = cycle.period
        db.delete(cycle)
        db.flush()

        if was_active:
            replacement_cycle = (
                db.query(models.SchoolCycle)
                .filter(models.SchoolCycle.id != cycle_id)
                .order_by(models.SchoolCycle.id.desc())
                .first()
            )
            if replacement_cycle:
                replacement_cycle.is_active = True

        db.commit()
        return {"ok": True, "deleted_cycle_id": cycle_id, "deleted_cycle_period": cycle_period}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo eliminar el ciclo escolar: {exc}")


@router.patch("/admin/school-cycles/{cycle_id}/set-active", response_model=schemas.SchoolCycle, summary="Activar ciclo escolar", tags=["Configuracion"])
def set_active_school_cycle(
    cycle_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Ciclo escolar no encontrado")
    db.query(models.SchoolCycle).update({"is_active": False})
    cycle.is_active = True
    db.commit()
    db.refresh(cycle)
    return cycle


