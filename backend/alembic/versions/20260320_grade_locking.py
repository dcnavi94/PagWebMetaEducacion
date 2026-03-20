"""Agregar recorded_at y teacher_locked a grades.

Revision ID: 20260320_grade_locking
Revises: 20260320_course_enrollments
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260320_grade_locking"
down_revision: Union[str, Sequence[str], None] = "20260320_course_enrollments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("grades", sa.Column("recorded_at", sa.DateTime(), nullable=True))
    op.add_column(
        "grades",
        sa.Column("teacher_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("grades", "teacher_locked")
    op.drop_column("grades", "recorded_at")
