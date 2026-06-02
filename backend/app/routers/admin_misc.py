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

@router.put("/admin/group-actions/bulk-enrollment", summary="Cambiar inscripción de todo un grupo", tags=["Administracion"])
def bulk_update_group_enrollment(body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    grupo = body.get("grupo", "").strip()
    carrera = body.get("carrera", "").strip()
    enrollment_status = body.get("enrollment_status", "").strip()
    usernames = body.get("usernames")  # Opcional: lista de matrículas específicas

    if not grupo or not enrollment_status:
        raise HTTPException(status_code=400, detail="Faltan grupo o enrollment_status")

    valid = [e.value for e in models.EnrollmentStatus]
    if enrollment_status not in valid:
        raise HTTPException(status_code=400, detail=f"Estatus inválido. Opciones: {valid}")

    enrollments, active_cycle = app.main._get_group_member_enrollments(
        db,
        group_name=grupo,
        career_name=carrera or None,
        usernames=usernames,
    )
    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        student.enrollment_status = enrollment_status
        app.main._ensure_single_active_enrollment_per_cycle(
            db,
            student_id=student.id,
            cycle_id=active_cycle.id,
            current_enrollment_id=enrollment.id,
            enrollment_status=models.EnrollmentStatus(enrollment_status),
        )
        enrollment.enrollment_status = enrollment_status
        enrollment.is_active = app.main._is_active_enrollment_status(models.EnrollmentStatus(enrollment_status))
    db.commit()
    return {"updated": len(enrollments), "enrollment_status": enrollment_status}


@router.post("/admin/group-actions/bulk-assign", summary="Asignar materia a todo un grupo", tags=["Administracion"])
def bulk_assign_group_subject(body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    grupo = body.get("grupo", "").strip()
    carrera = body.get("carrera", "").strip()
    assignment_id = body.get("assignment_id")
    usernames = body.get("usernames")  # Opcional: lista específica

    if not grupo or not assignment_id:
        raise HTTPException(status_code=400, detail="Faltan grupo o assignment_id")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if assignment.group and assignment.group.name != grupo:
        raise HTTPException(status_code=400, detail=f"La asignación pertenece al grupo {assignment.group.name}. Selecciona el mismo grupo para evitar mezclar calificaciones")

    enrollments, _ = app.main._get_group_member_enrollments(
        db,
        group_name=grupo,
        career_name=carrera or None,
        usernames=usernames,
    )
    enrolled = 0
    reassigned = 0

    for enrollment in enrollments:
        student = enrollment.student
        if not student:
            continue
        # Ya en esta asignación exacta → skip
        already = db.query(models.Grade).filter(
            models.Grade.student_id == student.id,
            models.Grade.assignment_id == assignment_id,
            models.Grade.attempt_type == models.AttemptType.REGULAR,
        ).first()
        if already:
            continue

        # Tiene grade para la misma materia → reasignar
        existing = db.query(models.Grade).filter(
            models.Grade.student_id == student.id,
            models.Grade.subject_id == assignment.subject_id,
            models.Grade.attempt_type == models.AttemptType.REGULAR,
        ).first()
        if existing:
            course_enrollment = app.main._get_or_create_course_enrollment(
                db,
                student=student,
                assignment=assignment,
                attempt_type=models.AttemptType.REGULAR,
                status=models.GradeStatus.CURSANDO,
            )
            existing.assignment_id = assignment.id
            existing.course_enrollment_id = course_enrollment.id
            existing.status = models.GradeStatus.CURSANDO
            reassigned += 1
        else:
            db.add(models.Grade(
                student_id=student.id,
                subject_id=assignment.subject_id,
                assignment_id=assignment.id,
                course_enrollment_id=app.main._get_or_create_course_enrollment(
                    db,
                    student=student,
                    assignment=assignment,
                    attempt_type=models.AttemptType.REGULAR,
                    status=models.GradeStatus.CURSANDO,
                ).id,
                attempt_type=models.AttemptType.REGULAR,
                status=models.GradeStatus.CURSANDO,
            ))
            enrolled += 1

    db.commit()
    return {"enrolled": enrolled, "reassigned": reassigned, "total": enrolled + reassigned}


@router.put("/admin/grades/{grade_id}", response_model=schemas.Grade, summary="Actualizar calificacion (admin)", tags=["Administracion"])
def update_grade(grade_id: int, grade_update: schemas.GradeUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")

    app.main._apply_grade_payload(db_grade, grade_update)

    db.commit()
    db.refresh(db_grade)
    return db_grade


