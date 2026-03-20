"""Agregar groups y student_enrollments con backfill desde users.

Revision ID: 20260319_groups_enrollments
Revises: 20260319_proximamente
Create Date: 2026-03-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "20260319_groups_enrollments"
down_revision: Union[str, Sequence[str], None] = "20260319_proximamente"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("modality_id", sa.Integer(), sa.ForeignKey("modalities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("name", "modality_id", name="uq_groups_name_modality"),
    )
    op.create_index("ix_groups_name", "groups", ["name"], unique=False)

    enrollment_status_enum = sa.Enum(
        "Inscrito",
        "No Inscrito",
        "Baja Temporal",
        "Baja Definitiva",
        "Graduado",
        name="student_enrollment_status",
    )
    enrollment_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "student_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("school_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("career_id", sa.Integer(), sa.ForeignKey("careers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("modality_id", sa.Integer(), sa.ForeignKey("modalities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("semester", sa.String(), nullable=True),
        sa.Column("enrollment_status", enrollment_status_enum, nullable=False, server_default="No Inscrito"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("change_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("student_id", "cycle_id", name="uq_student_enrollment_student_cycle"),
    )

    conn = op.get_bind()
    active_cycle = conn.execute(
        text("SELECT id FROM school_cycles WHERE is_active = true ORDER BY id DESC LIMIT 1")
    ).fetchone()

    if active_cycle:
        active_cycle_id = active_cycle[0]
        students = conn.execute(text("""
            SELECT id, career_id, modality_id, semestre, grupo, enrollment_status, user_status
            FROM users
            WHERE role = 'student'
        """)).fetchall()

        group_cache: dict[tuple[str, Union[int, None]], int] = {}

        for row in students:
            student_id, career_id, modality_id, semester, group_name, enrollment_status, user_status = row

            has_seed = any([
                career_id is not None,
                modality_id is not None,
                semester not in (None, ""),
                group_name not in (None, ""),
                enrollment_status != "No Inscrito",
            ])
            if not has_seed:
                continue

            group_id = None
            normalized_group = group_name.strip() if isinstance(group_name, str) else None
            if normalized_group:
                cache_key = (normalized_group, modality_id)
                group_id = group_cache.get(cache_key)
                if group_id is None:
                    inserted = conn.execute(
                        text("""
                            INSERT INTO groups (name, modality_id, is_active)
                            VALUES (:name, :modality_id, true)
                            RETURNING id
                        """),
                        {"name": normalized_group, "modality_id": modality_id},
                    ).fetchone()
                    group_id = inserted[0]
                    group_cache[cache_key] = group_id

            conn.execute(
                text("""
                    INSERT INTO student_enrollments (
                        student_id,
                        cycle_id,
                        career_id,
                        modality_id,
                        group_id,
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
                        :group_id,
                        :semester,
                        :enrollment_status,
                        :is_active,
                        :change_reason
                    )
                    ON CONFLICT (student_id, cycle_id) DO NOTHING
                """),
                {
                    "student_id": student_id,
                    "cycle_id": active_cycle_id,
                    "career_id": career_id,
                    "modality_id": modality_id,
                    "group_id": group_id,
                    "semester": semester,
                    "enrollment_status": enrollment_status,
                    "is_active": user_status != "Baja",
                    "change_reason": "Backfill inicial desde users",
                },
            )


def downgrade() -> None:
    op.drop_table("student_enrollments")
    op.drop_index("ix_groups_name", table_name="groups")
    op.drop_table("groups")
    sa.Enum(name="student_enrollment_status").drop(op.get_bind(), checkfirst=True)
