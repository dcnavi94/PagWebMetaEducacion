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

@router.get("/admin/stats", summary="Estadisticas generales", tags=["Administracion"])
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


@router.get("/admin/reports/grades-export", summary="Exportar calificaciones CSV por ciclo", tags=["Administracion"])
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


@router.get("/admin/reports/enrollment-summary", response_model=list[schemas.EnrollmentSummaryRow], summary="Reporte de matricula activa", tags=["Administracion"])
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

    cycle = app.main._resolve_report_cycle(db, cycle_id)

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
    query = app.main._apply_datetime_range(query, models.StudentEnrollment.created_at, date_from, date_to)

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


@router.get("/admin/reports/grade-outcomes", response_model=list[schemas.GradeOutcomeRow], summary="Reporte de aprobacion y reprobacion", tags=["Administracion"])
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
    cycle = app.main._resolve_report_cycle(db, cycle_id)
    cycle_filter = cycle.id if cycle else None

    grouped: dict[tuple[Optional[int], Optional[str], Optional[str], Optional[str]], dict] = {}
    for grade in grades:
        assignment = grade.assignment
        if not app.main._grade_matches_filters(
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
        group_name_for_assignment = assignment.group.name if assignment and assignment.group else None
        key = (grade.assignment_id, subject_name, teacher_name, cycle_period, group_name_for_assignment)
        bucket = grouped.setdefault(
            key,
            {
                "assignment_id": grade.assignment_id,
                "subject_name": subject_name,
                "teacher_name": teacher_name,
                "cycle_period": cycle_period,
                "group_name": group_name_for_assignment,
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


@router.get("/admin/reports/finance-summary", response_model=schemas.FinanceSummary, summary="Reporte financiero", tags=["Administracion"])
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
    cycle = app.main._resolve_report_cycle(db, cycle_id)
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
    charges_query = app.main._apply_datetime_range(charges_query, models.Charge.due_date, date_from, date_to)

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


@router.get("/admin/reports/blocked-students", response_model=list[schemas.BlockedStudentRow], summary="Reporte de alumnos bloqueados", tags=["Administracion"])
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
    enrollments_query, cycle = app.main._filtered_student_enrollments_query(
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
            and app.main._datetime_in_range(charge.due_date, date_from, date_to)
        ]
        pending_charges = [
            charge for charge in student.charges
            if charge.status != models.PaymentStatus.PAGADO
            and app.main._datetime_in_range(charge.due_date, date_from, date_to)
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


@router.get("/admin/reports/overview", response_model=schemas.AdminOverviewReport, summary="Resumen ejecutivo administrativo", tags=["Administracion"])
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
    enrollments_query, cycle = app.main._filtered_student_enrollments_query(
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
        and app.main._grade_matches_filters(
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
        and app.main._datetime_in_range(charge.due_date, date_from, date_to)
    )
    pending_services = (
        db.query(models.ServiceRequest)
        .filter(
            models.ServiceRequest.student_id.in_(student_ids or [-1]),
            models.ServiceRequest.status != models.ServiceRequestStatus.ENTREGADO,
        )
        .filter(
            models.ServiceRequest.request_date >= app.main._parse_report_datetime(date_from) if date_from else True,
            models.ServiceRequest.request_date <= app.main._parse_report_datetime(date_to, end_of_day=True) if date_to else True,
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


@router.get("/admin/reports/enrollment-status", response_model=list[schemas.EnrollmentStatusRow], summary="Resumen de estatus de inscripcion", tags=["Administracion"])
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

    query, _ = app.main._filtered_student_enrollments_query(
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


@router.get("/admin/reports/teacher-workload", response_model=list[schemas.TeacherWorkloadRow], summary="Carga academica por docente", tags=["Administracion"])
def get_teacher_workload_report(
    cycle_id: Optional[int] = None,
    career: Optional[str] = None,
    semester: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    cycle = app.main._resolve_report_cycle(db, cycle_id)
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
            if not app.main._datetime_in_range(cycle_start, date_from, date_to):
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


@router.get("/admin/reports/academic-risk", response_model=list[schemas.AcademicRiskRow], summary="Alumnos en riesgo academico", tags=["Administracion"])
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
    enrollments_query, _ = app.main._filtered_student_enrollments_query(
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
            if app.main._grade_matches_filters(
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


@router.get("/admin/reports/service-summary", response_model=list[schemas.ServiceSummaryRow], summary="Resumen de servicios escolares", tags=["Administracion"])
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
    cycle = app.main._resolve_report_cycle(db, cycle_id)
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
    query = app.main._apply_datetime_range(query, models.ServiceRequest.request_date, date_from, date_to)

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


@router.get("/admin/reports/charge-breakdown", response_model=list[schemas.ChargeBreakdownRow], summary="Desglose financiero por tipo de cargo", tags=["Administracion"])
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
    cycle = app.main._resolve_report_cycle(db, cycle_id)
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
    query = app.main._apply_datetime_range(query, models.Charge.due_date, date_from, date_to)

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


@router.get("/admin/reports/aging-balances", response_model=list[schemas.AgingBalanceRow], summary="Antiguedad de saldos", tags=["Administracion"])
def get_aging_balances_report(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    charges = (
        db.query(models.Charge)
        .options(joinedload(models.Charge.student))
        .options(joinedload(models.Charge.payments))
        .filter(models.Charge.status != models.PaymentStatus.PAGADO)
        .all()
    )
    
    student_balances = {}
    for c in charges:
        if not c.student:
            continue
            
        sid = c.student_id
        if sid not in student_balances:
            student_balances[sid] = {
                "student_id": sid,
                "username": c.student.username,
                "full_name": c.student.full_name,
                "days_1_30": 0.0,
                "days_31_60": 0.0,
                "days_61_90": 0.0,
                "days_90_plus": 0.0,
                "total_overdue": 0.0
            }
            
        if not c.due_date:
            continue
            
        days_overdue = (now - c.due_date).days
        amount_due = c.amount
        
        if c.payments:
            paid = sum(p.amount for p in c.payments if p.status == models.PaymentStatus.PAGADO)
            amount_due -= paid
            if amount_due <= 0:
                continue
                
        if days_overdue <= 0:
            continue
        elif days_overdue <= 30:
            student_balances[sid]["days_1_30"] += amount_due
        elif days_overdue <= 60:
            student_balances[sid]["days_31_60"] += amount_due
        elif days_overdue <= 90:
            student_balances[sid]["days_61_90"] += amount_due
        else:
            student_balances[sid]["days_90_plus"] += amount_due
            
        student_balances[sid]["total_overdue"] += amount_due
        
    result = [b for b in student_balances.values() if b["total_overdue"] > 0]
    return sorted(result, key=lambda x: x["total_overdue"], reverse=True)


@router.get("/admin/reports/income-flow", response_model=list[schemas.IncomeFlowRow], summary="Flujo de ingresos", tags=["Administracion"])
def get_income_flow_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Payment)
        .filter(models.Payment.status == models.PaymentStatus.PAGADO)
        .filter(models.Payment.payment_date != None)
    )
    query = app.main._apply_datetime_range(query, models.Payment.payment_date, date_from, date_to)
    
    payments = query.all()
    
    grouped = {}
    for p in payments:
        if not p.payment_date or not p.payment_method:
            continue
            
        p_date = p.payment_date.strftime("%Y-%m-%d")
        method = p.payment_method.value if hasattr(p.payment_method, 'value') else p.payment_method
        
        key = (p_date, method)
        if key not in grouped:
            grouped[key] = {
                "payment_date": p_date,
                "payment_method": method,
                "total_amount": 0.0,
                "count": 0
            }
        grouped[key]["total_amount"] += p.amount
        grouped[key]["count"] += 1
        
    return sorted(grouped.values(), key=lambda x: (x["payment_date"], x["payment_method"]), reverse=True)

