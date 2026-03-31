from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import DefaultDict, Deque, List, Optional
from pathlib import Path
import json
import logging
import os
import time
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, Request, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session, aliased

from . import models, schemas, auth
from .curriculum import ensure_subjects_for_career, get_public_curriculum
from .database import get_db
from .config import settings

# Intentos de login por IP en memoria para rate limiting simple
_login_attempts: DefaultDict[str, Deque[datetime]] = defaultdict(deque)


def _enforce_login_rate_limit(client_ip: str) -> None:
    """Bloquea el login si se excede el numero de intentos en la ventana configurada."""
    if not client_ip:
        client_ip = "unknown"
    window_start = datetime.utcnow() - timedelta(seconds=settings.LOGIN_RATE_WINDOW_SECONDS)
    attempts = _login_attempts[client_ip]
    while attempts and attempts[0] < window_start:
        attempts.popleft()
    if len(attempts) >= settings.LOGIN_RATE_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de login. Intenta mas tarde.",
        )
    attempts.append(datetime.utcnow())


def _reset_login_attempts(client_ip: str) -> None:
    if not client_ip:
        client_ip = "unknown"
    _login_attempts.pop(client_ip, None)


def _get_client_ip(request: Request) -> str:
    """Obtiene IP real contemplando cabeceras de proxy."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _validate_upload_file(
    file: UploadFile,
    *,
    max_size_bytes: Optional[int] = None,
    allowed_types: Optional[List[str]] = None,
) -> None:
    """Valida tipo MIME y peso de archivos subidos."""
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo requerido")
    allowed = allowed_types or settings.ALLOWED_UPLOAD_TYPES
    limit = max_size_bytes or settings.max_upload_size_bytes
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Tipo de archivo no permitido",
        )
    file.file.seek(0, os.SEEK_END)
    size_bytes = file.file.tell()
    file.file.seek(0)
    if size_bytes > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo supera el limite de {limit // (1024 * 1024)}MB",
        )


def _validate_csv_upload(file: UploadFile) -> None:
    _validate_upload_file(
        file,
        max_size_bytes=settings.max_csv_size_bytes,
        allowed_types=["text/csv", "application/vnd.ms-excel"],
    )


def _service_attachment_absolute_path(relative_path: Optional[str]) -> Optional[Path]:
    if not relative_path:
        return None
    return (Path(settings.UPLOAD_DIR) / relative_path).resolve()


def _store_service_attachment(*, student_username: str, file: UploadFile) -> tuple[str, str]:
    _validate_upload_file(file)
    safe_name = Path(file.filename or "documento").name
    relative_dir = Path(student_username) / "services"
    absolute_dir = Path(settings.UPLOAD_DIR) / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}_{safe_name}"
    absolute_path = absolute_dir / stored_name
    with absolute_path.open("wb") as buffer:
        buffer.write(file.file.read())
    return safe_name, str(relative_dir / stored_name)


import re as _re

def _parse_semester_num(semester_str: Optional[str]) -> int:
    """Extrae el numero de semestre de strings como '1er Semestre', '2do Semestre', etc."""
    if not semester_str:
        return 0
    m = _re.search(r'\d+', str(semester_str))
    return int(m.group()) if m else 0


def _subject_order_key(subject: models.Subject) -> tuple[int, int]:
    return (_parse_semester_num(subject.semester), subject.id or 0)


def _grade_status_for_semester(subject_sem: int, student_sem: int) -> "models.GradeStatus":
    """Determina el estatus inicial de una calificacion segun el cuatrimestre."""
    if student_sem == 0 or subject_sem == 0:
        return models.GradeStatus.CURSANDO
    if subject_sem < student_sem:
        return models.GradeStatus.REPROBADA
    if subject_sem == student_sem:
        return models.GradeStatus.CURSANDO
    return models.GradeStatus.PROXIMAMENTE


def _assign_curriculum_to_student(db: Session, student_id: int, career_name: Optional[str]) -> None:
    """Crea calificaciones para todas las materias de la carrera con estatus segun cuatrimestre.

    - Semestres anteriores al del alumno  → Reprobada  (admin puede editar)
    - Semestre actual del alumno          → Cursando
    - Semestres posteriores               → Proximamente
    """
    if not career_name:
        return

    ensure_subjects_for_career(db, career_name)
    subjects = (
        db.query(models.Subject)
        .filter(models.Subject.career == career_name)
        .order_by(models.Subject.semester.asc(), models.Subject.id.asc())
        .all()
    )
    if not subjects:
        return

    # Semestre actual del alumno (para asignar estatus correcto)
    student = db.query(models.User).filter(models.User.id == student_id).first()
    student_sem = _parse_semester_num(student.semestre if student else None)

    active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()

    # IDs de materias en las que el alumno ya tiene un registro (evita duplicados)
    existing_subject_ids = {
        grade.subject_id
        for grade in db.query(models.Grade).filter(
            models.Grade.student_id == student_id,
        ).all()
    }

    if active_cycle:
        # Asignaciones existentes del ciclo activo para las materias de esta carrera
        assignments = (
            db.query(models.SubjectAssignment)
            .join(models.Subject)
            .filter(
                models.Subject.career == career_name,
                models.SubjectAssignment.cycle_id == active_cycle.id,
            )
            .all()
        )

        existing_assignment_ids = {
            g.assignment_id
            for g in db.query(models.Grade).filter(
                models.Grade.student_id == student_id,
                models.Grade.assignment_id.isnot(None),
            ).all()
        }

        # Materias con asignación → usar estatus por cuatrimestre
        assigned_subject_ids = set()
        for assignment in assignments:
            if assignment.id in existing_assignment_ids:
                assigned_subject_ids.add(assignment.subject_id)
                continue
            subject_sem = _parse_semester_num(assignment.subject.semester if assignment.subject else None)
            status = _grade_status_for_semester(subject_sem, student_sem)
            db.add(
                models.Grade(
                    student_id=student_id,
                    subject_id=assignment.subject_id,
                    assignment_id=assignment.id,
                    attempt_type=models.AttemptType.REGULAR,
                    score=None,
                    status=status,
                )
            )
            assigned_subject_ids.add(assignment.subject_id)

        # Materias sin asignación → crear grade sin assignment_id con estatus por cuatrimestre
        for subject in subjects:
            if subject.id in existing_subject_ids or subject.id in assigned_subject_ids:
                continue
            subject_sem = _parse_semester_num(subject.semester)
            status = _grade_status_for_semester(subject_sem, student_sem)
            db.add(
                models.Grade(
                    student_id=student_id,
                    subject_id=subject.id,
                    attempt_type=models.AttemptType.REGULAR,
                    score=None,
                    status=status,
                )
            )
    else:
        # Sin ciclo activo: inscribir todas las materias con estatus por cuatrimestre
        for subject in subjects:
            if subject.id in existing_subject_ids:
                continue
            subject_sem = _parse_semester_num(subject.semester)
            status = _grade_status_for_semester(subject_sem, student_sem)
            db.add(
                models.Grade(
                    student_id=student_id,
                    subject_id=subject.id,
                    attempt_type=models.AttemptType.REGULAR,
                    score=None,
                    status=status,
                )
            )


def _get_active_cycle(db: Session) -> Optional[models.SchoolCycle]:
    return db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).order_by(models.SchoolCycle.id.desc()).first()


def _has_enrollment_seed_data(student: models.User) -> bool:
    return any([
        student.career_id,
        student.carrera,
        student.modality_id,
        student.modalidad,
        student.semestre,
        student.grupo,
        student.enrollment_status != models.EnrollmentStatus.NO_INSCRITO,
    ])


def _is_active_enrollment_status(enrollment_status: models.EnrollmentStatus) -> bool:
    return enrollment_status == models.EnrollmentStatus.INSCRITO


def _ensure_single_active_enrollment_per_cycle(
    db: Session,
    *,
    student_id: int,
    cycle_id: int,
    current_enrollment_id: Optional[int] = None,
    enrollment_status: models.EnrollmentStatus,
) -> None:
    if not _is_active_enrollment_status(enrollment_status):
        return

    active_enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student_id,
            models.StudentEnrollment.cycle_id == cycle_id,
            models.StudentEnrollment.id != (current_enrollment_id or 0),
            models.StudentEnrollment.is_active == True,
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
        )
        .first()
    )
    if active_enrollment:
        raise HTTPException(
            status_code=400,
            detail="El alumno ya tiene una inscripcion activa en este ciclo escolar",
        )


def _get_or_create_group(
    db: Session,
    *,
    group_name: Optional[str],
    modality_id: Optional[int] = None,
) -> Optional[models.Group]:
    if not group_name:
        return None
    normalized = group_name.strip()
    if not normalized:
        return None

    group = (
        db.query(models.Group)
        .filter(
            models.Group.name == normalized,
            models.Group.modality_id == modality_id,
        )
        .first()
    )
    if group:
        return group

    group = models.Group(name=normalized, modality_id=modality_id)
    db.add(group)
    db.flush()
    return group


def _sync_student_enrollment_from_legacy(
    db: Session,
    student: models.User,
    *,
    cycle_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> Optional[models.StudentEnrollment]:
    if student.role != models.UserRole.STUDENT:
        return None

    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id
        else _get_active_cycle(db)
    )
    if not cycle:
        return None

    enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student.id,
            models.StudentEnrollment.cycle_id == cycle.id,
        )
        .first()
    )
    if not enrollment and not _has_enrollment_seed_data(student):
        return None

    group = _get_or_create_group(
        db,
        group_name=student.grupo,
        modality_id=student.modality_id,
    )

    if not enrollment:
        enrollment = models.StudentEnrollment(
            student_id=student.id,
            cycle_id=cycle.id,
        )
        db.add(enrollment)

    enrollment.career_id = student.career_id
    enrollment.modality_id = student.modality_id
    enrollment.group_id = group.id if group else None
    enrollment.semester = student.semestre
    _ensure_single_active_enrollment_per_cycle(
        db,
        student_id=student.id,
        cycle_id=cycle.id,
        current_enrollment_id=enrollment.id,
        enrollment_status=student.enrollment_status,
    )
    enrollment.enrollment_status = student.enrollment_status
    enrollment.is_active = student.user_status != models.UserStatus.BAJA and _is_active_enrollment_status(student.enrollment_status)
    if reason:
        enrollment.change_reason = reason
    db.flush()
    return enrollment


def _get_or_create_student_enrollment_for_cycle(
    db: Session,
    student: models.User,
    cycle_id: Optional[int],
    *,
    reason: Optional[str] = None,
) -> models.StudentEnrollment:
    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id
        else _get_active_cycle(db)
    )
    if not cycle:
        raise HTTPException(status_code=404, detail="No hay ciclo escolar activo")

    enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student.id,
            models.StudentEnrollment.cycle_id == cycle.id,
        )
        .first()
    )
    if enrollment:
        return enrollment

    enrollment = _sync_student_enrollment_from_legacy(
        db,
        student,
        cycle_id=cycle.id,
        reason=reason,
    )
    if enrollment:
        return enrollment

    enrollment = models.StudentEnrollment(
        student_id=student.id,
        cycle_id=cycle.id,
        career_id=student.career_id,
        modality_id=student.modality_id,
        semester=student.semestre,
        enrollment_status=student.enrollment_status,
        is_active=student.user_status != models.UserStatus.BAJA and _is_active_enrollment_status(student.enrollment_status),
        change_reason=reason,
    )
    db.add(enrollment)
    db.flush()
    return enrollment


def _get_or_create_course_enrollment(
    db: Session,
    *,
    student: models.User,
    assignment: models.SubjectAssignment,
    attempt_type: models.AttemptType,
    status: models.GradeStatus,
) -> models.CourseEnrollment:
    student_enrollment = _get_or_create_student_enrollment_for_cycle(
        db,
        student,
        assignment.cycle_id,
        reason="Inscripcion academica automatica",
    )
    course_enrollment = (
        db.query(models.CourseEnrollment)
        .filter(
            models.CourseEnrollment.student_enrollment_id == student_enrollment.id,
            models.CourseEnrollment.assignment_id == assignment.id,
            models.CourseEnrollment.attempt_type == attempt_type,
        )
        .first()
    )
    if course_enrollment:
        if course_enrollment.status != status:
            course_enrollment.status = status
        return course_enrollment

    course_enrollment = models.CourseEnrollment(
        student_enrollment_id=student_enrollment.id,
        assignment_id=assignment.id,
        attempt_type=attempt_type,
        status=status,
    )
    db.add(course_enrollment)
    db.flush()
    return course_enrollment


def _ensure_grade_record_for_course_enrollment(
    db: Session,
    *,
    student: models.User,
    assignment: models.SubjectAssignment,
    course_enrollment: models.CourseEnrollment,
    status: models.GradeStatus,
) -> models.Grade:
    grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.course_enrollment_id == course_enrollment.id,
        )
        .first()
    )
    if grade:
        if grade.status != status:
            grade.status = status
        return grade

    grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.assignment_id == assignment.id,
            models.Grade.attempt_type == course_enrollment.attempt_type,
        )
        .first()
    )
    if grade:
        grade.course_enrollment_id = course_enrollment.id
        if grade.status != status:
            grade.status = status
        return grade

    grade = models.Grade(
        student_id=student.id,
        subject_id=assignment.subject_id,
        assignment_id=assignment.id,
        course_enrollment_id=course_enrollment.id,
        attempt_type=course_enrollment.attempt_type,
        status=status,
    )
    db.add(grade)
    db.flush()
    return grade


def _create_admin_course_enrollment(
    db: Session,
    *,
    student: models.User,
    assignment: models.SubjectAssignment,
    attempt_type: models.AttemptType,
    status: models.GradeStatus,
    create_grade_record: bool = True,
) -> models.CourseEnrollment:
    student_enrollment = _get_or_create_student_enrollment_for_cycle(
        db,
        student,
        assignment.cycle_id,
        reason="Inscripcion academica administrativa",
    )

    existing = (
        db.query(models.CourseEnrollment)
        .filter(
            models.CourseEnrollment.student_enrollment_id == student_enrollment.id,
            models.CourseEnrollment.assignment_id == assignment.id,
            models.CourseEnrollment.attempt_type == attempt_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="El alumno ya esta inscrito en esta materia para la misma oportunidad")

    course_enrollment = models.CourseEnrollment(
        student_enrollment_id=student_enrollment.id,
        assignment_id=assignment.id,
        attempt_type=attempt_type,
        status=status,
    )
    db.add(course_enrollment)
    db.flush()

    if create_grade_record:
        _ensure_grade_record_for_course_enrollment(
            db,
            student=student,
            assignment=assignment,
            course_enrollment=course_enrollment,
            status=status,
        )

    return course_enrollment


def _apply_grade_payload(
    grade: models.Grade,
    grade_update: schemas.GradeUpdate,
    *,
    lock_for_teacher: bool = False,
) -> None:
    if grade_update.score is not None:
        grade.score = grade_update.score
        grade.status = (
            models.GradeStatus.APROBADA if grade_update.score >= 6
            else models.GradeStatus.REPROBADA
        )
        grade.recorded_at = datetime.utcnow()
    elif grade_update.status is not None:
        grade.status = grade_update.status
        if grade.recorded_at is None and grade_update.status != models.GradeStatus.CURSANDO:
            grade.recorded_at = datetime.utcnow()

    if lock_for_teacher and (grade.score is not None or grade.status != models.GradeStatus.CURSANDO):
        grade.teacher_locked = True

    if grade.course_enrollment:
        grade.course_enrollment.status = grade.status


def _get_grade_for_course_enrollment(course_enrollment: models.CourseEnrollment) -> Optional[models.Grade]:
    if not course_enrollment.grades:
        return None
    ordered = sorted(
        course_enrollment.grades,
        key=lambda grade: (
            grade.recorded_at or datetime.min,
            grade.id,
        ),
        reverse=True,
    )
    return ordered[0]


def _get_teacher_name_from_assignment(assignment: Optional[models.SubjectAssignment]) -> Optional[str]:
    if assignment and assignment.teacher:
        return assignment.teacher.full_name or assignment.teacher.username
    return None


def _serialize_grade_row(
    *,
    grade: Optional[models.Grade] = None,
    course_enrollment: Optional[models.CourseEnrollment] = None,
) -> dict:
    assignment = course_enrollment.assignment if course_enrollment else (grade.assignment if grade else None)
    subject = assignment.subject if assignment and assignment.subject else (grade.subject if grade else None)
    teacher_name = _get_teacher_name_from_assignment(assignment)

    status = grade.status if grade else (course_enrollment.status if course_enrollment else None)
    attempt_type = grade.attempt_type if grade else (course_enrollment.attempt_type if course_enrollment else None)
    score = grade.score if grade and grade.score is not None else None

    return {
        "grade_id": grade.id if grade else None,
        "course_enrollment_id": course_enrollment.id if course_enrollment else (grade.course_enrollment_id if grade else None),
        "assignment_id": assignment.id if assignment else (grade.assignment_id if grade else None),
        "period": subject.semester if subject else None,
        "description": subject.name if subject else None,
        "credits": subject.credits if subject else None,
        "score": score,
        "status": status,
        "teacher": teacher_name,
        "attempt_type": attempt_type,
    }


def _serialize_course_card(
    course_enrollment: models.CourseEnrollment,
    grade: Optional[models.Grade],
) -> dict:
    assignment = course_enrollment.assignment
    subject = assignment.subject if assignment else (grade.subject if grade else None)
    teacher_name = _get_teacher_name_from_assignment(assignment) or "Docente no asignado"
    status = grade.status if grade else course_enrollment.status
    score = grade.score if grade and grade.score is not None else 0

    return {
        "id": subject.id if subject else None,
        "course_enrollment_id": course_enrollment.id,
        "grade_id": grade.id if grade else None,
        "assignment_id": assignment.id if assignment else None,
        "name": subject.name if subject else None,
        "progress": 100 if status == models.GradeStatus.APROBADA else (40 if status == models.GradeStatus.CURSANDO else 0),
        "score": score,
        "professor": teacher_name,
        "semester": subject.semester if subject else None,
        "credits": subject.credits if subject else None,
        "status": status,
        "attempt_type": grade.attempt_type if grade else course_enrollment.attempt_type,
    }


def _serialize_academic_history_item(
    *,
    grade: Optional[models.Grade] = None,
    course_enrollment: Optional[models.CourseEnrollment] = None,
) -> dict:
    assignment = course_enrollment.assignment if course_enrollment else (grade.assignment if grade else None)
    subject = assignment.subject if assignment and assignment.subject else (grade.subject if grade else None)
    cycle = None
    if assignment and assignment.cycle:
        cycle = assignment.cycle.period
    elif course_enrollment and course_enrollment.student_enrollment and course_enrollment.student_enrollment.cycle:
        cycle = course_enrollment.student_enrollment.cycle.period

    return {
        "grade_id": grade.id if grade else None,
        "course_enrollment_id": course_enrollment.id if course_enrollment else (grade.course_enrollment_id if grade else None),
        "assignment_id": assignment.id if assignment else (grade.assignment_id if grade else None),
        "subject_id": subject.id if subject else None,
        "subject_name": subject.name if subject else None,
        "semester": subject.semester if subject else None,
        "credits": subject.credits if subject else None,
        "cycle": cycle,
        "teacher": _get_teacher_name_from_assignment(assignment),
        "attempt_type": grade.attempt_type if grade else (course_enrollment.attempt_type if course_enrollment else None),
        "final_score": grade.score if grade else None,
        "status": grade.status if grade else (course_enrollment.status if course_enrollment else None),
        "dropped_at": course_enrollment.dropped_at if course_enrollment else None,
    }


def _get_academic_history_for_student(db: Session, student_id: int) -> list[dict]:
    history = []
    seen_grade_ids = set()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == student_id)
        .all()
    )
    for course_enrollment in course_enrollments:
        grade = _get_grade_for_course_enrollment(course_enrollment)
        if grade:
            seen_grade_ids.add(grade.id)
        history.append(_serialize_academic_history_item(grade=grade, course_enrollment=course_enrollment))

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == student_id).all()
    for grade in legacy_grades:
        if grade.id in seen_grade_ids:
            continue
        history.append(_serialize_academic_history_item(grade=grade))

    history.sort(
        key=lambda item: (
            item["cycle"] or "",
            item["semester"] or "",
            item["subject_name"] or "",
            item["grade_id"] or 0,
        )
    )
    return history


def _get_student_enrollment_for_charge(
    db: Session,
    *,
    student: models.User,
    cycle_id: Optional[int] = None,
    student_enrollment_id: Optional[int] = None,
) -> Optional[models.StudentEnrollment]:
    if student_enrollment_id is not None:
        return (
            db.query(models.StudentEnrollment)
            .filter(
                models.StudentEnrollment.id == student_enrollment_id,
                models.StudentEnrollment.student_id == student.id,
            )
            .first()
        )

    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id is not None
        else _get_active_cycle(db)
    )
    if not cycle:
        return None

    return (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student.id,
            models.StudentEnrollment.cycle_id == cycle.id,
        )
        .first()
    )


def _get_group_member_enrollments(
    db: Session,
    *,
    group_name: str,
    cycle_id: Optional[int] = None,
    career_name: Optional[str] = None,
    usernames: Optional[list[str]] = None,
) -> tuple[list[models.StudentEnrollment], models.SchoolCycle]:
    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id is not None
        else _get_active_cycle(db)
    )
    if not cycle:
        raise HTTPException(status_code=404, detail="No hay ciclo escolar activo")

    query = (
        db.query(models.StudentEnrollment)
        .join(models.Group, models.Group.id == models.StudentEnrollment.group_id)
        .join(models.User, models.User.id == models.StudentEnrollment.student_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .filter(
            models.StudentEnrollment.cycle_id == cycle.id,
            models.Group.name == group_name,
            models.User.role == models.UserRole.STUDENT,
        )
    )

    normalized_career = (career_name or "").strip()
    if normalized_career:
        query = query.filter(models.Career.name == normalized_career)

    if usernames:
        query = query.filter(models.User.username.in_(usernames))

    return query.all(), cycle


def _ensure_payment_for_charge(db: Session, charge: models.Charge) -> models.Payment:
    payment = (
        db.query(models.Payment)
        .filter(models.Payment.charge_id == charge.id)
        .first()
    )
    if not payment:
        payment = models.Payment(student_id=charge.student_id, charge_id=charge.id)
        db.add(payment)

    payment.concept = charge.concept
    payment.amount = charge.amount
    payment.due_date = charge.due_date
    payment.status = charge.status
    db.flush()
    return payment


def _ensure_unique_charge_for_enrollment_period(
    db: Session,
    *,
    student_enrollment_id: Optional[int],
    concept: str,
    period_label: Optional[str],
    current_charge_id: Optional[int] = None,
) -> None:
    if student_enrollment_id is None:
        return

    duplicate = (
        db.query(models.Charge)
        .filter(
            models.Charge.student_enrollment_id == student_enrollment_id,
            models.Charge.concept == concept,
            models.Charge.period_label == period_label,
            models.Charge.id != (current_charge_id or 0),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="Ya existe un cargo para esa inscripcion y periodo")


class JsonFormatter(logging.Formatter):
    """Formato JSON compacto para logs estructurados."""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                log[key] = value
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=True)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("unives.api")
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Validar configuracion en produccion
if settings.is_production:
    settings.validate_production()

# Origenes CORS: "*" o lista separada por coma
_cors_origins = settings.cors_origins

app = FastAPI(
    title="Plataforma Escolar Unives API",
    description="API de gestion academica: alumnos, docentes, materias, calificaciones, pagos y tramites.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
admin_required = auth.require_roles(models.UserRole.ADMIN)
teacher_or_admin = auth.require_roles(models.UserRole.TEACHER, models.UserRole.ADMIN)
services_or_admin = auth.require_roles(models.UserRole.SERVICES, models.UserRole.ADMIN)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = int((time.time() - start) * 1000)
        status_code = response.status_code if response else 500
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client": _get_client_ip(request),
            },
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    error_id = str(uuid4())
    logger.warning(
        "http_error",
        extra={
            "error_id": error_id,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"id": error_id, "message": exc.detail, "status_code": exc.status_code}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid4())
    logger.exception(
        "unhandled_error",
        extra={"error_id": error_id, "path": request.url.path},
    )
    message = str(exc) if settings.DEBUG else "Error interno. Revisa logs con el id proporcionado."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"id": error_id, "message": message, "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR}},
    )


@app.get("/", summary="Estado del API")
def root():
    return {"message": "Plataforma Escolar Unives API operativa"}


@app.get("/catalogs/careers", response_model=list[schemas.Career], summary="Catalogo de carreras", tags=["Catalogos"])
def list_careers(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las carreras almacenadas en la base de datos."""
    return db.query(models.Career).order_by(models.Career.name).all()


