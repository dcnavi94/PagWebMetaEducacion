"""Agregar study_plans y study_plan_subjects con backfill inicial.

Revision ID: 20260320_study_plans
Revises: 20260319_groups_enrollments
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "20260320_study_plans"
down_revision: Union[str, Sequence[str], None] = "20260319_groups_enrollments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("career_id", sa.Integer(), sa.ForeignKey("careers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("career_id", "name", name="uq_study_plans_career_name"),
    )

    op.create_table(
        "study_plan_subjects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("study_plan_id", sa.Integer(), sa.ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("semester", sa.String(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("study_plan_id", "subject_id", name="uq_study_plan_subjects_plan_subject"),
    )

    conn = op.get_bind()
    careers = conn.execute(text("SELECT id, name FROM careers ORDER BY id")).fetchall()
    plan_ids_by_career: dict[int, int] = {}

    for career_id, career_name in careers:
        inserted = conn.execute(
            text("""
                INSERT INTO study_plans (career_id, name, version, is_active)
                VALUES (:career_id, :name, '1', true)
                RETURNING id
            """),
            {"career_id": career_id, "name": f"Plan General {career_name}"},
        ).fetchone()
        plan_ids_by_career[career_id] = inserted[0]

    subjects = conn.execute(text("""
        SELECT s.id, s.career, s.semester
        FROM subjects s
        ORDER BY s.career, s.id
    """)).fetchall()

    career_map = {name: cid for cid, name in careers}
    order_counter: dict[int, int] = {}
    for subject_id, subject_career, subject_semester in subjects:
        career_id = career_map.get(subject_career)
        if not career_id:
            continue
        plan_id = plan_ids_by_career.get(career_id)
        if not plan_id:
            continue
        order_counter[plan_id] = order_counter.get(plan_id, 0) + 1
        conn.execute(
            text("""
                INSERT INTO study_plan_subjects (study_plan_id, subject_id, semester, order_index, is_required)
                VALUES (:study_plan_id, :subject_id, :semester, :order_index, true)
                ON CONFLICT (study_plan_id, subject_id) DO NOTHING
            """),
            {
                "study_plan_id": plan_id,
                "subject_id": subject_id,
                "semester": subject_semester,
                "order_index": order_counter[plan_id],
            },
        )


def downgrade() -> None:
    op.drop_table("study_plan_subjects")
    op.drop_table("study_plans")
