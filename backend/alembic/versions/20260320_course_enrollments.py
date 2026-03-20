"""Agregar course_enrollments y vincular grades existentes.

Revision ID: 20260320_course_enrollments
Revises: 20260320_study_plans
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "20260320_course_enrollments"
down_revision: Union[str, Sequence[str], None] = "20260320_study_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    attempt_enum = sa.Enum("Regular", "Extemporaneo", name="course_enrollment_attempt_type")
    status_enum = sa.Enum("Cursando", "Aprobada", "Reprobada", "Proximamente", name="course_enrollment_status")
    attempt_enum.create(op.get_bind(), checkfirst=True)
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "course_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("student_enrollment_id", sa.Integer(), sa.ForeignKey("student_enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("subject_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_type", attempt_enum, nullable=False, server_default="Regular"),
        sa.Column("status", status_enum, nullable=False, server_default="Cursando"),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("dropped_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("student_enrollment_id", "assignment_id", "attempt_type", name="uq_course_enrollment_student_assignment_attempt"),
    )
    op.add_column("grades", sa.Column("course_enrollment_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_grades_course_enrollment_id_course_enrollments",
        "grades",
        "course_enrollments",
        ["course_enrollment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    conn = op.get_bind()
    active_cycle = conn.execute(
        text("SELECT id FROM school_cycles WHERE is_active = true ORDER BY id DESC LIMIT 1")
    ).fetchone()
    active_cycle_id = active_cycle[0] if active_cycle else None

    grades = conn.execute(text("""
        SELECT
            g.id,
            g.student_id,
            g.assignment_id,
            g.attempt_type,
            g.status,
            u.career_id,
            u.modality_id,
            u.semestre,
            u.enrollment_status,
            u.user_status
        FROM grades g
        JOIN users u ON u.id = g.student_id
        WHERE g.assignment_id IS NOT NULL
        ORDER BY g.id
    """)).fetchall()

    student_enrollment_cache: dict[tuple[int, int], int] = {}
    course_enrollment_cache: dict[tuple[int, int, str], int] = {}

    for row in grades:
        (
            grade_id,
            student_id,
            assignment_id,
            attempt_type,
            status,
            career_id,
            modality_id,
            semester,
            enrollment_status,
            user_status,
        ) = row

        assignment_cycle = conn.execute(
            text("SELECT cycle_id FROM subject_assignments WHERE id = :assignment_id"),
            {"assignment_id": assignment_id},
        ).fetchone()
        cycle_id = assignment_cycle[0] if assignment_cycle and assignment_cycle[0] is not None else active_cycle_id
        if cycle_id is None:
            continue

        enrollment_key = (student_id, cycle_id)
        student_enrollment_id = student_enrollment_cache.get(enrollment_key)
        if student_enrollment_id is None:
            existing_enrollment = conn.execute(
                text("""
                    SELECT id
                    FROM student_enrollments
                    WHERE student_id = :student_id AND cycle_id = :cycle_id
                """),
                {"student_id": student_id, "cycle_id": cycle_id},
            ).fetchone()
            if existing_enrollment:
                student_enrollment_id = existing_enrollment[0]
            else:
                inserted_enrollment = conn.execute(
                    text("""
                        INSERT INTO student_enrollments (
                            student_id,
                            cycle_id,
                            career_id,
                            modality_id,
                            semester,
                            enrollment_status,
                            is_active,
                            change_reason
                        )
                        VALUES (
                            :student_id,
                            :cycle_id,
                            :career_id,
                            :modality_id,
                            :semester,
                            :enrollment_status,
                            :is_active,
                            :change_reason
                        )
                        RETURNING id
                    """),
                    {
                        "student_id": student_id,
                        "cycle_id": cycle_id,
                        "career_id": career_id,
                        "modality_id": modality_id,
                        "semester": semester,
                        "enrollment_status": enrollment_status,
                        "is_active": user_status != "Baja",
                        "change_reason": "Backfill desde grades",
                    },
                ).fetchone()
                student_enrollment_id = inserted_enrollment[0]
            student_enrollment_cache[enrollment_key] = student_enrollment_id

        course_key = (student_enrollment_id, assignment_id, attempt_type)
        course_enrollment_id = course_enrollment_cache.get(course_key)
        if course_enrollment_id is None:
            existing_course = conn.execute(
                text("""
                    SELECT id
                    FROM course_enrollments
                    WHERE student_enrollment_id = :student_enrollment_id
                      AND assignment_id = :assignment_id
                      AND attempt_type = :attempt_type
                """),
                {
                    "student_enrollment_id": student_enrollment_id,
                    "assignment_id": assignment_id,
                    "attempt_type": attempt_type,
                },
            ).fetchone()
            if existing_course:
                course_enrollment_id = existing_course[0]
            else:
                inserted_course = conn.execute(
                    text("""
                        INSERT INTO course_enrollments (
                            student_enrollment_id,
                            assignment_id,
                            attempt_type,
                            status
                        )
                        VALUES (
                            :student_enrollment_id,
                            :assignment_id,
                            :attempt_type,
                            :status
                        )
                        RETURNING id
                    """),
                    {
                        "student_enrollment_id": student_enrollment_id,
                        "assignment_id": assignment_id,
                        "attempt_type": attempt_type,
                        "status": status,
                    },
                ).fetchone()
                course_enrollment_id = inserted_course[0]
            course_enrollment_cache[course_key] = course_enrollment_id

        conn.execute(
            text("""
                UPDATE grades
                SET course_enrollment_id = :course_enrollment_id
                WHERE id = :grade_id
            """),
            {"course_enrollment_id": course_enrollment_id, "grade_id": grade_id},
        )


def downgrade() -> None:
    op.drop_constraint("fk_grades_course_enrollment_id_course_enrollments", "grades", type_="foreignkey")
    op.drop_column("grades", "course_enrollment_id")
    op.drop_table("course_enrollments")
    sa.Enum(name="course_enrollment_attempt_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="course_enrollment_status").drop(op.get_bind(), checkfirst=True)