@app.post("/admin/catalogs/careers", response_model=schemas.Career, summary="Crear carrera", tags=["Catalogos"])
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


@app.get("/catalogs/modalities", response_model=list[schemas.Modality], summary="Catalogo de modalidades", tags=["Catalogos"])
def list_modalities(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las modalidades disponibles."""
    return db.query(models.Modality).order_by(models.Modality.name).all()


@app.post("/admin/catalogs/modalities", response_model=schemas.Modality, summary="Crear modalidad", tags=["Catalogos"])
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


@app.get("/admin/study-plans", response_model=list[schemas.StudyPlan], summary="Listar planes de estudio", tags=["Administracion"])
def get_study_plans(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.StudyPlan).order_by(models.StudyPlan.id.desc()).all()


@app.post("/admin/study-plans", response_model=schemas.StudyPlan, summary="Crear plan de estudio", tags=["Administracion"])
def create_study_plan(
    study_plan: schemas.StudyPlanCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    career = db.query(models.Career).filter(models.Career.id == study_plan.career_id).first()
    if not career:
        raise HTTPException(status_code=404, detail="Carrera no encontrada")

    existing = (
        db.query(models.StudyPlan)
        .filter(
            models.StudyPlan.career_id == study_plan.career_id,
            models.StudyPlan.name == study_plan.name,
        )
        .first()
    )
    if existing:
        return existing

    new_plan = models.StudyPlan(
        career_id=study_plan.career_id,
        name=study_plan.name.strip(),
        version=study_plan.version.strip() or "1",
        is_active=study_plan.is_active,
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return new_plan


@app.get("/admin/study-plans/{study_plan_id}", response_model=schemas.StudyPlanWithSubjects, summary="Detalle de plan de estudio", tags=["Administracion"])
def get_study_plan(
    study_plan_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    plan = db.query(models.StudyPlan).filter(models.StudyPlan.id == study_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan de estudio no encontrado")
    return plan


@app.post("/admin/study-plans/{study_plan_id}/subjects", response_model=schemas.StudyPlanSubject, summary="Agregar materia a plan", tags=["Administracion"])
def add_subject_to_study_plan(
    study_plan_id: int,
    payload: schemas.StudyPlanSubjectCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    plan = db.query(models.StudyPlan).filter(models.StudyPlan.id == study_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan de estudio no encontrado")

    subject = db.query(models.Subject).filter(models.Subject.id == payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    existing = (
        db.query(models.StudyPlanSubject)
        .filter(
            models.StudyPlanSubject.study_plan_id == study_plan_id,
            models.StudyPlanSubject.subject_id == payload.subject_id,
        )
        .first()
    )
    if existing:
        return existing

    item = models.StudyPlanSubject(
        study_plan_id=study_plan_id,
        subject_id=payload.subject_id,
        semester=payload.semester or subject.semester,
        order_index=payload.order_index,
        is_required=payload.is_required,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/admin/school-cycle", response_model=Optional[schemas.SchoolCycle], tags=["Configuracion"])
def get_active_school_cycle(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).order_by(models.SchoolCycle.id.desc()).first()


@app.post("/admin/school-cycle", response_model=schemas.SchoolCycle, tags=["Configuracion"])
def save_school_cycle(cycle: schemas.SchoolCycleCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db.query(models.SchoolCycle).update({"is_active": False})
    new_cycle = models.SchoolCycle(
        period=cycle.period,
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


@app.post("/admin/school-cycle/generate-payments", response_model=schemas.SchoolCyclePaymentResult, tags=["Configuracion"])
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
            _ensure_payment_for_charge(db, charge)
            payments_created += 1
            students_affected.add(student.id)

    db.commit()
    return {
        "payments_created": payments_created,
        "students_affected": len(students_affected),
        "months": [m["month"] for m in months],
    }


@app.post("/token", response_model=schemas.TokenPair, summary="Iniciar sesion", tags=["Autenticacion"])
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Autentica con username (matricula) y password. Devuelve tokens JWT (access y refresh)."""
    client_ip = _get_client_ip(request)
    _enforce_login_rate_limit(client_ip)

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
            detail="Acceso bloqueado. Consulta a servicios escolares, es posible que tengas algún pago pendiente.",
        )
    _reset_login_attempts(client_ip)
    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
    refresh_token = auth.create_refresh_token(data={"sub": user.username, "role": user.role})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@app.post("/token/refresh", response_model=schemas.TokenPair, summary="Refrescar access token", tags=["Autenticacion"])
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


