from typing import List, Optional, Any, Dict
import os
import app.main
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response, Request, Security
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, import_csv, curriculum_credits
from app.config import settings
from app.database import get_db
from app.dependencies import admin_required, teacher_or_admin, services_or_admin, oauth2_scheme
from app.moodle_client import moodle_client
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import csv
from io import StringIO
import io

router = APIRouter()

@router.get("/teacher/subjects", summary="Asignaciones del docente en ciclo activo", tags=["Docente"])
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
            "group_id": a.group_id,
            "group_name": a.group.name if a.group else None,
        })
    return result


async def _teacher_moodle_course_ids(current_user: models.User, db: Session) -> tuple[set[int], list[dict]]:
    if current_user.role == models.UserRole.TEACHER and not current_user.moodle_id:
        evidence = await app.main._sync_teacher_to_moodle(db, user=current_user)
        if not evidence.get("success"):
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "No fue posible sincronizar la cuenta docente con Moodle",
                    "moodle_error": app.main._latest_moodle_error(),
                },
            )
    if not current_user.moodle_id:
        return set(), []

    courses = await moodle_client.get_user_courses(int(current_user.moodle_id))
    if courses is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar los cursos del docente en Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    course_ids = {int(course["id"]) for course in courses if course.get("id")}
    return course_ids, courses


