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

@router.get("/admin/subjects", response_model=list[schemas.Subject], summary="Listar materias", tags=["Administracion"])
def get_all_subjects(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Subject).all()


@router.post("/admin/subjects", response_model=schemas.Subject, summary="Crear materia", tags=["Administracion"])
async def create_subject(subject: schemas.SubjectCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    new_subject = models.Subject(
        name=subject.name,
        credits=subject.credits,
        semester=subject.semester,
        career=subject.career,
        modality=subject.modality,
    )
    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)
    
    if new_subject.modality and new_subject.modality.lower() in ["virtual", "hibrido", "híbrido"]:
        await app.main._sync_subject_to_moodle_internal(db, subject=new_subject, category_id=1)
        db.refresh(new_subject)

    return new_subject


@router.put("/admin/subjects/{subject_id}", response_model=schemas.SubjectWithTeacher, summary="Actualizar materia", tags=["Administracion"])
async def update_subject(subject_id: int, subject_update: schemas.SubjectUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not db_subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    if subject_update.name is not None:
        db_subject.name = subject_update.name
    if subject_update.credits is not None:
        db_subject.credits = subject_update.credits
    if subject_update.semester is not None:
        db_subject.semester = subject_update.semester
    if subject_update.career is not None:
        db_subject.career = subject_update.career
    if subject_update.modality is not None:
        db_subject.modality = subject_update.modality

    db.commit()
    
    if db_subject.modality and db_subject.modality.lower() in ["virtual", "hibrido", "híbrido"] and not db_subject.moodle_course_id:
        await app.main._sync_subject_to_moodle_internal(db, subject=db_subject, category_id=1)

    teacher = None
    assignment = None
    if subject_update.teacher_username is not None:
        teacher = db.query(models.User).filter(
            models.User.username == subject_update.teacher_username,
            models.User.role == models.UserRole.TEACHER,
        ).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Docente no encontrado")

        active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
        cycle_id = active_cycle.id if active_cycle else None
        assignment = db.query(models.SubjectAssignment).filter(
            models.SubjectAssignment.subject_id == db_subject.id,
            models.SubjectAssignment.cycle_id == cycle_id,
        ).first()
        if assignment:
            assignment.teacher_id = teacher.id
        else:
            assignment = models.SubjectAssignment(
                subject_id=db_subject.id,
                teacher_id=teacher.id,
                cycle_id=cycle_id,
            )
            db.add(assignment)

    db.commit()
    db.refresh(db_subject)
    return {
        "id": db_subject.id,
        "name": db_subject.name,
        "credits": db_subject.credits,
        "semester": db_subject.semester,
        "career": db_subject.career,
        "teacher_id": assignment.teacher_id if assignment else None,
        "teacher_username": teacher.username if teacher else None,
    }


# ----------------------------
# Asignaciones de docente a materia por ciclo
# ----------------------------


@router.get("/admin/subject-assignments", summary="Listar asignaciones", tags=["Administracion"])
def get_subject_assignments(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Lista asignaciones. Si cycle_id es None devuelve las del ciclo activo."""
    query = db.query(models.SubjectAssignment)
    if cycle_id:
        query = query.filter(models.SubjectAssignment.cycle_id == cycle_id)
    else:
        active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
        if active_cycle:
            query = query.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    assignments = query.all()
    from fastapi.encoders import jsonable_encoder as _je
    result = []
    for a in assignments:
        student_count = len({
            ce.student_enrollment.student_id
            for ce in a.course_enrollments
            if ce.student_enrollment and ce.student_enrollment.student_id
        })
        item = app.main._je(schemas.SubjectAssignment.model_validate(a))
        item["student_count"] = student_count
        item["group_name"] = a.group.name if a.group else None
        result.append(item)
    return result


@router.post("/admin/subject-assignments", response_model=schemas.SubjectAssignment, summary="Asignar docente a materia", tags=["Administracion"])
def create_subject_assignment(
    data: schemas.SubjectAssignmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    subject = db.query(models.Subject).filter(models.Subject.id == data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    teacher = db.query(models.User).filter(
        models.User.username == data.teacher_username,
        models.User.role == models.UserRole.TEACHER,
    ).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    cycle_id = data.cycle_id
    if not cycle_id:
        active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
        cycle_id = active_cycle.id if active_cycle else None
    if data.group_id is None:
        raise HTTPException(status_code=400, detail="Debes seleccionar un grupo para la asignación")

    group = db.query(models.Group).filter(models.Group.id == data.group_id, models.Group.is_active == True).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    # Verificar duplicado
    existing = db.query(models.SubjectAssignment).filter(
        models.SubjectAssignment.subject_id == data.subject_id,
        models.SubjectAssignment.teacher_id == teacher.id,
        models.SubjectAssignment.cycle_id == cycle_id,
        models.SubjectAssignment.group_id == data.group_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Este docente ya tiene esta materia asignada para ese grupo en el ciclo indicado")

    assignment = models.SubjectAssignment(
        subject_id=data.subject_id,
        teacher_id=teacher.id,
        cycle_id=cycle_id,
        group_id=group.id,
    )
    db.add(assignment)
    db.flush()  # Obtener el ID sin hacer commit todavía

    # Auto-vincular alumnos que tengan esta materia sin docente asignado (assignment_id IS NULL)
    # Solo se vinculan los que aún no tienen asignación → son los que no pertenecen a ninguna sección
    unlinked_grades = (
        db.query(models.Grade)
        .filter(
            models.Grade.subject_id == data.subject_id,
            models.Grade.assignment_id.is_(None),
            models.Grade.attempt_type == models.AttemptType.REGULAR,
        )
        .all()
    )
    linked_count = 0
    for grade in unlinked_grades:
        active_enrollment = app.main._get_active_student_enrollment(db, grade.student_id) if grade.student_id else None
        if assignment.group_id:
            if not active_enrollment or active_enrollment.group_id != assignment.group_id:
                continue
        grade.assignment_id = assignment.id
        if grade.student:
            grade.course_enrollment_id = app.main._get_or_create_course_enrollment(
                db,
                student=grade.student,
                assignment=assignment,
                attempt_type=grade.attempt_type,
                status=grade.status,
            ).id
        linked_count += 1

    db.commit()
    db.refresh(assignment)

    # Devolver el assignment con metadato de alumnos vinculados (usando JSONResponse para incluirlo)
    from fastapi.responses import JSONResponse as _JSONResponse
    from fastapi.encoders import jsonable_encoder as _jsonable_encoder

    data = app.main._jsonable_encoder(assignment)
    data["auto_linked"] = linked_count
    return app.main._JSONResponse(content=data)


@router.put("/admin/subject-assignments/{assignment_id}", summary="Cambiar docente de asignación", tags=["Administracion"])
def update_subject_assignment(
    assignment_id: int,
    data: schemas.SubjectAssignmentUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if data.teacher_username is not None:
        teacher = db.query(models.User).filter(
            models.User.username == data.teacher_username,
            models.User.role == models.UserRole.TEACHER,
        ).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Docente no encontrado")
        existing = db.query(models.SubjectAssignment).filter(
            models.SubjectAssignment.subject_id == assignment.subject_id,
            models.SubjectAssignment.teacher_id == teacher.id,
            models.SubjectAssignment.cycle_id == assignment.cycle_id,
            models.SubjectAssignment.group_id == (data.group_id if data.group_id is not None else assignment.group_id),
            models.SubjectAssignment.id != assignment_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Este docente ya tiene esta materia asignada para ese grupo en el ciclo")
        db.query(models.Grade).filter(models.Grade.assignment_id == assignment_id).update(
            {"assignment_id": assignment_id}, synchronize_session=False
        )
        assignment.teacher_id = teacher.id
    if data.group_id is not None:
        group = db.query(models.Group).filter(models.Group.id == data.group_id, models.Group.is_active == True).first()
        if not group:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")
        duplicate = db.query(models.SubjectAssignment).filter(
            models.SubjectAssignment.subject_id == assignment.subject_id,
            models.SubjectAssignment.teacher_id == assignment.teacher_id,
            models.SubjectAssignment.cycle_id == assignment.cycle_id,
            models.SubjectAssignment.group_id == group.id,
            models.SubjectAssignment.id != assignment_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Ya existe una asignación igual para ese grupo")
        assignment.group_id = group.id
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/admin/subject-assignments/{assignment_id}", summary="Eliminar asignación", tags=["Administracion"])
def delete_subject_assignment(
    assignment_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    db.delete(assignment)
    db.commit()
    return {"detail": "Asignación eliminada"}


@router.post("/admin/subjects/{subject_id}/moodle-sync", summary="Sincronizar materia con Moodle", tags=["Administracion"])
async def sync_subject_moodle(subject_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not db_subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")
    result = await app.main._sync_subject_to_moodle_internal(db, subject=db_subject, category_id=1)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail={"message": result.get("message") or "No fue posible sincronizar la materia con Moodle", "moodle_error": result.get("moodle_error") or app.main._latest_moodle_error(), "evidence": result.get("evidence")})
    return result