@app.get("/users/me", response_model=schemas.User, summary="Perfil del usuario", tags=["Usuario"])
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


# ----------------------------
# Admin
# ----------------------------

@app.get("/admin/stats", summary="Estadisticas generales", tags=["Administracion"])
def get_admin_stats(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    total_students = db.query(models.User).filter(models.User.role == models.UserRole.STUDENT).count()
    paid_payments = db.query(models.Payment).filter(models.Payment.status == models.PaymentStatus.PAGADO).all()
    total_income = sum(p.amount for p in paid_payments)
    pending_services = db.query(models.ServiceRequest).filter(models.ServiceRequest.status == models.ServiceRequestStatus.EN_PROCESO).count()
    total_teachers = db.query(models.User).filter(models.User.role == models.UserRole.TEACHER).count()
    return {
        "total_students": total_students,
        "total_income": total_income,
        "pending_services": pending_services,
        "total_teachers": total_teachers,
    }


@app.get("/admin/students", response_model=list[schemas.User], summary="Listar alumnos", tags=["Administracion"])
def get_all_students(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.role == models.UserRole.STUDENT).all()


@app.post("/admin/students", response_model=schemas.User, summary="Crear alumno", tags=["Administracion"])
def create_student(student: schemas.UserCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == student.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="La matricula/usuario ya esta registrada")

    career = None
    if student.career_id:
        career = db.query(models.Career).filter(models.Career.id == student.career_id).first()
        if not career:
            raise HTTPException(status_code=400, detail="Carrera no encontrada")
    elif student.carrera:
        career = db.query(models.Career).filter(models.Career.name == student.carrera).first()
        if not career:
            career = models.Career(name=student.carrera)
            db.add(career)
            db.flush()

    modality = None
    if student.modality_id:
        modality = db.query(models.Modality).filter(models.Modality.id == student.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
    elif student.modalidad:
        modality = db.query(models.Modality).filter(models.Modality.name == student.modalidad).first()
        if not modality:
            modality = models.Modality(name=student.modalidad)
            db.add(modality)
            db.flush()

    hashed_password = auth.get_password_hash(student.password)
    new_user = models.User(
        username=student.username,
        email=student.email,
        full_name=student.full_name,
        role=models.UserRole.STUDENT,
        hashed_password=hashed_password,
        career_id=career.id if career else None,
        carrera=career.name if career else student.carrera,
        modality_id=modality.id if modality else None,
        modalidad=modality.name if modality else student.modalidad,
        semestre=student.semestre,
        grupo=student.grupo,
    )
    db.add(new_user)
    db.flush()
    _assign_curriculum_to_student(db, new_user.id, career.name if career else student.carrera)
    _sync_student_enrollment_from_legacy(db, new_user, reason="Alta de alumno")
    db.commit()
    db.refresh(new_user)
    return new_user


@app.put("/admin/students/{username}", response_model=schemas.User, summary="Actualizar alumno", tags=["Administracion"])
def update_student(username: str, student_update: schemas.UserUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    if student_update.full_name is not None:
        db_user.full_name = student_update.full_name
    if student_update.email is not None:
        db_user.email = student_update.email
    if student_update.password:
        db_user.hashed_password = auth.get_password_hash(student_update.password)
    if student_update.user_status is not None:
        db_user.user_status = student_update.user_status
    if student_update.enrollment_status is not None:
        db_user.enrollment_status = student_update.enrollment_status
    if student_update.career_id is not None:
        career = db.query(models.Career).filter(models.Career.id == student_update.career_id).first()
        if not career:
            raise HTTPException(status_code=400, detail="Carrera no encontrada")
        db_user.career_id = career.id
        db_user.carrera = career.name
    if hasattr(student_update, "carrera") and student_update.carrera is not None:
        career = db.query(models.Career).filter(models.Career.name == student_update.carrera).first()
        if not career and student_update.carrera:
            career = models.Career(name=student_update.carrera)
            db.add(career)
            db.flush()
        if career:
            db_user.career_id = career.id
            db_user.carrera = career.name
    if student_update.modality_id is not None:
        modality = db.query(models.Modality).filter(models.Modality.id == student_update.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
        db_user.modality_id = modality.id
        db_user.modalidad = modality.name
    if hasattr(student_update, "modalidad") and student_update.modalidad is not None:
        modality = db.query(models.Modality).filter(models.Modality.name == student_update.modalidad).first()
        if not modality and student_update.modalidad:
            modality = models.Modality(name=student_update.modalidad)
            db.add(modality)
            db.flush()
        if modality:
            db_user.modality_id = modality.id
            db_user.modalidad = modality.name
    if student_update.semestre is not None:
        db_user.semestre = student_update.semestre
    if student_update.grupo is not None:
        db_user.grupo = student_update.grupo

    _sync_student_enrollment_from_legacy(db, db_user, reason="Actualizacion de alumno")

    db.commit()
    db.refresh(db_user)

    # Asignar materias de la carrera actualizada
    if student_update.career_id is not None or (hasattr(student_update, "carrera") and student_update.carrera is not None):
        _assign_curriculum_to_student(db, db_user.id, db_user.carrera)
        db.commit()

    db.refresh(db_user)
    return db_user


@app.get("/admin/students/{username}/full", summary="Perfil completo de alumno con docentes", tags=["Administracion"])
def get_student_full_profile(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    grades_data = []
    for g in db_user.grades:
        teacher_name = None
        cycle_period = None
        if g.assignment:
            if g.assignment.teacher:
                teacher_name = g.assignment.teacher.full_name or g.assignment.teacher.username
            if g.assignment.cycle:
                cycle_period = g.assignment.cycle.period
        grades_data.append({
            "id": g.id,
            "subject_id": g.subject_id,
            "subject_name": g.subject.name if g.subject else None,
            "subject_semester": g.subject.semester if g.subject else None,
            "subject_credits": g.subject.credits if g.subject else None,
            "assignment_id": g.assignment_id,
            "course_enrollment_id": g.course_enrollment_id,
            "teacher": teacher_name,
            "cycle": cycle_period,
            "score": g.score,
            "status": g.status,
            "attempt_type": g.attempt_type,
        })

    return {
        "id": db_user.id,
        "username": db_user.username,
        "full_name": db_user.full_name,
        "email": db_user.email,
        "role": db_user.role,
        "user_status": db_user.user_status,
        "enrollment_status": db_user.enrollment_status,
        "carrera": db_user.carrera,
        "career_id": db_user.career_id,
        "modalidad": db_user.modalidad,
        "modality_id": db_user.modality_id,
        "semestre": db_user.semestre,
        "grupo": db_user.grupo,
        "grades": grades_data,
        "payments": [{"id": p.id, "concept": p.concept, "amount": p.amount, "status": p.status, "due_date": str(p.due_date)} for p in db_user.payments],
        "service_requests": [{"id": r.id, "type": r.type, "status": r.status} for r in db_user.service_requests],
    }


@app.get("/admin/students/{username}/boleta", summary="Boleta de calificaciones en PDF", tags=["Administracion"])
def get_student_boleta_pdf(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from fpdf import FPDF
    from fastapi.responses import Response as FastAPIResponse

    student = db.query(models.User).filter(models.User.username == username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    grades = db.query(models.Grade).filter(models.Grade.student_id == student.id).all()

    def safe(s: object, maxlen: int = 999) -> str:
        return str(s or "—")[:maxlen]

    class BoletaPDF(FPDF):
        def header(self):
            self.set_fill_color(26, 61, 182)
            self.rect(0, 0, 210, 30, "F")
            self.set_font("Helvetica", "B", 15)
            self.set_text_color(255, 255, 255)
            self.set_xy(10, 7)
            self.cell(190, 9, "Universidad Unives - Legion Axolot", align="C", new_x="LMARGIN", new_y="NEXT")
            self.set_font("Helvetica", "", 9)
            self.set_xy(10, 18)
            self.cell(190, 7, "Boleta Oficial de Calificaciones", align="C", new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(0, 0, 0)
            self.set_y(35)

        def footer(self):
            self.set_y(-13)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(128)
            self.cell(0, 8, f"Pagina {self.page_no()} | Generado el {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC | Sistema Administrativo Unives", align="C")

    pdf = BoletaPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Folio + fecha
    folio = f"BOL-{username}-{int(datetime.utcnow().timestamp()) % 1000000:06d}"
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100)
    pdf.cell(95, 5, f"Folio: {folio}", align="L")
    pdf.cell(95, 5, f"Fecha: {datetime.utcnow().strftime('%d/%m/%Y')}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(3)

    # Bloque de datos del alumno
    pdf.set_fill_color(240, 244, 255)
    pdf.set_draw_color(200, 210, 240)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(190, 7, "  Datos del Alumno", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    info_rows = [
        ("Nombre", safe(student.full_name, 40), "Matricula", safe(student.username)),
        ("Carrera", safe(student.carrera, 35), "Semestre", safe(student.semestre)),
        ("Correo", safe(student.email, 38), "Grupo", safe(student.grupo)),
    ]
    for lbl1, val1, lbl2, val2 in info_rows:
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(22, 6, lbl1 + ":", border="LB", fill=True)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(73, 6, val1, border="RB", fill=True)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(22, 6, lbl2 + ":", border="LB", fill=True)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(73, 6, val2, border="RB", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Tabla de calificaciones
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(190, 7, "  Historial Academico", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    col_w = [60, 18, 45, 20, 16, 18, 13]
    headers = ["Materia", "Sem.", "Docente", "Ciclo", "Calif.", "Estatus", "Tipo"]
    pdf.set_fill_color(26, 61, 182)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 7)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_text_color(0)
    pdf.set_font("Helvetica", "", 7)
    alt = False
    for g in grades:
        subject_name = safe(g.subject.name if g.subject else None, 38)
        subject_sem = safe(g.subject.semester if g.subject else None, 8)
        teacher_name = "—"
        cycle_period = "—"
        if g.assignment:
            if g.assignment.teacher:
                teacher_name = safe(g.assignment.teacher.full_name or g.assignment.teacher.username, 28)
            if g.assignment.cycle:
                cycle_period = safe(g.assignment.cycle.period, 12)
        score_txt = str(round(g.score, 1)) if g.score is not None else "—"
        status_txt = safe(g.status, 14)
        attempt_txt = "Extemp." if str(g.attempt_type) == "Extemporaneo" else "Regular"

        fill_color = (248, 250, 255) if alt else (255, 255, 255)
        pdf.set_fill_color(*fill_color)
        vals = [subject_name, subject_sem, teacher_name, cycle_period, score_txt, status_txt, attempt_txt]
        for w, v in zip(col_w, vals):
            pdf.cell(w, 5.5, v, border=1, fill=True, align="C" if w <= 20 else "L")
        pdf.ln()
        alt = not alt

    if not grades:
        pdf.set_fill_color(255, 255, 255)
        pdf.cell(190, 7, "No hay calificaciones registradas.", border=1, align="C", new_x="LMARGIN", new_y="NEXT")

    # Resumen estadistico
    pdf.ln(4)
    approved = sum(1 for g in grades if str(g.status) == "Aprobada")
    failed = sum(1 for g in grades if str(g.status) == "Reprobada")
    in_prog = sum(1 for g in grades if str(g.status) == "Cursando")
    scored = [g.score for g in grades if g.score is not None]
    avg = round(sum(scored) / len(scored), 2) if scored else 0.0
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(240, 244, 255)
    for lbl, val in [("Aprobadas", approved), ("Reprobadas", failed), ("En curso", in_prog), ("Promedio", avg)]:
        pdf.cell(47, 6, f"{lbl}: {val}", border=1, fill=True, align="C")
    pdf.ln()

    # Area de firmas
    pdf.ln(14)
    pdf.set_draw_color(100)
    line_y = pdf.get_y()
    pdf.set_line_width(0.4)
    pdf.line(15, line_y, 80, line_y)
    pdf.line(130, line_y, 195, line_y)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(80)
    pdf.set_xy(15, line_y + 2)
    pdf.cell(65, 5, "Director(a) General", align="C")
    pdf.set_xy(130, line_y + 2)
    pdf.cell(65, 5, "Secretaria Academica", align="C")
    pdf.ln(10)

    # Nota legal
    pdf.set_font("Helvetica", "I", 6.5)
    pdf.set_text_color(140)
    pdf.multi_cell(190, 3.5,
        "Documento generado electronicamente por el Sistema Administrativo de Universidad Unives. "
        "Valido como consulta interna. Para tramites oficiales solicite documento con sello fisico en Secretaria Academica.",
        align="C")

    pdf_bytes = bytes(pdf.output())
    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=boleta_{username}.pdf"},
    )


@app.get("/admin/reports/grades-export", summary="Exportar calificaciones CSV por ciclo", tags=["Administracion"])
def export_grades_csv(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    import csv, io
    from fastapi.responses import StreamingResponse

    query = (
        db.query(models.Grade)
        .join(models.Grade.student)
        .filter(models.User.role == models.UserRole.STUDENT)
    )

    if cycle_id:
        query = (
            query
            .join(models.Grade.assignment)
            .join(models.SubjectAssignment.cycle)
            .filter(models.SchoolCycle.id == cycle_id)
        )

    grades = query.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Matricula", "Nombre", "Carrera", "Semestre", "Grupo", "Materia", "Sem.Materia", "Creditos", "Calificacion", "Estatus", "Tipo", "Docente", "Ciclo"])
    for g in grades:
        s = g.student
        subj = g.subject
        teacher = "—"
        cycle_p = "—"
        if g.assignment:
            if g.assignment.teacher:
                teacher = g.assignment.teacher.full_name or g.assignment.teacher.username
            if g.assignment.cycle:
                cycle_p = g.assignment.cycle.period or "—"
        writer.writerow([
            s.username if s else "",
            s.full_name if s else "",
            s.carrera if s else "",
            s.semestre if s else "",
            s.grupo if s else "",
            subj.name if subj else "",
            subj.semester if subj else "",
            subj.credits if subj else "",
            g.score if g.score is not None else "",
            str(g.status) if g.status else "",
            str(g.attempt_type) if g.attempt_type else "",
            teacher,
            cycle_p,
        ])

    content = "\ufeff" + buf.getvalue()
    fname = f"calificaciones_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@app.get("/admin/students/{username}/academic-history", response_model=list[schemas.AcademicHistoryItem], summary="Historial academico del alumno", tags=["Administracion"])
def get_student_academic_history(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    return _get_academic_history_for_student(db, student.id)


@app.put("/admin/students/{username}/password", summary="Resetear contraseña de alumno", tags=["Administracion"])
def reset_student_password(username: str, body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    new_password = body.get("password", "").strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    db_user.hashed_password = auth.get_password_hash(new_password)
    db.commit()
    return {"detail": "Contraseña actualizada"}


@app.post("/admin/enrollments", summary="Inscribir alumno en asignación", tags=["Administracion"])
def enroll_student_in_assignment(body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    """Inscribe manualmente a un alumno en una asignación (materia + docente + ciclo)."""
    username = body.get("username")
    assignment_id = body.get("assignment_id")

    student = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.REGULAR,
        status=models.GradeStatus.CURSANDO,
    )
    db.commit()
    db.refresh(course_enrollment)
    latest_grade = _get_grade_for_course_enrollment(course_enrollment)
    return {
        "detail": "Inscripción exitosa",
        "grade_id": latest_grade.id if latest_grade else None,
        "course_enrollment_id": course_enrollment.id,
        "reassigned": False,
    }


@app.get("/admin/course-enrollments", response_model=list[schemas.CourseEnrollmentWithRelations], summary="Listar carga académica", tags=["Administracion"])
def get_course_enrollments(
    cycle_id: Optional[int] = None,
    username: Optional[str] = None,
    assignment_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    query = db.query(models.CourseEnrollment).join(models.StudentEnrollment)

    if cycle_id:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle_id)
    if username:
        query = query.join(models.User).filter(models.User.username == username)
    if assignment_id:
        query = query.filter(models.CourseEnrollment.assignment_id == assignment_id)

    return query.order_by(models.CourseEnrollment.id.desc()).all()


@app.post("/admin/course-enrollments", response_model=schemas.CourseEnrollmentWithRelations, summary="Inscribir alumno a materia", tags=["Administracion"])
def create_course_enrollment(
    body: schemas.CourseEnrollmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == body.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=body.attempt_type,
        status=body.status,
        create_grade_record=body.create_grade_record,
    )
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.post("/admin/course-enrollments/extraordinary", response_model=schemas.CourseEnrollmentWithRelations, summary="Registrar extraordinario", tags=["Administracion"])
def create_extraordinary_course_enrollment(
    body: schemas.CourseEnrollmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == body.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.EXTEMPORANEO,
        status=body.status,
        create_grade_record=body.create_grade_record,
    )
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.post("/admin/course-enrollments/retake", response_model=schemas.CourseEnrollmentWithRelations, summary="Registrar recursa", tags=["Administracion"])
def create_retake_course_enrollment(
    body: schemas.CourseEnrollmentCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == body.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignacion no encontrada")

    prior_grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.subject_id == assignment.subject_id,
            models.Grade.status == models.GradeStatus.REPROBADA,
        )
        .first()
    )
    if not prior_grade:
        raise HTTPException(status_code=400, detail="La recursa requiere un antecedente reprobado de la misma materia")

    course_enrollment = _create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.REGULAR,
        status=body.status,
        create_grade_record=body.create_grade_record,
    )
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.put("/admin/course-enrollments/{course_enrollment_id}/drop", response_model=schemas.CourseEnrollmentWithRelations, summary="Dar de baja materia", tags=["Administracion"])
def drop_course_enrollment(
    course_enrollment_id: int,
    body: schemas.CourseEnrollmentDropRequest,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    course_enrollment = (
        db.query(models.CourseEnrollment)
        .filter(models.CourseEnrollment.id == course_enrollment_id)
        .first()
    )
    if not course_enrollment:
        raise HTTPException(status_code=404, detail="Inscripcion academica no encontrada")

    if course_enrollment.dropped_at:
        raise HTTPException(status_code=400, detail="La materia ya fue dada de baja")

    course_enrollment.dropped_at = body.dropped_at or datetime.utcnow()
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@app.get("/admin/groups", response_model=list[schemas.GroupSummary], summary="Listar grupos con conteo de alumnos", tags=["Administracion"])
def get_groups(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from sqlalchemy import func
    active_cycle = _get_active_cycle(db)
    if not active_cycle:
        return []

    tutor_user = aliased(models.User)
    rows = (
        db.query(
            models.Group.id.label("group_id"),
            models.Group.name.label("grupo"),
            func.coalesce(func.min(models.Career.name), "Sin carrera").label("carrera"),
            models.Group.modality_id.label("modality_id"),
            models.Group.tutor_id.label("tutor_id"),
            tutor_user.full_name.label("tutor_name"),
            func.count(models.StudentEnrollment.id).label("total"),
        )
        .outerjoin(
            models.StudentEnrollment,
            (models.StudentEnrollment.group_id == models.Group.id) & (models.StudentEnrollment.cycle_id == active_cycle.id),
        )
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(tutor_user, tutor_user.id == models.Group.tutor_id)
        .filter(models.Group.is_active == True)
        .group_by(
            models.Group.id,
            models.Group.name,
            models.Group.modality_id,
            models.Group.tutor_id,
            tutor_user.full_name,
        )
        .order_by(models.Group.name)
        .all()
    )
    return [
        {
            "group_id": r.group_id,
            "grupo": r.grupo,
            "carrera": r.carrera or "Sin carrera",
            "total": r.total,
            "modality_id": r.modality_id,
            "tutor_id": r.tutor_id,
            "tutor_name": r.tutor_name,
        }
        for r in rows
    ]


@app.post("/admin/groups", response_model=schemas.GroupWithRelations, summary="Crear grupo", tags=["Administracion"])
def create_group(
    body: schemas.GroupCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.Group)
        .filter(
            models.Group.name == body.name.strip(),
            models.Group.modality_id == body.modality_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un grupo con ese nombre y modalidad")

    tutor = None
    if body.tutor_id is not None:
        tutor = db.query(models.User).filter(models.User.id == body.tutor_id).first()
        if not tutor or tutor.role != models.UserRole.TEACHER:
            raise HTTPException(status_code=400, detail="Tutor no encontrado o no es docente")

    group = models.Group(
        name=body.name.strip(),
        modality_id=body.modality_id,
        tutor_id=tutor.id if tutor else None,
        is_active=body.is_active,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@app.get("/admin/groups/{group_id}", response_model=schemas.GroupWithRelations, summary="Detalle de grupo", tags=["Administracion"])
def get_group_detail(
    group_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return group


@app.put("/admin/groups/{group_id}", response_model=schemas.GroupWithRelations, summary="Editar grupo", tags=["Administracion"])
def update_group(
    group_id: int,
    body: schemas.GroupUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    if body.name is not None:
        normalized_name = body.name.strip()
        duplicate = (
            db.query(models.Group)
            .filter(
                models.Group.id != group.id,
                models.Group.name == normalized_name,
                models.Group.modality_id == (body.modality_id if body.modality_id is not None else group.modality_id),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Ya existe otro grupo con ese nombre y modalidad")
        group.name = normalized_name

    if "modality_id" in body.model_fields_set:
        group.modality_id = body.modality_id

    if "tutor_id" in body.model_fields_set:
        if body.tutor_id is None:
            group.tutor_id = None
        else:
            tutor = db.query(models.User).filter(models.User.id == body.tutor_id).first()
            if not tutor or tutor.role != models.UserRole.TEACHER:
                raise HTTPException(status_code=400, detail="Tutor no encontrado o no es docente")
            group.tutor_id = tutor.id

    if "is_active" in body.model_fields_set:
        group.is_active = body.is_active

    db.commit()
    db.refresh(group)
    return group


@app.get("/admin/groups/{group_id}/students", response_model=list[schemas.StudentEnrollmentWithRelations], summary="Alumnos del grupo", tags=["Administracion"])
def get_group_students(
    group_id: int,
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    query = db.query(models.StudentEnrollment).filter(models.StudentEnrollment.group_id == group_id)
    if cycle_id:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle_id)
    else:
        active_cycle = _get_active_cycle(db)
        if active_cycle:
            query = query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)

    return query.order_by(models.StudentEnrollment.id.desc()).all()


@app.get("/admin/student-enrollments", response_model=list[schemas.StudentEnrollmentWithRelations], summary="Listar inscripciones por ciclo", tags=["Administracion"])
def get_student_enrollments(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id
        else _get_active_cycle(db)
    )
    if not cycle:
        return []

    return (
        db.query(models.StudentEnrollment)
        .filter(models.StudentEnrollment.cycle_id == cycle.id)
        .order_by(models.StudentEnrollment.id.desc())
        .all()
    )


@app.get("/admin/migration-audit", response_model=schemas.MigrationAuditResult, summary="Auditoria de migracion escolar", tags=["Administracion"])
def get_migration_audit(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    active_cycle = _get_active_cycle(db)

    legacy_students = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.STUDENT)
        .all()
    )
    legacy_students_with_seed_data = [student for student in legacy_students if _has_enrollment_seed_data(student)]
    legacy_students_with_group = [
        student for student in legacy_students
        if student.grupo and str(student.grupo).strip()
    ]

    student_enrollments_query = db.query(models.StudentEnrollment)
    if active_cycle:
        student_enrollments_query = student_enrollments_query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)
    student_enrollments = student_enrollments_query.all()

    enrolled_student_ids = {enrollment.student_id for enrollment in student_enrollments}
    missing_usernames = [
        student.username
        for student in legacy_students_with_seed_data
        if student.id not in enrolled_student_ids
    ]

    grades_total = db.query(models.Grade).count()
    grades_linked = (
        db.query(models.Grade)
        .filter(models.Grade.course_enrollment_id.isnot(None))
        .count()
    )

    return {
        "active_cycle_id": active_cycle.id if active_cycle else None,
        "active_cycle_period": active_cycle.period if active_cycle else None,
        "legacy_students_with_seed_data": len(legacy_students_with_seed_data),
        "student_enrollments_in_active_cycle": len(student_enrollments),
        "legacy_students_missing_enrollment": missing_usernames[:50],
        "legacy_students_with_group": len(legacy_students_with_group),
        "active_cycle_group_memberships": sum(1 for enrollment in student_enrollments if enrollment.group_id),
        "grades_total": grades_total,
        "grades_linked_to_course_enrollment": grades_linked,
        "grades_without_course_enrollment": grades_total - grades_linked,
    }


def _resolve_report_cycle(db: Session, cycle_id: Optional[int] = None):
    return (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id is not None
        else _get_active_cycle(db)
    )


def _parse_report_datetime(value: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Formato de fecha invalido. Usa YYYY-MM-DD") from exc
    if len(value) <= 10:
        if end_of_day:
            return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed


def _apply_datetime_range(query, column, date_from: Optional[str] = None, date_to: Optional[str] = None):
    start = _parse_report_datetime(date_from)
    end = _parse_report_datetime(date_to, end_of_day=True)
    if start:
        query = query.filter(column >= start)
    if end:
        query = query.filter(column <= end)
    return query


def _datetime_in_range(value: Optional[datetime], date_from: Optional[str] = None, date_to: Optional[str] = None) -> bool:
    if value is None:
        return not date_from and not date_to
    start = _parse_report_datetime(date_from)
    end = _parse_report_datetime(date_to, end_of_day=True)
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


def _filtered_student_enrollments_query(
    db: Session,
    *,
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    cycle = _resolve_report_cycle(db, cycle_id)
    query = (
        db.query(models.StudentEnrollment)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    if cycle:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle.id)
    if career:
        query = query.filter(models.Career.name == career)
    if modality:
        query = query.filter(models.Modality.name == modality)
    if semester:
        query = query.filter(models.StudentEnrollment.semester == semester)
    if group_name:
        query = query.filter(models.Group.name == group_name)
    query = _apply_datetime_range(query, models.StudentEnrollment.created_at, date_from, date_to)
    return query, cycle


def _grade_matches_filters(
    grade: models.Grade,
    *,
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    teacher_username: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> bool:
    assignment = grade.assignment
    course_enrollment = grade.course_enrollment
    student_enrollment = course_enrollment.student_enrollment if course_enrollment else None
    effective_date = grade.recorded_at or (
        student_enrollment.created_at if student_enrollment else None
    )

    if cycle_id is not None and assignment and assignment.cycle_id != cycle_id:
        return False
    if teacher_username and assignment and assignment.teacher and assignment.teacher.username != teacher_username:
        return False
    if career and student_enrollment and student_enrollment.career and student_enrollment.career.name != career:
        return False
    if modality and student_enrollment and student_enrollment.modality and student_enrollment.modality.name != modality:
        return False
    if semester and student_enrollment and student_enrollment.semester != semester:
        return False
    if group_name and student_enrollment and student_enrollment.group and student_enrollment.group.name != group_name:
        return False
    if not _datetime_in_range(effective_date, date_from, date_to):
        return False
    return True


@app.get("/admin/reports/enrollment-summary", response_model=list[schemas.EnrollmentSummaryRow], summary="Reporte de matricula activa", tags=["Administracion"])
def get_enrollment_summary_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    cycle = _resolve_report_cycle(db, cycle_id)

    query = (
        db.query(
            models.StudentEnrollment.cycle_id.label("cycle_id"),
            models.SchoolCycle.period.label("cycle_period"),
            models.Career.name.label("career"),
            models.Modality.name.label("modality"),
            models.StudentEnrollment.semester.label("semester"),
            models.Group.name.label("group_name"),
            func.count(models.StudentEnrollment.id).label("total_students"),
        )
        .outerjoin(models.SchoolCycle, models.SchoolCycle.id == models.StudentEnrollment.cycle_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
        .filter(
            models.StudentEnrollment.enrollment_status == models.EnrollmentStatus.INSCRITO,
            models.StudentEnrollment.is_active == True,
        )
    )
    if cycle:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle.id)
    if career:
        query = query.filter(models.Career.name == career)
    if modality:
        query = query.filter(models.Modality.name == modality)
    if semester:
        query = query.filter(models.StudentEnrollment.semester == semester)
    if group_name:
        query = query.filter(models.Group.name == group_name)
    query = _apply_datetime_range(query, models.StudentEnrollment.created_at, date_from, date_to)

    rows = (
        query.group_by(
            models.StudentEnrollment.cycle_id,
            models.SchoolCycle.period,
            models.Career.name,
            models.Modality.name,
            models.StudentEnrollment.semester,
            models.Group.name,
        )
        .order_by(models.Career.name, models.Modality.name, models.StudentEnrollment.semester, models.Group.name)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.get("/admin/reports/grade-outcomes", response_model=list[schemas.GradeOutcomeRow], summary="Reporte de aprobacion y reprobacion", tags=["Administracion"])
def get_grade_outcomes_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    teacher_username: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    grades = (
        db.query(models.Grade)
        .outerjoin(models.SubjectAssignment, models.SubjectAssignment.id == models.Grade.assignment_id)
        .all()
    )
    cycle = _resolve_report_cycle(db, cycle_id)
    cycle_filter = cycle.id if cycle else None

    grouped: dict[tuple[Optional[int], Optional[str], Optional[str], Optional[str]], dict] = {}
    for grade in grades:
        assignment = grade.assignment
        if not _grade_matches_filters(
            grade,
            cycle_id=cycle_filter,
            career=career,
            modality=modality,
            semester=semester,
            group_name=group_name,
            teacher_username=teacher_username,
            date_from=date_from,
            date_to=date_to,
        ):
            continue

        subject_name = assignment.subject.name if assignment and assignment.subject else (grade.subject.name if grade.subject else None)
        teacher_name = assignment.teacher.full_name if assignment and assignment.teacher and assignment.teacher.full_name else (
            assignment.teacher.username if assignment and assignment and assignment.teacher else None
        )
        cycle_period = assignment.cycle.period if assignment and assignment.cycle else None
        key = (grade.assignment_id, subject_name, teacher_name, cycle_period)
        bucket = grouped.setdefault(
            key,
            {
                "assignment_id": grade.assignment_id,
                "subject_name": subject_name,
                "teacher_name": teacher_name,
                "cycle_period": cycle_period,
                "approved_count": 0,
                "failed_count": 0,
                "in_progress_count": 0,
                "total_records": 0,
            },
        )
        bucket["total_records"] += 1
        if grade.status == models.GradeStatus.APROBADA:
            bucket["approved_count"] += 1
        elif grade.status == models.GradeStatus.REPROBADA:
            bucket["failed_count"] += 1
        else:
            bucket["in_progress_count"] += 1

    return list(grouped.values())


@app.get("/admin/reports/finance-summary", response_model=schemas.FinanceSummary, summary="Reporte financiero", tags=["Administracion"])
def get_finance_summary_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    charges_query = (
        db.query(models.Charge)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    cycle = _resolve_report_cycle(db, cycle_id)
    if cycle:
        charges_query = charges_query.filter(models.StudentEnrollment.cycle_id == cycle.id)
    if career:
        charges_query = charges_query.filter(models.Career.name == career)
    if modality:
        charges_query = charges_query.filter(models.Modality.name == modality)
    if semester:
        charges_query = charges_query.filter(models.StudentEnrollment.semester == semester)
    if group_name:
        charges_query = charges_query.filter(models.Group.name == group_name)
    charges_query = _apply_datetime_range(charges_query, models.Charge.due_date, date_from, date_to)

    charges = charges_query.all()
    now = datetime.utcnow()

    total_amount = sum(charge.amount for charge in charges)
    paid = [charge for charge in charges if charge.status == models.PaymentStatus.PAGADO]
    pending = [charge for charge in charges if charge.status == models.PaymentStatus.PENDIENTE]
    overdue = [
        charge
        for charge in charges
        if charge.status in (models.PaymentStatus.PENDIENTE, models.PaymentStatus.VENCIDO) and charge.due_date < now
    ]

    return {
        "total_charges": len(charges),
        "total_charge_amount": total_amount,
        "paid_amount": sum(charge.amount for charge in paid),
        "pending_amount": sum(charge.amount for charge in pending),
        "overdue_amount": sum(charge.amount for charge in overdue),
        "paid_count": len(paid),
        "pending_count": len(pending),
        "overdue_count": len(overdue),
    }


@app.get("/admin/reports/blocked-students", response_model=list[schemas.BlockedStudentRow], summary="Reporte de alumnos bloqueados", tags=["Administracion"])
def get_blocked_students_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    students = db.query(models.User).filter(
        models.User.role == models.UserRole.STUDENT,
        models.User.user_status == models.UserStatus.BLOQUEADO,
    ).all()
    enrollments_query, cycle = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    filtered_student_ids = {enrollment.student_id for enrollment in enrollments_query.all()}
    apply_enrollment_scope = any([
        cycle_id is not None,
        career,
        modality,
        semester,
        group_name,
        date_from,
        date_to,
    ])
    now = datetime.utcnow()
    rows = []
    for student in students:
        if apply_enrollment_scope and student.id not in filtered_student_ids:
            continue
        overdue_charges = [
            charge for charge in student.charges
            if charge.status in (models.PaymentStatus.PENDIENTE, models.PaymentStatus.VENCIDO) and charge.due_date < now
            and _datetime_in_range(charge.due_date, date_from, date_to)
        ]
        pending_charges = [
            charge for charge in student.charges
            if charge.status != models.PaymentStatus.PAGADO
            and _datetime_in_range(charge.due_date, date_from, date_to)
        ]
        rows.append(
            {
                "student_id": student.id,
                "username": student.username,
                "full_name": student.full_name,
                "overdue_charges": len(overdue_charges),
                "overdue_amount": sum(charge.amount for charge in overdue_charges),
                "total_pending_amount": sum(charge.amount for charge in pending_charges),
            }
        )
    return rows


@app.get("/admin/reports/overview", response_model=schemas.AdminOverviewReport, summary="Resumen ejecutivo administrativo", tags=["Administracion"])
def get_admin_overview_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    enrollments_query, cycle = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    enrollments = enrollments_query.all()
    enrollment_ids = [enrollment.id for enrollment in enrollments]
    student_ids = [enrollment.student_id for enrollment in enrollments]
    course_enrollments = (
        db.query(models.CourseEnrollment)
        .filter(models.CourseEnrollment.student_enrollment_id.in_(enrollment_ids or [-1]))
        .all()
    )
    assignments = {ce.assignment_id for ce in course_enrollments if ce.assignment_id}
    teacher_ids = {ce.assignment.teacher_id for ce in course_enrollments if ce.assignment and ce.assignment.teacher_id}
    grades = db.query(models.Grade).filter(models.Grade.course_enrollment_id.isnot(None)).all()
    relevant_grades = [
        grade for grade in grades
        if grade.course_enrollment_id in {ce.id for ce in course_enrollments}
        and _grade_matches_filters(
            grade,
            cycle_id=cycle.id if cycle else None,
            career=career,
            modality=modality,
            semester=semester,
            group_name=group_name,
            date_from=date_from,
            date_to=date_to,
        )
    ]
    scored = [float(grade.score) for grade in relevant_grades if grade.score is not None]
    approved = [grade for grade in relevant_grades if grade.status == models.GradeStatus.APROBADA]
    failed = [grade for grade in relevant_grades if grade.status == models.GradeStatus.REPROBADA]
    in_progress = [grade for grade in relevant_grades if grade.status not in (models.GradeStatus.APROBADA, models.GradeStatus.REPROBADA)]
    blocked_students = (
        db.query(models.User)
        .filter(models.User.id.in_(student_ids or [-1]), models.User.user_status == models.UserStatus.BLOQUEADO)
        .count()
    )
    overdue_amount = sum(
        charge.amount
        for charge in db.query(models.Charge).filter(models.Charge.student_enrollment_id.in_(enrollment_ids or [-1])).all()
        if charge.status in (models.PaymentStatus.PENDIENTE, models.PaymentStatus.VENCIDO) and charge.due_date < datetime.utcnow()
        and _datetime_in_range(charge.due_date, date_from, date_to)
    )
    pending_services = (
        db.query(models.ServiceRequest)
        .filter(
            models.ServiceRequest.student_id.in_(student_ids or [-1]),
            models.ServiceRequest.status != models.ServiceRequestStatus.ENTREGADO,
        )
        .filter(
            models.ServiceRequest.request_date >= _parse_report_datetime(date_from) if date_from else True,
            models.ServiceRequest.request_date <= _parse_report_datetime(date_to, end_of_day=True) if date_to else True,
        )
        .count()
    )
    approval_rate = round((len(approved) / (len(approved) + len(failed)) * 100), 2) if (len(approved) + len(failed)) else 0.0
    failed_rate = round((len(failed) / (len(approved) + len(failed)) * 100), 2) if (len(approved) + len(failed)) else 0.0

    return {
        "cycle_id": cycle.id if cycle else None,
        "cycle_period": cycle.period if cycle else None,
        "total_students": len({enrollment.student_id for enrollment in enrollments}),
        "active_enrollments": sum(1 for enrollment in enrollments if enrollment.is_active),
        "groups_count": len({enrollment.group_id for enrollment in enrollments if enrollment.group_id}),
        "teachers_with_assignments": len(teacher_ids),
        "subjects_with_assignments": len(assignments),
        "average_final_score": round(sum(scored) / len(scored), 2) if scored else 0.0,
        "approval_rate": approval_rate,
        "failed_rate": failed_rate,
        "failed_count": len(failed),
        "in_progress_count": len(in_progress),
        "blocked_students": blocked_students,
        "overdue_amount": overdue_amount,
        "pending_services": pending_services,
    }


@app.get("/admin/reports/enrollment-status", response_model=list[schemas.EnrollmentStatusRow], summary="Resumen de estatus de inscripcion", tags=["Administracion"])
def get_enrollment_status_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    query, _ = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    rows = (
        query.with_entities(
            models.StudentEnrollment.enrollment_status.label("enrollment_status"),
            func.count(models.StudentEnrollment.id).label("total_students"),
        )
        .group_by(models.StudentEnrollment.enrollment_status)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.get("/admin/reports/teacher-workload", response_model=list[schemas.TeacherWorkloadRow], summary="Carga academica por docente", tags=["Administracion"])
def get_teacher_workload_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    semester: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = _resolve_report_cycle(db, cycle_id)
    assignments_query = (
        db.query(models.SubjectAssignment)
        .outerjoin(models.Subject, models.Subject.id == models.SubjectAssignment.subject_id)
    )
    if cycle:
        assignments_query = assignments_query.filter(models.SubjectAssignment.cycle_id == cycle.id)
    if career:
        assignments_query = assignments_query.filter(models.Subject.career == career)
    if semester:
        assignments_query = assignments_query.filter(models.Subject.semester == semester)
    if date_from or date_to:
        assignments_query = assignments_query.filter(models.SubjectAssignment.cycle_id.isnot(None))

    assignments = assignments_query.all()
    grouped: dict[int, dict] = {}
    for assignment in assignments:
        if not assignment.teacher_id:
            continue
        if date_from or date_to:
            cycle_start = assignment.cycle.start_date if assignment.cycle else None
            if not _datetime_in_range(cycle_start, date_from, date_to):
                continue
        bucket = grouped.setdefault(
            assignment.teacher_id,
            {
                "teacher_username": assignment.teacher.username if assignment.teacher else None,
                "teacher_name": assignment.teacher.full_name if assignment.teacher else None,
                "assignments_count": 0,
                "students_count": 0,
                "subjects_count": set(),
                "groups_count": set(),
            },
        )
        bucket["assignments_count"] += 1
        bucket["subjects_count"].add(assignment.subject_id)
        course_enrollments = assignment.course_enrollments or []
        bucket["students_count"] += len({ce.student_enrollment.student_id for ce in course_enrollments if ce.student_enrollment})
        bucket["groups_count"].update({ce.student_enrollment.group_id for ce in course_enrollments if ce.student_enrollment and ce.student_enrollment.group_id})

    return [
        {
            **value,
            "subjects_count": len(value["subjects_count"]),
            "groups_count": len(value["groups_count"]),
        }
        for value in grouped.values()
    ]


@app.get("/admin/reports/academic-risk", response_model=list[schemas.AcademicRiskRow], summary="Alumnos en riesgo academico", tags=["Administracion"])
def get_academic_risk_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    enrollments_query, _ = _filtered_student_enrollments_query(
        db,
        cycle_id=cycle_id,
        career=career,
        modality=modality,
        semester=semester,
        group_name=group_name,
        date_from=date_from,
        date_to=date_to,
    )
    enrollments = enrollments_query.all()
    rows = []
    for enrollment in enrollments:
        course_enrollments = enrollment.course_enrollments or []
        grades = [
            grade for ce in course_enrollments for grade in (ce.grades or [])
            if _grade_matches_filters(
                grade,
                cycle_id=cycle_id,
                career=career,
                modality=modality,
                semester=semester,
                group_name=group_name,
                date_from=date_from,
                date_to=date_to,
            )
        ]
        scores = [float(grade.score) for grade in grades if grade.score is not None]
        failed_count = sum(1 for grade in grades if grade.status == models.GradeStatus.REPROBADA)
        in_progress_count = sum(1 for grade in grades if grade.status == models.GradeStatus.CURSANDO)
        if failed_count == 0 and in_progress_count == 0:
            continue
        rows.append(
            {
                "username": enrollment.student.username if enrollment.student else "",
                "full_name": enrollment.student.full_name if enrollment.student else None,
                "career": enrollment.career.name if enrollment.career else None,
                "semester": enrollment.semester,
                "group_name": enrollment.group.name if enrollment.group else None,
                "failed_count": failed_count,
                "in_progress_count": in_progress_count,
                "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            }
        )
    rows.sort(key=lambda item: (-item["failed_count"], -item["in_progress_count"], item["average_score"]))
    return rows


@app.get("/admin/reports/service-summary", response_model=list[schemas.ServiceSummaryRow], summary="Resumen de servicios escolares", tags=["Administracion"])
def get_service_summary_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    query = (
        db.query(models.ServiceRequest)
        .join(models.User, models.User.id == models.ServiceRequest.student_id)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.student_id == models.User.id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    cycle = _resolve_report_cycle(db, cycle_id)
    if cycle:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle.id)
    if career:
        query = query.filter(models.Career.name == career)
    if modality:
        query = query.filter(models.Modality.name == modality)
    if semester:
        query = query.filter(models.StudentEnrollment.semester == semester)
    if group_name:
        query = query.filter(models.Group.name == group_name)
    query = _apply_datetime_range(query, models.ServiceRequest.request_date, date_from, date_to)

    rows = (
        query.with_entities(
            models.ServiceRequest.type.label("service_type"),
            models.ServiceRequest.status.label("status"),
            func.count(models.ServiceRequest.id).label("total_requests"),
        )
        .group_by(models.ServiceRequest.type, models.ServiceRequest.status)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.get("/admin/reports/charge-breakdown", response_model=list[schemas.ChargeBreakdownRow], summary="Desglose financiero por tipo de cargo", tags=["Administracion"])
def get_charge_breakdown_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    modality: Optional[str] = None,
    semester: Optional[str] = None,
    group_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    query = (
        db.query(models.Charge)
        .outerjoin(models.StudentEnrollment, models.StudentEnrollment.id == models.Charge.student_enrollment_id)
        .outerjoin(models.Career, models.Career.id == models.StudentEnrollment.career_id)
        .outerjoin(models.Modality, models.Modality.id == models.StudentEnrollment.modality_id)
        .outerjoin(models.Group, models.Group.id == models.StudentEnrollment.group_id)
    )
    cycle = _resolve_report_cycle(db, cycle_id)
    if cycle:
        query = query.filter(models.StudentEnrollment.cycle_id == cycle.id)
    if career:
        query = query.filter(models.Career.name == career)
    if modality:
        query = query.filter(models.Modality.name == modality)
    if semester:
        query = query.filter(models.StudentEnrollment.semester == semester)
    if group_name:
        query = query.filter(models.Group.name == group_name)
    query = _apply_datetime_range(query, models.Charge.due_date, date_from, date_to)

    rows = (
        query.with_entities(
            models.Charge.charge_type.label("charge_type"),
            models.Charge.status.label("status"),
            func.count(models.Charge.id).label("total_charges"),
            func.coalesce(func.sum(models.Charge.amount), 0).label("total_amount"),
        )
        .group_by(models.Charge.charge_type, models.Charge.status)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@app.put("/admin/student-enrollments/move-group", response_model=schemas.StudentEnrollmentWithRelations, summary="Mover alumno a grupo", tags=["Administracion"])
def move_student_to_group(
    body: schemas.MoveStudentGroupRequest,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == body.username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == body.cycle_id).first()
        if body.cycle_id
        else _get_active_cycle(db)
    )
    if not cycle:
        raise HTTPException(status_code=404, detail="No hay ciclo escolar activo")

    enrollment = (
        db.query(models.StudentEnrollment)
        .filter(
            models.StudentEnrollment.student_id == student.id,
            models.StudentEnrollment.cycle_id == cycle.id,
        )
        .first()
    )
    if not enrollment:
        enrollment = _sync_student_enrollment_from_legacy(
            db,
            student,
            cycle_id=cycle.id,
            reason=body.reason or "Creacion de inscripcion desde movimiento de grupo",
        )
        if not enrollment:
            enrollment = models.StudentEnrollment(
                student_id=student.id,
                cycle_id=cycle.id,
                career_id=student.career_id,
                modality_id=body.modality_id or student.modality_id,
                semester=student.semestre,
                enrollment_status=student.enrollment_status,
                is_active=student.user_status != models.UserStatus.BAJA and _is_active_enrollment_status(student.enrollment_status),
                change_reason=body.reason,
            )
            _ensure_single_active_enrollment_per_cycle(
                db,
                student_id=student.id,
                cycle_id=cycle.id,
                enrollment_status=enrollment.enrollment_status,
            )
            db.add(enrollment)
            db.flush()

    if body.modality_id is not None:
        modality = db.query(models.Modality).filter(models.Modality.id == body.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
        student.modality_id = modality.id
        student.modalidad = modality.name
        enrollment.modality_id = modality.id

    group = _get_or_create_group(
        db,
        group_name=body.group_name,
        modality_id=enrollment.modality_id or student.modality_id,
    )

    enrollment.group_id = group.id if group else None
    enrollment.change_reason = body.reason or enrollment.change_reason
    student.grupo = group.name if group else None

    db.commit()
    db.refresh(enrollment)
    return enrollment


@app.put("/admin/group-actions/bulk-enrollment", summary="Cambiar inscripción de todo un grupo", tags=["Administracion"])
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

    enrollments, active_cycle = _get_group_member_enrollments(
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
        _ensure_single_active_enrollment_per_cycle(
            db,
            student_id=student.id,
            cycle_id=active_cycle.id,
            current_enrollment_id=enrollment.id,
            enrollment_status=models.EnrollmentStatus(enrollment_status),
        )
        enrollment.enrollment_status = enrollment_status
        enrollment.is_active = _is_active_enrollment_status(models.EnrollmentStatus(enrollment_status))
    db.commit()
    return {"updated": len(enrollments), "enrollment_status": enrollment_status}


@app.post("/admin/group-actions/bulk-assign", summary="Asignar materia a todo un grupo", tags=["Administracion"])
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

    enrollments, _ = _get_group_member_enrollments(
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
            course_enrollment = _get_or_create_course_enrollment(
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
                course_enrollment_id=_get_or_create_course_enrollment(
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


@app.get("/admin/school-cycles/all", summary="Todos los ciclos escolares", tags=["Configuracion"])
def get_all_school_cycles(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    cycles = db.query(models.SchoolCycle).order_by(models.SchoolCycle.id.desc()).all()
    result = []
    for c in cycles:
        payment_count = db.query(models.Payment).filter(
            models.Payment.concept.like(f"%{c.period}%") if c.period else False
        ).count() if c.period else 0
        result.append({
            "id": c.id,
            "period": c.period,
            "start_date": str(c.start_date)[:10] if c.start_date else None,
            "end_date": str(c.end_date)[:10] if c.end_date else None,
            "is_active": c.is_active,
            "monthly_amount": c.monthly_amount,
            "payment_count": payment_count,
        })
    return result


@app.get("/admin/teachers", response_model=list[schemas.User], summary="Listar docentes", tags=["Administracion"])
def get_all_teachers(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.User).filter(models.User.role == models.UserRole.TEACHER).all()


@app.put("/admin/teachers/{username}", response_model=schemas.User, summary="Actualizar docente", tags=["Administracion"])
def update_teacher(username: str, teacher_update: schemas.UserUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.TEACHER).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Docente no encontrado")

    if teacher_update.full_name is not None:
        db_user.full_name = teacher_update.full_name
    if teacher_update.email is not None:
        db_user.email = teacher_update.email
    if teacher_update.password:
        db_user.hashed_password = auth.get_password_hash(teacher_update.password)

    db.commit()
    db.refresh(db_user)
    return db_user


@app.post("/admin/teachers", response_model=schemas.User, summary="Crear docente", tags=["Administracion"])
def create_teacher(teacher: schemas.UserCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == teacher.username).first():
        raise HTTPException(status_code=400, detail="El usuario/matrícula ya está registrado")

    if teacher.email and db.query(models.User).filter(models.User.email == teacher.email).first():
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado por otro usuario")

    hashed_password = auth.get_password_hash(teacher.password)
    new_user = models.User(
        username=teacher.username,
        email=teacher.email,
        full_name=teacher.full_name,
        role=models.UserRole.TEACHER,
        hashed_password=hashed_password,
    )
    db.add(new_user)
    try:
        db.commit()
        db.refresh(new_user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error al guardar: verifica que el usuario y correo sean únicos")
    return new_user


@app.get("/admin/subjects", response_model=list[schemas.Subject], summary="Listar materias", tags=["Administracion"])
def get_all_subjects(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Subject).all()


@app.post("/admin/subjects", response_model=schemas.Subject, summary="Crear materia", tags=["Administracion"])
def create_subject(subject: schemas.SubjectCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    new_subject = models.Subject(
        name=subject.name,
        credits=subject.credits,
        semester=subject.semester,
        career=subject.career,
    )
    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)
    return new_subject


@app.put("/admin/subjects/{subject_id}", response_model=schemas.SubjectWithTeacher, summary="Actualizar materia", tags=["Administracion"])
def update_subject(subject_id: int, subject_update: schemas.SubjectUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
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

@app.get("/admin/subject-assignments", response_model=list[schemas.SubjectAssignment], summary="Listar asignaciones", tags=["Administracion"])
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
    return query.all()


@app.post("/admin/subject-assignments", response_model=schemas.SubjectAssignment, summary="Asignar docente a materia", tags=["Administracion"])
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

    # Verificar duplicado
    existing = db.query(models.SubjectAssignment).filter(
        models.SubjectAssignment.subject_id == data.subject_id,
        models.SubjectAssignment.teacher_id == teacher.id,
        models.SubjectAssignment.cycle_id == cycle_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Este docente ya tiene esta materia asignada en el ciclo indicado")

    assignment = models.SubjectAssignment(
        subject_id=data.subject_id,
        teacher_id=teacher.id,
        cycle_id=cycle_id,
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
        grade.assignment_id = assignment.id
        if grade.student:
            grade.course_enrollment_id = _get_or_create_course_enrollment(
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

    data = _jsonable_encoder(assignment)
    data["auto_linked"] = linked_count
    return _JSONResponse(content=data)


@app.delete("/admin/subject-assignments/{assignment_id}", summary="Eliminar asignación", tags=["Administracion"])
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


@app.put("/admin/grades/{grade_id}", response_model=schemas.Grade, summary="Actualizar calificacion (admin)", tags=["Administracion"])
def update_grade(grade_id: int, grade_update: schemas.GradeUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")

    _apply_grade_payload(db_grade, grade_update)

    db.commit()
    db.refresh(db_grade)
    return db_grade


@app.get("/admin/payments", response_model=list[schemas.PaymentWithStudent], summary="Listar pagos", tags=["Administracion"])
def get_all_payments(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Payment).all()


@app.get("/admin/charges", response_model=list[schemas.ChargeWithStudent], summary="Listar cargos", tags=["Administracion"])
def get_all_charges(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Charge).order_by(models.Charge.id.desc()).all()


@app.post("/admin/charges", response_model=schemas.ChargeWithStudent, summary="Crear cargo", tags=["Administracion"])
def create_charge(charge: schemas.ChargeCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(models.User.username == charge.student_username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    enrollment = _get_student_enrollment_for_charge(
        db,
        student=student,
        cycle_id=charge.cycle_id,
        student_enrollment_id=charge.student_enrollment_id,
    )

    _ensure_unique_charge_for_enrollment_period(
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
    _ensure_payment_for_charge(db, new_charge)
    db.commit()
    db.refresh(new_charge)
    return new_charge


@app.put("/admin/charges/{charge_id}", response_model=schemas.Charge, summary="Actualizar cargo", tags=["Administracion"])
def update_charge(charge_id: int, charge_update: schemas.ChargeUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_charge = db.query(models.Charge).filter(models.Charge.id == charge_id).first()
    if not db_charge:
        raise HTTPException(status_code=404, detail="Cargo no encontrado")

    next_concept = charge_update.concept if charge_update.concept is not None else db_charge.concept
    next_period_label = charge_update.period_label if charge_update.period_label is not None else db_charge.period_label
    _ensure_unique_charge_for_enrollment_period(
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

    _ensure_payment_for_charge(db, db_charge)
    db.commit()
    db.refresh(db_charge)
    return db_charge


@app.post("/admin/payments", response_model=schemas.PaymentWithStudent, summary="Crear pago", tags=["Administracion"])
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


@app.put("/admin/payments/{payment_id}", response_model=schemas.Payment, summary="Actualizar pago", tags=["Administracion"])
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


@app.get("/admin/services", response_model=list[schemas.ServiceRequestWithStudent], summary="Listar tramites", tags=["Administracion"])
def get_all_services(current_user: models.User = Depends(services_or_admin), db: Session = Depends(get_db)):
    return db.query(models.ServiceRequest).all()


@app.post("/admin/services", response_model=schemas.ServiceRequestWithStudent, summary="Crear tramite", tags=["Administracion"])
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


@app.post("/users/me/services", response_model=schemas.ServiceRequest, summary="Solicitar tramite", tags=["Usuario"])
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


@app.post("/users/me/services/with-document", response_model=schemas.ServiceRequest, summary="Solicitar tramite con documento", tags=["Usuario"])
async def create_user_service_with_document(
    type: str = Form(...),
    request_date: str = Form(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    service_payload = schemas.ServiceRequestSelfCreate(type=type, request_date=request_date)
    original_filename, stored_relative_path = _store_service_attachment(
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


@app.get("/users/me/services/{service_id}/attachment", summary="Descargar adjunto de tramite propio", tags=["Usuario"])
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
    file_path = _service_attachment_absolute_path(service.attachment_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(path=file_path, filename=service.attachment_filename or file_path.name)


@app.put("/admin/services/{service_id}", response_model=schemas.ServiceRequest, summary="Actualizar tramite", tags=["Administracion"])
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


@app.get("/admin/services/{service_id}/attachment", summary="Descargar adjunto de tramite", tags=["Administracion"])
def download_admin_service_attachment(
    service_id: int,
    current_user: models.User = Depends(services_or_admin),
    db: Session = Depends(get_db),
):
    service = db.query(models.ServiceRequest).filter(models.ServiceRequest.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Tramite no encontrado")
    file_path = _service_attachment_absolute_path(service.attachment_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    return FileResponse(path=file_path, filename=service.attachment_filename or file_path.name)


# ----------------------------
# Endpoints de usuario
# ----------------------------

@app.get("/users/me/grades", summary="Mis calificaciones", tags=["Usuario"])
def read_user_grades(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    result = []
    seen_grade_ids = set()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == current_user.id)
        .all()
    )
    for course_enrollment in course_enrollments:
        grade = _get_grade_for_course_enrollment(course_enrollment)
        if grade:
            seen_grade_ids.add(grade.id)
        result.append(_serialize_grade_row(grade=grade, course_enrollment=course_enrollment))

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == current_user.id).all()
    for grade in legacy_grades:
        if grade.id in seen_grade_ids:
            continue
        result.append(_serialize_grade_row(grade=grade))

    return result


@app.get("/users/me/academic-history", response_model=list[schemas.AcademicHistoryItem], summary="Mi historial academico", tags=["Usuario"])
def read_user_academic_history(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return _get_academic_history_for_student(db, current_user.id)


@app.put("/users/me", summary="Actualizar perfil", tags=["Usuario"])
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


@app.post("/upload-document", summary="Subir documento", tags=["Usuario"])
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "otro",
    current_user: models.User = Depends(auth.get_current_user),
):
    _validate_upload_file(file)
    upload_dir = f"{settings.UPLOAD_DIR}/{current_user.username}"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {"filename": file.filename, "status": "success", "message": f"Documento {document_type} subido correctamente"}


@app.get("/users/me/payments", summary="Mis pagos", tags=["Usuario"])
def read_user_payments(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Payment).filter(models.Payment.student_id == current_user.id).all()


@app.get("/users/me/charges", response_model=list[schemas.Charge], summary="Mis cargos", tags=["Usuario"])
def read_user_charges(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Charge).filter(models.Charge.student_id == current_user.id).order_by(models.Charge.id.desc()).all()


@app.get("/users/me/services", summary="Mis tramites", tags=["Usuario"])
def read_user_services(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.ServiceRequest).filter(models.ServiceRequest.student_id == current_user.id).all()


@app.get("/users/me/documents", summary="Mis documentos", tags=["Usuario"])
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


@app.get("/users/me/courses", summary="Mis cursos", tags=["Usuario"])
async def read_user_courses(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    course_enrollments = (
        db.query(models.CourseEnrollment)
        .join(models.StudentEnrollment)
        .filter(models.StudentEnrollment.student_id == current_user.id)
        .all()
    )
    courses = []
    seen_grade_ids = set()

    for ce in course_enrollments:
        grade = _get_grade_for_course_enrollment(ce)
        if grade:
            seen_grade_ids.add(grade.id)
        courses.append(_serialize_course_card(ce, grade))

    legacy_grades = db.query(models.Grade).filter(models.Grade.student_id == current_user.id).all()
    for g in legacy_grades:
        if g.id in seen_grade_ids:
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
            }
        )
    return courses


# ----------------------------
# Endpoints de docente
# ----------------------------

@app.get("/teacher/subjects", summary="Asignaciones del docente en ciclo activo", tags=["Docente"])
def get_teacher_subjects(current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    """Devuelve las asignaciones (materia + ciclo) del docente en el ciclo activo.
    El campo 'id' de cada resultado es el assignment_id para usar en /teacher/students/{id}.
    """
    active_cycle = db.query(models.SchoolCycle).filter(models.SchoolCycle.is_active == True).first()
    query = db.query(models.SubjectAssignment)
    if current_user.role == models.UserRole.TEACHER:
        query = query.filter(models.SubjectAssignment.teacher_id == current_user.id)
    if active_cycle:
        query = query.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    assignments = query.all()
    result = []
    for a in assignments:
        result.append({
            "id": a.id,                       # assignment_id (usar en /teacher/students/{id})
            "subject_id": a.subject_id,
            "name": a.subject.name if a.subject else None,
            "credits": a.subject.credits if a.subject else None,
            "semester": a.subject.semester if a.subject else None,
            "career": a.subject.career if a.subject else None,
            "cycle_id": a.cycle_id,
        })
    return result


@app.get("/teacher/students/{assignment_id}", summary="Alumnos por asignación", tags=["Docente"])
def get_students_by_assignment(assignment_id: int, current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    """Devuelve todos los alumnos inscritos en una asignación (REGULAR y EXTEMPORANEO)."""
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if current_user.role == models.UserRole.TEACHER and assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes asignada esta materia")

    result = []
    seen_grade_ids = set()

    course_enrollments = (
        db.query(models.CourseEnrollment)
        .filter(models.CourseEnrollment.assignment_id == assignment_id)
        .all()
    )
    for course_enrollment in course_enrollments:
        student = course_enrollment.student_enrollment.student if course_enrollment.student_enrollment else None
        if not student:
            continue
        grade = _get_grade_for_course_enrollment(course_enrollment)
        if grade:
            seen_grade_ids.add(grade.id)
        result.append({
            "grade_id": grade.id if grade else None,
            "course_enrollment_id": course_enrollment.id,
            "student_id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "score": grade.score if grade else None,
            "status": grade.status if grade else course_enrollment.status,
            "attempt_type": grade.attempt_type if grade else course_enrollment.attempt_type,
        })

    grades = db.query(models.Grade).filter(models.Grade.assignment_id == assignment_id).all()
    for grade in grades:
        if grade.id in seen_grade_ids:
            continue
        result.append({
            "grade_id": grade.id,
            "course_enrollment_id": grade.course_enrollment_id,
            "student_id": grade.student.id,
            "username": grade.student.username,
            "full_name": grade.student.full_name,
            "score": grade.score,
            "status": grade.status,
            "attempt_type": grade.attempt_type,
        })

    result.sort(key=lambda item: ((item["full_name"] or "").lower(), item["username"]))
    return result


@app.post("/teacher/assignments/{assignment_id}/extemporaneo/{student_id}", summary="Crear calificación extemporánea", tags=["Docente"])
def create_extemporaneo_grade(
    assignment_id: int,
    student_id: int,
    grade_data: schemas.ExtemporaneGradeCreate,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    """Agrega un intento de examen extemporáneo para un alumno que reprobó el ordinario.
    El alumno debe tener una calificación REPROBADA en el mismo assignment.
    """
    assignment = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if current_user.role == models.UserRole.TEACHER and assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permisos sobre esta asignación")

    # Verificar que el alumno tiene una calificación REPROBADA en este assignment
    regular_grade = db.query(models.Grade).filter(
        models.Grade.assignment_id == assignment_id,
        models.Grade.student_id == student_id,
        models.Grade.attempt_type == models.AttemptType.REGULAR,
        models.Grade.status == models.GradeStatus.REPROBADA,
    ).first()
    if not regular_grade:
        raise HTTPException(status_code=400, detail="El alumno debe tener una calificación ordinaria REPROBADA para registrar un extemporáneo")

    # Verificar que no existe ya un extemporáneo
    existing = db.query(models.Grade).filter(
        models.Grade.assignment_id == assignment_id,
        models.Grade.student_id == student_id,
        models.Grade.attempt_type == models.AttemptType.EXTEMPORANEO,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe una calificación extemporánea para este alumno en esta asignación")

    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    new_grade = models.Grade(
        student_id=student_id,
        subject_id=assignment.subject_id,
        assignment_id=assignment_id,
        course_enrollment_id=_get_or_create_course_enrollment(
            db,
            student=student,
            assignment=assignment,
            attempt_type=models.AttemptType.EXTEMPORANEO,
            status=grade_data.status,
        ).id,
        attempt_type=models.AttemptType.EXTEMPORANEO,
        score=grade_data.score,
        status=grade_data.status,
    )
    if current_user.role == models.UserRole.TEACHER and (
        grade_data.score is not None or grade_data.status != models.GradeStatus.CURSANDO
    ):
        new_grade.recorded_at = datetime.utcnow()
        new_grade.teacher_locked = True
    db.add(new_grade)
    db.commit()
    db.refresh(new_grade)
    return new_grade


@app.put("/teacher/grades/{grade_id}", summary="Actualizar calificacion", tags=["Docente"])
def update_student_grade(grade_id: int, grade_update: schemas.GradeUpdate, current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")

    # Verificar que el docente tiene permiso sobre esta calificación
    if current_user.role == models.UserRole.TEACHER:
        if db_grade.assignment and db_grade.assignment.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permisos sobre esta calificacion")
        if db_grade.teacher_locked:
            raise HTTPException(
                status_code=403,
                detail="La calificacion ya fue capturada por el docente y solo el administrador puede corregirla",
            )

    if grade_update.score is not None:
        _apply_grade_payload(
            db_grade,
            grade_update,
            lock_for_teacher=current_user.role == models.UserRole.TEACHER,
        )
        # Estatus calculado automáticamente: ≥6 aprobatoria, <6 reprobatoria
    elif grade_update.status is not None:
        _apply_grade_payload(
            db_grade,
            grade_update,
            lock_for_teacher=current_user.role == models.UserRole.TEACHER,
        )

    db.commit()
    db.refresh(db_grade)
    return db_grade




# ── Página Web: endpoints públicos ──────────────────────────────────────────

@app.get("/public/projects", response_model=List[schemas.ProjectOut], tags=["Web Pública"])
def public_get_projects(category: Optional[str] = None, db: Session = Depends(get_db)):
    """Devuelve proyectos/eventos activos. Filtrable por category=portfolio|evento."""
    q = db.query(models.Project).filter(models.Project.is_active == True)
    if category:
        q = q.filter(models.Project.category == category)
    return q.order_by(models.Project.created_at.desc()).all()


@app.post("/public/contacts", response_model=schemas.ContactOut, status_code=201, tags=["Web Pública"])
def public_create_contact(data: schemas.ContactCreate, db: Session = Depends(get_db)):
    """Recibe un lead del formulario de contacto de la landing page."""
    contact = models.Contact(**data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


# ── Página Web: endpoints de administración ──────────────────────────────────

@app.get("/admin/projects", response_model=List[schemas.ProjectOut], tags=["Admin Web"])
def admin_get_projects(category: Optional[str] = None, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    q = db.query(models.Project)
    if category:
        q = q.filter(models.Project.category == category)
    return q.order_by(models.Project.created_at.desc()).all()


@app.post("/admin/projects", response_model=schemas.ProjectOut, status_code=201, tags=["Admin Web"])
def admin_create_project(data: schemas.ProjectCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = models.Project(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.put("/admin/projects/{project_id}", response_model=schemas.ProjectOut, tags=["Admin Web"])
def admin_update_project(project_id: int, data: schemas.ProjectUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@app.delete("/admin/projects/{project_id}", status_code=204, tags=["Admin Web"])
def admin_delete_project(project_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    db.delete(project)
    db.commit()


@app.get("/admin/contacts", response_model=List[schemas.ContactOut], tags=["Admin Web"])
def admin_get_contacts(status: Optional[str] = None, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    q = db.query(models.Contact)
    if status:
        q = q.filter(models.Contact.status == status)
    return q.order_by(models.Contact.created_at.desc()).all()


@app.put("/admin/contacts/{contact_id}/status", response_model=schemas.ContactOut, tags=["Admin Web"])
def admin_update_contact_status(contact_id: int, data: schemas.ContactStatusUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    valid = {e.value for e in models.ContactStatus}
    if data.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status inválido. Opciones: {valid}")
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    contact.status = data.status
    db.commit()
    db.refresh(contact)
    return contact


@app.delete("/admin/contacts/{contact_id}", status_code=204, tags=["Admin Web"])
def admin_delete_contact(contact_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    db.delete(contact)
    db.commit()


# ── Comunidades: endpoints públicos ─────────────────────────────────────────

@app.get("/public/communities", response_model=List[schemas.CommunityOut], tags=["Web Pública"])
def public_get_communities(db: Session = Depends(get_db)):
    """Devuelve comunidades activas ordenadas por sort_order."""
    return (
        db.query(models.Community)
        .filter(models.Community.is_active == True)
        .order_by(models.Community.sort_order, models.Community.id)
        .all()
    )


# ── Comunidades: endpoints de administración ─────────────────────────────────

@app.get("/admin/communities", response_model=List[schemas.CommunityOut], tags=["Admin Web"])
def admin_get_communities(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.Community).order_by(models.Community.sort_order, models.Community.id).all()


@app.post("/admin/communities", response_model=schemas.CommunityOut, status_code=201, tags=["Admin Web"])
def admin_create_community(data: schemas.CommunityCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = models.Community(**data.model_dump())
    db.add(community)
    db.commit()
    db.refresh(community)
    return community


@app.put("/admin/communities/{community_id}", response_model=schemas.CommunityOut, tags=["Admin Web"])
def admin_update_community(community_id: int, data: schemas.CommunityUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = db.query(models.Community).filter(models.Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(community, field, value)
    db.commit()
    db.refresh(community)
    return community


@app.delete("/admin/communities/{community_id}", status_code=204, tags=["Admin Web"])
def admin_delete_community(community_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    community = db.query(models.Community).filter(models.Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=404, detail="Comunidad no encontrada")
    db.delete(community)
    db.commit()


@app.get("/")
def read_root():
    return {"message": "Bienvenido a la API de la Plataforma Escolar Unives"}
