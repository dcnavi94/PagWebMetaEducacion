"""Agregar SubjectAssignment y attempt_type en grades; quitar teacher_id de subjects.

Revision ID: 20260319_subject_assignments
Revises: 20260318_grade_score_check
Create Date: 2026-03-19

Cambios:
1. Crea tabla subject_assignments (materia + docente + ciclo).
2. Migra teacher_id existente en subjects a subject_assignments (usando ciclo activo si existe).
3. Elimina teacher_id de subjects.
4. Agrega assignment_id (nullable) y attempt_type a grades.
5. Vincula grades existentes con su assignment_id donde sea posible.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "20260319_subject_assignments"
down_revision: Union[str, Sequence[str], None] = "20260318_grade_score_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Crear tabla subject_assignments
    op.create_table(
        "subject_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("school_cycles.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("subject_id", "teacher_id", "cycle_id", name="uq_assignment_subject_teacher_cycle"),
    )

    # 2. Obtener el ciclo activo (para migrar datos existentes)
    active_cycle = conn.execute(
        text("SELECT id FROM school_cycles WHERE is_active = true ORDER BY id DESC LIMIT 1")
    ).fetchone()
    active_cycle_id = active_cycle[0] if active_cycle else None

    # 3. Migrar subjects con teacher_id a subject_assignments
    subjects_with_teacher = conn.execute(
        text("SELECT id, teacher_id FROM subjects WHERE teacher_id IS NOT NULL")
    ).fetchall()

    for subject_id, teacher_id in subjects_with_teacher:
        conn.execute(
            text("""
                INSERT INTO subject_assignments (subject_id, teacher_id, cycle_id)
                VALUES (:subject_id, :teacher_id, :cycle_id)
                ON CONFLICT DO NOTHING
            """),
            {"subject_id": subject_id, "teacher_id": teacher_id, "cycle_id": active_cycle_id},
        )

    # 4. Agregar assignment_id a grades (nullable para retrocompatibilidad)
    op.add_column("grades", sa.Column(
        "assignment_id",
        sa.Integer(),
        sa.ForeignKey("subject_assignments.id", ondelete="SET NULL"),
        nullable=True,
    ))

    # 5. Agregar attempt_type a grades con default 'Regular'
    op.add_column("grades", sa.Column(
        "attempt_type",
        sa.String(length=20),
        nullable=False,
        server_default="Regular",
    ))

    # 6. Vincular grades existentes con su assignment_id donde subject.teacher_id existe
    if active_cycle_id:
        conn.execute(text("""
            UPDATE grades g
            SET assignment_id = sa.id
            FROM subject_assignments sa
            WHERE g.subject_id = sa.subject_id
              AND sa.cycle_id = :cycle_id
              AND g.assignment_id IS NULL
        """), {"cycle_id": active_cycle_id})

    # 7. Eliminar teacher_id de subjects
    # Intenta el nombre estandar de SQLAlchemy primero, luego el nombre de la migracion anterior
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    fk_names = [fk['name'] for fk in inspector.get_foreign_keys('subjects')]
    fk_to_drop = None
    for candidate in ("fk_subjects_teacher_id_users", "subjects_teacher_id_fkey"):
        if candidate in fk_names:
            fk_to_drop = candidate
            break
    if fk_to_drop:
        op.drop_constraint(fk_to_drop, "subjects", type_="foreignkey")
    op.drop_column("subjects", "teacher_id")

    # 8. Cambiar constraint de calificación: de 0-100 a escala 0-10
    op.drop_constraint("ck_grades_score_range", "grades", type_="check")
    op.create_check_constraint("ck_grades_score_range", "grades", "score >= 0 AND score <= 10")


def downgrade() -> None:
    # Restaurar teacher_id en subjects
    op.add_column("subjects", sa.Column("teacher_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_subjects_teacher_id_users",
        "subjects",
        "users",
        ["teacher_id"],
        ["id"],
    )

    # Restaurar teacher_id desde subject_assignments
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE subjects s
        SET teacher_id = sa.teacher_id
        FROM subject_assignments sa
        WHERE s.id = sa.subject_id
          AND sa.teacher_id IS NOT NULL
    """))

    op.drop_column("grades", "attempt_type")
    op.drop_column("grades", "assignment_id")
    op.drop_table("subject_assignments")

    op.drop_constraint("ck_grades_score_range", "grades", type_="check")
    op.create_check_constraint("ck_grades_score_range", "grades", "score >= 0 AND score <= 100")