@router.get("/teacher/moodle/courses", summary="Cursos Moodle del docente", tags=["Docente"])
async def get_teacher_moodle_courses(
    include_participants: bool = False,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    _, remote_courses = await _teacher_moodle_course_ids(current_user, db)
    remote_ids = [int(course["id"]) for course in remote_courses if course.get("id")]
    local_subjects = (
        db.query(models.Subject)
        .filter(models.Subject.moodle_course_id.in_(remote_ids))
        .all()
        if remote_ids
        else []
    )
    subject_by_course = {
        int(subject.moodle_course_id): subject
        for subject in local_subjects
        if subject.moodle_course_id
    }

    items = []
    for course in remote_courses:
        course_id = int(course.get("id") or 0)
        if not course_id:
            continue
        subject = subject_by_course.get(course_id)
        participants_count = None
        if include_participants:
            participants = await moodle_client.get_enrolled_users(course_id)
            participants_count = len(participants or []) if participants is not None else 0
        serialized = app.main._serialize_moodle_course(course)
        items.append(
            {
                "moodle_course_id": course_id,
                "subject_id": subject.id if subject else None,
                "subject_name": subject.name if subject else serialized.get("displayname"),
                "semester": subject.semester if subject else None,
                "participants_count": participants_count,
                "moodle_course": serialized,
            }
        )
    return {"count": len(items), "moodle_id": current_user.moodle_id, "courses": items}


@router.get("/teacher/moodle/courses/{course_id}/contents", summary="Contenido de curso Moodle del docente", tags=["Docente"])
async def get_teacher_moodle_course_contents(
    course_id: int,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    allowed_ids, _ = await _teacher_moodle_course_ids(current_user, db)
    if course_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Curso Moodle no asignado a este docente")
    sections = await moodle_client.get_course_contents(course_id)
    if sections is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar el contenido del curso Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {"course_id": course_id, "sections": sections}


@router.get("/teacher/moodle/courses/{course_id}/participants", summary="Participantes del curso Moodle", tags=["Docente"])
async def get_teacher_moodle_course_participants(
    course_id: int,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    allowed_ids, _ = await _teacher_moodle_course_ids(current_user, db)
    if course_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Curso Moodle no asignado a este docente")
    users = await moodle_client.get_enrolled_users(course_id)
    if users is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar los participantes del curso Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {
        "course_id": course_id,
        "count": len(users),
        "users": [
            {
                "id": user.get("id"),
                "username": user.get("username"),
                "fullname": user.get("fullname"),
                "email": user.get("email"),
            }
            for user in users
        ],
    }


@router.get("/teacher/moodle/courses/{course_id}/badges", summary="Catalogo de insignias Moodle del curso", tags=["Docente"])
async def get_teacher_moodle_badges(
    course_id: int,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    allowed_ids, _ = await _teacher_moodle_course_ids(current_user, db)
    if course_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Curso Moodle no asignado a este docente")
    remote_users = await moodle_client.get_enrolled_users(course_id)
    if remote_users is None:
        raise HTTPException(status_code=502, detail="No fue posible consultar los participantes del curso")
    moodle_ids = [int(user["id"]) for user in remote_users if user.get("id")]
    local_students = (
        db.query(models.User)
        .filter(
            models.User.moodle_id.in_(moodle_ids),
            models.User.role == models.UserRole.STUDENT,
        )
        .order_by(models.User.full_name.asc())
        .all()
        if moodle_ids
        else []
    )
    catalog = await moodle_client.badge_action(
        "catalog",
        teacher_id=int(current_user.moodle_id or 0),
        course_id=course_id,
    )
    if catalog is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No fue posible consultar las insignias Moodle",
                "moodle_error": app.main._latest_moodle_error(),
            },
        )
    return {
        "course_id": course_id,
        "badges": catalog.get("badges") or [],
        "students": [
            {
                "username": student.username,
                "full_name": student.full_name,
                "moodle_id": student.moodle_id,
            }
            for student in local_students
        ],
    }


@router.post("/teacher/moodle/courses/{course_id}/badges/{badge_id}/award", summary="Otorgar insignia Moodle", tags=["Docente"])
async def award_teacher_moodle_badge(
    course_id: int,
    badge_id: int,
    payload: Dict[str, Any],
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    allowed_ids, _ = await _teacher_moodle_course_ids(current_user, db)
    if course_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Curso Moodle no asignado a este docente")
    username = str(payload.get("username") or "").strip()
    student = db.query(models.User).filter(
        models.User.username == username,
        models.User.role == models.UserRole.STUDENT,
    ).first()
    if not student or not student.moodle_id:
        raise HTTPException(status_code=404, detail="Alumno Moodle no encontrado")
    result = await moodle_client.badge_action(
        "award",
        teacher_id=int(current_user.moodle_id or 0),
        user_id=int(student.moodle_id),
        course_id=course_id,
        badge_id=badge_id,
    )
    if result is None:
        message = app.main._latest_moodle_error() or "No fue posible entregar la insignia"
        status_code = 409 if "ya tiene" in message.lower() else 502
        raise HTTPException(status_code=status_code, detail=message)
    return {
        "message": result.get("message") or "Insignia entregada correctamente",
        "student": student.full_name or student.username,
        "badge_id": badge_id,
        "course_id": course_id,
    }


@router.get("/teacher/notifications", summary="Notificaciones del docente", tags=["Docente"])
def read_teacher_notifications(current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    notifications: list[dict] = app.main._get_custom_notifications_for_user(db, current_user)

    active_cycle = app.main._get_active_cycle(db)
    assignments_query = db.query(models.SubjectAssignment).filter(models.SubjectAssignment.teacher_id == current_user.id)
    if active_cycle:
        assignments_query = assignments_query.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    assignments = assignments_query.all()

    if assignments:
        app.main._push_notification(
            notifications,
            notif_type="assignments",
            title="Materias asignadas",
            message=f"Tienes {len(assignments)} materia(s) asignada(s) en el ciclo activo.",
            level="info",
            source="Administracion",
        )

    unlocked_grades = (
        db.query(models.Grade)
        .join(models.SubjectAssignment, models.SubjectAssignment.id == models.Grade.assignment_id)
        .filter(
            models.SubjectAssignment.teacher_id == current_user.id,
            models.Grade.teacher_locked == False,
        )
    )
    if active_cycle:
        unlocked_grades = unlocked_grades.filter(models.SubjectAssignment.cycle_id == active_cycle.id)
    unlocked_total = unlocked_grades.count()
    if unlocked_total:
        app.main._push_notification(
            notifications,
            notif_type="grades_pending",
            title="Calificaciones pendientes",
            message=f"Aun tienes {unlocked_total} calificacion(es) sin captura final.",
            level="warning",
            source="Control Escolar",
        )

    if settings.MOODLE_BASE_URL:
        app.main._push_notification(
            notifications,
            notif_type="moodle",
            title="Moodle docente disponible",
            message="Puedes entrar a Moodle desde tu panel docente.",
            level="success",
            source="Moodle",
            action_url=app.main._build_moodle_url("/my/courses.php"),
        )

    notifications.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"count": len(notifications), "items": notifications[:20]}


@router.get("/teacher/students/{assignment_id}", summary="Alumnos por asignación", tags=["Docente"])
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
        active_enrollment = app.main._get_active_student_enrollment(db, student.id)
        active_group_name = active_enrollment.group.name if active_enrollment and active_enrollment.group else None
        grade = app.main._get_grade_for_course_enrollment(course_enrollment)
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
            "teacher_locked": grade.teacher_locked if grade else False,
            "document_filename": grade.document_filename if grade else None,
            "has_document": bool(grade and grade.document_path),
            "group_name": (
                active_group_name
                or (
                    course_enrollment.student_enrollment.group.name
                    if course_enrollment.student_enrollment and course_enrollment.student_enrollment.group
                    else None
                )
                or student.grupo
                or (assignment.group.name if assignment.group else None)
            ),
        })

    grades = db.query(models.Grade).filter(models.Grade.assignment_id == assignment_id).all()
    for grade in grades:
        if grade.id in seen_grade_ids:
            continue
        active_enrollment = app.main._get_active_student_enrollment(db, grade.student.id) if grade.student else None
        active_group_name = active_enrollment.group.name if active_enrollment and active_enrollment.group else None
        result.append({
            "grade_id": grade.id,
            "course_enrollment_id": grade.course_enrollment_id,
            "student_id": grade.student.id,
            "username": grade.student.username,
            "full_name": grade.student.full_name,
            "score": grade.score,
            "status": grade.status,
            "attempt_type": grade.attempt_type,
            "teacher_locked": grade.teacher_locked,
            "document_filename": grade.document_filename,
            "has_document": bool(grade.document_path),
            "group_name": active_group_name or grade.student.grupo or (assignment.group.name if assignment.group else None),
        })

    result.sort(key=lambda item: (((item["group_name"] or "Sin grupo")).lower(), (item["full_name"] or "").lower(), item["username"]))
    return result


@router.post("/teacher/assignments/{assignment_id}/extemporaneo/{student_id}", summary="Crear calificación extemporánea", tags=["Docente"])
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

    # Verificar que el alumno tiene una calificación reprobada previa en esta misma asignación.
    failed_grade = db.query(models.Grade).filter(
        models.Grade.assignment_id == assignment_id,
        models.Grade.student_id == student_id,
        models.Grade.attempt_type.in_([models.AttemptType.REGULAR, models.AttemptType.RECURSA]),
        models.Grade.status == models.GradeStatus.REPROBADA,
    ).first()
    if not failed_grade:
        raise HTTPException(status_code=400, detail="El alumno debe tener una calificación reprobada previa para registrar un extemporáneo")

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
        course_enrollment_id=app.main._get_or_create_course_enrollment(
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


@router.put("/teacher/grades/{grade_id}", summary="Actualizar calificacion", tags=["Docente"])
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
        app.main._apply_grade_payload(
            db_grade,
            grade_update,
            lock_for_teacher=current_user.role == models.UserRole.TEACHER,
        )
        # Estatus calculado automáticamente: ≥6 aprobatoria, <6 reprobatoria
    elif grade_update.status is not None:
        app.main._apply_grade_payload(
            db_grade,
            grade_update,
            lock_for_teacher=current_user.role == models.UserRole.TEACHER,
        )

    db.commit()
    db.refresh(db_grade)
    return db_grade


@router.post("/teacher/grades/{grade_id}/document", summary="Subir comprobante fisico de calificacion", tags=["Docente"])
async def upload_grade_document(
    grade_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")
    if current_user.role == models.UserRole.TEACHER:
        if db_grade.assignment and db_grade.assignment.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permiso sobre esta calificacion")
    app.main._validate_upload_file(
        file,
        allowed_types=["image/jpeg", "image/png", "image/webp", "application/pdf"],
        max_size_bytes=10 * 1024 * 1024,
    )
    safe_name = Path(file.filename or "comprobante").name
    relative_dir = Path("grades") / str(grade_id)
    absolute_dir = Path(settings.UPLOAD_DIR) / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}_{safe_name}"
    absolute_path = absolute_dir / stored_name
    with absolute_path.open("wb") as buf:
        buf.write(await file.read())
    db_grade.document_filename = safe_name
    db_grade.document_path = str(relative_dir / stored_name)
    db.commit()
    return {"ok": True, "filename": safe_name}


@router.get("/teacher/grades/{grade_id}/document", summary="Ver comprobante fisico de calificacion", tags=["Docente"])
def download_grade_document(
    grade_id: int,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    from fastapi.responses import FileResponse
    db_grade = db.query(models.Grade).filter(models.Grade.id == grade_id).first()
    if not db_grade or not db_grade.document_path:
        raise HTTPException(status_code=404, detail="Sin comprobante adjunto")
    if current_user.role == models.UserRole.TEACHER:
        if db_grade.assignment and db_grade.assignment.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="No tienes permiso sobre esta calificacion")
    abs_path = (Path(settings.UPLOAD_DIR) / db_grade.document_path).resolve()
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en servidor")
    return FileResponse(str(abs_path), filename=db_grade.document_filename or "comprobante")


# ── Página Web: endpoints públicos ──────────────────────────────────────────


@router.get("/teacher/advisor/students", summary="Alumnos asignados en asesoria", tags=["Docente"])
def read_teacher_advisor_students(current_user: models.User = Depends(teacher_or_admin), db: Session = Depends(get_db)):
    active_cycle = app.main._get_active_cycle(db)
    rows = []
    seen_student_ids = set()

    direct_students = (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.STUDENT,
            models.User.academic_advisor_id == current_user.id,
        )
        .order_by(models.User.full_name.asc(), models.User.username.asc())
        .all()
    )
    def _grade_stats(student_id):
        grades = db.query(models.Grade).filter(models.Grade.student_id == student_id).all()
        approved = sum(1 for g in grades if g.status == models.GradeStatus.APROBADA)
        risk = sum(1 for g in grades if g.status == models.GradeStatus.REPROBADA)
        in_progress = sum(1 for g in grades if g.status == models.GradeStatus.CURSANDO)
        scores = [g.score for g in grades if g.score is not None]
        avg = round(sum(scores) / len(scores), 1) if scores else None
        return {"approved": approved, "risk": risk, "in_progress": in_progress, "avg": avg, "total": len(grades)}

    for student in direct_students:
        enrollment = app.main._get_active_student_enrollment(db, student.id)
        rows.append({
            "student_id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "carrera": enrollment.career.name if enrollment and enrollment.career else student.carrera,
            "period_label": enrollment.cycle.period if enrollment and enrollment.cycle else "Asignacion directa",
            "group_name": enrollment.group.name if enrollment and enrollment.group else student.grupo,
            "source": "direct",
            **_grade_stats(student.id),
        })
        seen_student_ids.add(student.id)

    group_enrollments_query = (
        db.query(models.StudentEnrollment)
        .join(models.Group, models.Group.id == models.StudentEnrollment.group_id)
        .filter(
            models.StudentEnrollment.is_active == True,
            models.Group.tutor_id == current_user.id,
        )
    )
    if active_cycle:
        group_enrollments_query = group_enrollments_query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)
    for enrollment in group_enrollments_query.all():
        student = enrollment.student
        if not student or student.id in seen_student_ids:
            continue
        rows.append({
            "student_id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "carrera": enrollment.career.name if enrollment.career else student.carrera,
            "period_label": enrollment.cycle.period if enrollment.cycle else "Ciclo activo",
            "group_name": enrollment.group.name if enrollment.group else student.grupo,
            "source": "group",
            **_grade_stats(student.id),
        })
        seen_student_ids.add(student.id)

    def _thesis_data(student_id: int) -> dict:
        thesis = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student_id).first()
        if not thesis:
            return {"status": "Sin Iniciar", "title": None, "director": None}
        return {
            "status": thesis.status if isinstance(thesis.status, str) else thesis.status.value,
            "title": thesis.title,
            "director": thesis.director,
        }

    for row in rows:
        row["pasaporte"] = {"thesis": _thesis_data(row["student_id"])}

    rows.sort(key=lambda item: ((item.get("full_name") or "").lower(), item.get("username") or ""))
    return {"students": rows}


