"""Herramientas de backfill para reconciliar modelo legacy con el modelo escolar nuevo."""

from typing import Optional

from sqlalchemy.orm import Session

from . import models


def has_legacy_school_data(student: models.User) -> bool:
    return any(
        [
            student.career_id,
            student.carrera,
            student.modality_id,
            student.modalidad,
            student.semestre,
            student.grupo,
            student.enrollment_status != models.EnrollmentStatus.NO_INSCRITO,
        ]
    )


def is_active_enrollment_status(enrollment_status: models.EnrollmentStatus) -> bool:
    return enrollment_status == models.EnrollmentStatus.INSCRITO


def get_target_cycle(db: Session, cycle_id: Optional[int] = None) -> Optional[models.SchoolCycle]:
    if cycle_id is not None:
        return db.query(models.SchoolCycle).filter(models.SchoolCycle.id == cycle_id).first()
    return (
        db.query(models.SchoolCycle)
        .filter(models.SchoolCycle.is_active == True)
        .order_by(models.SchoolCycle.id.desc())
        .first()
    )


def get_or_create_group_from_legacy(
    db: Session,
    *,
    group_name: Optional[str],
    modality_id: Optional[int],
    counters: dict,
) -> Optional[models.Group]:
    if not group_name or not str(group_name).strip():
        return None

    normalized = str(group_name).strip()
    group = (
        db.query(models.Group)
        .filter(
            models.Group.name == normalized,
            models.Group.modality_id == modality_id,
        )
        .first()
    )
    if group:
        counters["groups_reused"] += 1
        return group

    group = models.Group(name=normalized, modality_id=modality_id, is_active=True)
    db.add(group)
    db.flush()
    counters["groups_created"] += 1
    return group


def backfill_student_enrollments_from_legacy(
    db: Session,
    *,
    cycle_id: Optional[int] = None,
    only_missing: bool = False,
    limit: Optional[int] = None,
    apply_changes: bool = False,
) -> dict:
    cycle = get_target_cycle(db, cycle_id=cycle_id)
    if not cycle:
        raise ValueError("No hay ciclo disponible para ejecutar el backfill")

    counters = {
        "cycle_id": cycle.id,
        "cycle_period": cycle.period,
        "students_scanned": 0,
        "students_with_legacy_data": 0,
        "groups_created": 0,
        "groups_reused": 0,
        "enrollments_created": 0,
        "enrollments_updated": 0,
        "enrollments_unchanged": 0,
        "students_skipped_without_data": 0,
    }

    query = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.STUDENT)
        .order_by(models.User.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)

    students = query.all()
    for student in students:
        counters["students_scanned"] += 1
        if not has_legacy_school_data(student):
            counters["students_skipped_without_data"] += 1
            continue

        counters["students_with_legacy_data"] += 1

        enrollment = (
            db.query(models.StudentEnrollment)
            .filter(
                models.StudentEnrollment.student_id == student.id,
                models.StudentEnrollment.cycle_id == cycle.id,
            )
            .first()
        )
        if only_missing and enrollment:
            counters["enrollments_unchanged"] += 1
            continue

        group = get_or_create_group_from_legacy(
            db,
            group_name=student.grupo,
            modality_id=student.modality_id,
            counters=counters,
        )

        expected_is_active = (
            student.user_status != models.UserStatus.BAJA
            and is_active_enrollment_status(student.enrollment_status)
        )

        changed = False
        if not enrollment:
            enrollment = models.StudentEnrollment(
                student_id=student.id,
                cycle_id=cycle.id,
                career_id=student.career_id,
                modality_id=student.modality_id,
                group_id=group.id if group else None,
                semester=student.semestre,
                enrollment_status=student.enrollment_status,
                is_active=expected_is_active,
                change_reason="Backfill desde modelo legacy",
            )
            db.add(enrollment)
            db.flush()
            counters["enrollments_created"] += 1
            continue

        updates = {
            "career_id": student.career_id,
            "modality_id": student.modality_id,
            "group_id": group.id if group else None,
            "semester": student.semestre,
            "enrollment_status": student.enrollment_status,
            "is_active": expected_is_active,
        }
        for field_name, expected_value in updates.items():
            if getattr(enrollment, field_name) != expected_value:
                setattr(enrollment, field_name, expected_value)
                changed = True

        if changed:
            enrollment.change_reason = "Backfill desde modelo legacy"
            counters["enrollments_updated"] += 1
        else:
            counters["enrollments_unchanged"] += 1

    if apply_changes:
        db.commit()
    else:
        db.rollback()

    return counters
