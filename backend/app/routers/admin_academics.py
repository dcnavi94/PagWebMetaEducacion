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

@router.get("/admin/study-plans", response_model=list[schemas.StudyPlan], summary="Listar planes de estudio", tags=["Administracion"])
def get_study_plans(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.StudyPlan).order_by(models.StudyPlan.id.desc()).all()


@router.post("/admin/study-plans", response_model=schemas.StudyPlan, summary="Crear plan de estudio", tags=["Administracion"])
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


@router.get("/admin/study-plans/{study_plan_id}", response_model=schemas.StudyPlanWithSubjects, summary="Detalle de plan de estudio", tags=["Administracion"])
def get_study_plan(
    study_plan_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    plan = db.query(models.StudyPlan).filter(models.StudyPlan.id == study_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan de estudio no encontrado")
    return plan


@router.post("/admin/study-plans/{study_plan_id}/subjects", response_model=schemas.StudyPlanSubject, summary="Agregar materia a plan", tags=["Administracion"])
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


@router.post("/admin/enrollments", summary="Inscribir alumno en asignación", tags=["Administracion"])
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

    course_enrollment = app.main._create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.REGULAR,
        status=models.GradeStatus.CURSANDO,
    )
    db.commit()
    db.refresh(course_enrollment)
    latest_grade = app.main._get_grade_for_course_enrollment(course_enrollment)
    return {
        "detail": "Inscripción exitosa",
        "grade_id": latest_grade.id if latest_grade else None,
        "course_enrollment_id": course_enrollment.id,
        "reassigned": False,
    }


@router.get("/admin/course-enrollments", response_model=list[schemas.CourseEnrollmentWithRelations], summary="Listar carga académica", tags=["Administracion"])
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


@router.post("/admin/course-enrollments", response_model=schemas.CourseEnrollmentWithRelations, summary="Inscribir alumno a materia", tags=["Administracion"])
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

    course_enrollment = app.main._create_admin_course_enrollment(
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


@router.post("/admin/course-enrollments/extraordinary", response_model=schemas.CourseEnrollmentWithRelations, summary="Registrar extraordinario", tags=["Administracion"])
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

    failed_attempt = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.assignment_id == assignment.id,
            models.Grade.attempt_type.in_([models.AttemptType.REGULAR, models.AttemptType.RECURSA]),
            models.Grade.status == models.GradeStatus.REPROBADA,
        )
        .first()
    )
    if not failed_attempt:
        raise HTTPException(status_code=400, detail="El extraordinario requiere un antecedente reprobado en esta misma asignación")

    course_enrollment = app.main._create_admin_course_enrollment(
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


@router.post("/admin/course-enrollments/retake", response_model=schemas.CourseEnrollmentWithRelations, summary="Registrar recursa", tags=["Administracion"])
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

    approved_grade = (
        db.query(models.Grade)
        .filter(
            models.Grade.student_id == student.id,
            models.Grade.subject_id == assignment.subject_id,
            models.Grade.status == models.GradeStatus.APROBADA,
        )
        .first()
    )
    if approved_grade:
        raise HTTPException(status_code=400, detail="La materia ya fue aprobada. No corresponde registrar recursa")

    course_enrollment = app.main._create_admin_course_enrollment(
        db,
        student=student,
        assignment=assignment,
        attempt_type=models.AttemptType.RECURSA,
        status=body.status,
        create_grade_record=body.create_grade_record,
    )
    db.commit()
    db.refresh(course_enrollment)
    return course_enrollment


@router.put("/admin/course-enrollments/{course_enrollment_id}/drop", response_model=schemas.CourseEnrollmentWithRelations, summary="Dar de baja materia", tags=["Administracion"])
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


@router.get("/admin/groups", response_model=list[schemas.GroupSummary], summary="Listar grupos con conteo de alumnos", tags=["Administracion"])
def get_groups(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from sqlalchemy import func
    active_cycle = app.main._get_active_cycle(db)
    tutor_user = aliased(models.User)
    enrollment_join = models.StudentEnrollment.group_id == models.Group.id
    if active_cycle:
        enrollment_join = enrollment_join & (models.StudentEnrollment.cycle_id == active_cycle.id)

    group_career = aliased(models.Career)
    enroll_career = aliased(models.Career)
    rows = (
        db.query(
            models.Group.id.label("group_id"),
            models.Group.name.label("grupo"),
            models.Group.career_id.label("group_career_id"),
            group_career.name.label("group_career_name"),
            func.coalesce(func.min(enroll_career.name), "Sin carrera").label("enroll_carrera"),
            models.Group.modality_id.label("modality_id"),
            models.Group.tutor_id.label("tutor_id"),
            tutor_user.full_name.label("tutor_name"),
            func.count(models.StudentEnrollment.id).label("total"),
        )
        .outerjoin(models.StudentEnrollment, enrollment_join)
        .outerjoin(enroll_career, enroll_career.id == models.StudentEnrollment.career_id)
        .outerjoin(group_career, group_career.id == models.Group.career_id)
        .outerjoin(tutor_user, tutor_user.id == models.Group.tutor_id)
        .filter(models.Group.is_active == True)
        .group_by(
            models.Group.id,
            models.Group.name,
            models.Group.career_id,
            group_career.name,
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
            "carrera": r.group_career_name or r.enroll_carrera or "Sin carrera",
            "total": r.total,
            "modality_id": r.modality_id,
            "tutor_id": r.tutor_id,
            "tutor_name": r.tutor_name,
            "career_id": r.group_career_id,
        }
        for r in rows
    ]


@router.post("/admin/groups", response_model=schemas.GroupWithRelations, summary="Crear grupo", tags=["Administracion"])
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


@router.get("/admin/groups/{group_id}", response_model=schemas.GroupWithRelations, summary="Detalle de grupo", tags=["Administracion"])
def get_group_detail(
    group_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return group


@router.put("/admin/groups/{group_id}", response_model=schemas.GroupWithRelations, summary="Editar grupo", tags=["Administracion"])
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

    if "career_id" in body.model_fields_set:
        if body.career_id is None:
            group.career_id = None
        else:
            career = db.query(models.Career).filter(models.Career.id == body.career_id).first()
            if not career:
                raise HTTPException(status_code=404, detail="Carrera no encontrada")
            group.career_id = career.id

    if "is_active" in body.model_fields_set:
        group.is_active = body.is_active

    db.commit()
    db.refresh(group)
    return group


@router.delete("/admin/groups/{group_id}", summary="Eliminar grupo", tags=["Administracion"])
def delete_group(
    group_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    affected_enrollments = (
        db.query(models.StudentEnrollment)
        .filter(models.StudentEnrollment.group_id == group_id)
        .all()
    )

    affected_student_ids = {enrollment.student_id for enrollment in affected_enrollments if enrollment.student_id}
    for enrollment in affected_enrollments:
        enrollment.group_id = None
        enrollment.change_reason = f"Grupo eliminado: {group.name}"

    if affected_student_ids:
        students = db.query(models.User).filter(models.User.id.in_(affected_student_ids)).all()
        for student in students:
            has_other_group = (
                db.query(models.StudentEnrollment)
                .filter(
                    models.StudentEnrollment.student_id == student.id,
                    models.StudentEnrollment.group_id.isnot(None),
                )
                .first()
            )
            if not has_other_group and student.grupo == group.name:
                student.grupo = None

    db.delete(group)
    db.commit()
    return {"ok": True, "deleted_group_id": group_id, "released_students": len(affected_student_ids)}


@router.get("/admin/groups/{group_id}/students", response_model=list[schemas.StudentEnrollmentWithRelations], summary="Alumnos del grupo", tags=["Administracion"])
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
        active_cycle = app.main._get_active_cycle(db)
        if active_cycle:
            query = query.filter(models.StudentEnrollment.cycle_id == active_cycle.id)

    return query.order_by(models.StudentEnrollment.id.desc()).all()


@router.get("/admin/student-enrollments", response_model=list[schemas.StudentEnrollmentWithRelations], summary="Listar inscripciones por ciclo", tags=["Administracion"])
def get_student_enrollments(
    cycle_id: Optional[int] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = (
        db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
        if cycle_id
        else app.main._get_active_cycle(db)
    )
    if not cycle:
        return []

    return (
        db.query(models.StudentEnrollment)
        .filter(models.StudentEnrollment.cycle_id == cycle.id)
        .order_by(models.StudentEnrollment.id.desc())
        .all()
    )


@router.get("/admin/migration-audit", response_model=schemas.MigrationAuditResult, summary="Auditoria de migracion escolar", tags=["Administracion"])
def get_migration_audit(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    active_cycle = app.main._get_active_cycle(db)

    legacy_students = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.STUDENT)
        .all()
    )
    legacy_students_with_seed_data = [student for student in legacy_students if app.main._has_enrollment_seed_data(student)]
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


@router.put("/admin/student-enrollments/move-group", response_model=schemas.StudentEnrollmentWithRelations, summary="Mover alumno a grupo", tags=["Administracion"])
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
        else app.main._get_active_cycle(db)
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
        enrollment = app.main._sync_student_enrollment_from_legacy(
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
                is_active=student.user_status != models.UserStatus.BAJA and app.main._is_active_enrollment_status(student.enrollment_status),
                change_reason=body.reason,
            )
            app.main._ensure_single_active_enrollment_per_cycle(
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

    group = app.main._get_or_create_group(
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