@router.put("/teacher/advisor/students/{username}/thesis-status", summary="Actualizar estado de tesis (director)", tags=["Docente"])
def teacher_update_thesis_status(
    username: str,
    payload: dict,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if not app.main._teacher_can_advise_student(db, current_user.id, student):
        raise HTTPException(status_code=403, detail="No tienes permiso para actualizar este alumno")
    new_status = (payload.get("status") or "").strip()
    valid = [e.value for e in models.ThesisStatus]
    if new_status not in valid:
        raise HTTPException(status_code=400, detail=f"Estatus inválido. Use: {valid}")
    record = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student.id).first()
    if not record:
        record = models.ThesisRecord(student_id=student.id)
        db.add(record)
    record.status = new_status
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return {"ok": True, "status": record.status if isinstance(record.status, str) else record.status.value}


@router.get("/teacher/advisor/messages", summary="Historial de mensajes de asesoría enviados", tags=["Docente"])
def list_teacher_advisor_messages(
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    app.main._ensure_notification_schema(db)
    rows = (
        db.query(models.NotificationMessage)
        .filter(
            models.NotificationMessage.created_by_user_id == current_user.id,
            models.NotificationMessage.category == "advisor",
        )
        .order_by(models.NotificationMessage.created_at.desc(), models.NotificationMessage.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": row.id,
            "recipient_user_id": row.recipient_user_id,
            "recipient_username": row.recipient_user.username if row.recipient_user else None,
            "recipient_fullname": row.recipient_user.full_name if row.recipient_user else None,
            "title": row.title,
            "message": row.message,
            "is_read": row.is_read,
            "read_at": row.read_at,
            "deleted_by_recipient": row.deleted_by_recipient,
            "deleted_at": row.deleted_at,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/teacher/advisor/messages", summary="Enviar mensaje de asesoria a un alumno", tags=["Docente"])
def create_teacher_advisor_message(
    payload: dict,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    student_username = (payload.get("student_username") or "").strip()
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or "").strip()
    if not student_username or not title or not message:
        raise HTTPException(status_code=400, detail="Alumno, titulo y mensaje son obligatorios")

    student = (
        db.query(models.User)
        .filter(models.User.username == student_username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if not app.main._teacher_can_advise_student(db, current_user.id, student):
        raise HTTPException(status_code=403, detail="No tienes asignada la asesoria de este alumno")

    app.main._ensure_notification_schema(db)
    notification = models.NotificationMessage(
        recipient_role=models.UserRole.STUDENT,
        recipient_user_id=student.id,
        created_by_user_id=current_user.id,
        target_scope="user",
        category="advisor",
        title=title[:180],
        message=message[:2000],
        level="info",
        is_active=True,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return {"ok": True, "id": notification.id}


@router.post("/teacher/advisor/sessions", summary="Agendar sesion de asesoria", tags=["Docente"])
def create_advisor_session(
    payload: schemas.AdvisorySessionCreate,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == payload.student_username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    if not app.main._teacher_can_advise_student(db, current_user.id, student):
        raise HTTPException(status_code=403, detail="No tienes asignada la asesoria de este alumno")
    session = models.AdvisorySession(
        teacher_id=current_user.id,
        student_id=student.id,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        topic=payload.topic,
        notes=payload.notes,
    )
    db.add(session)
    app.main._ensure_notification_schema(db)
    notif = models.NotificationMessage(
        recipient_role=models.UserRole.STUDENT,
        recipient_user_id=student.id,
        created_by_user_id=current_user.id,
        target_scope="user",
        category="advisor",
        title=f"Asesoría programada: {payload.topic[:80]}",
        message=(
            f"Tu asesor ha agendado una sesión para el "
            f"{payload.scheduled_at.strftime('%d/%m/%Y a las %H:%M')} "
            f"({payload.duration_minutes} min). Tema: {payload.topic}"
        ),
        level="info",
        is_active=True,
    )
    db.add(notif)
    db.commit()
    db.refresh(session)
    return {"ok": True, "id": session.id}


@router.get("/teacher/advisor/sessions", summary="Sesiones de asesoria del docente", tags=["Docente"])
def get_teacher_advisor_sessions(
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(models.AdvisorySession)
        .filter(models.AdvisorySession.teacher_id == current_user.id)
        .order_by(models.AdvisorySession.scheduled_at.asc())
        .all()
    )
    result = []
    for s in sessions:
        student = db.query(models.User).filter(models.User.id == s.student_id).first()
        result.append({
            "id": s.id,
            "student_id": s.student_id,
            "student_username": student.username if student else "-",
            "student_name": student.full_name if student else "-",
            "scheduled_at": s.scheduled_at.isoformat(),
            "duration_minutes": s.duration_minutes,
            "topic": s.topic,
            "notes": s.notes,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "created_at": s.created_at.isoformat(),
        })
    return {"sessions": result}


@router.patch("/teacher/advisor/sessions/{session_id}", summary="Actualizar estado de sesion de asesoria", tags=["Docente"])
def update_advisor_session(
    session_id: int,
    payload: schemas.AdvisorySessionStatusUpdate,
    current_user: models.User = Depends(teacher_or_admin),
    db: Session = Depends(get_db),
):
    session = (
        db.query(models.AdvisorySession)
        .filter(
            models.AdvisorySession.id == session_id,
            models.AdvisorySession.teacher_id == current_user.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    try:
        session.status = models.AdvisorySessionStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {payload.status}")
    if payload.notes is not None:
        session.notes = payload.notes.strip() or None
    db.commit()
    return {"ok": True}


