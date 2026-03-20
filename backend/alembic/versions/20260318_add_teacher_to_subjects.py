"""Agregar columna teacher_id a subjects.

Revision ID: add_teacher_to_subjects
Revises: 050c14d17469
Create Date: 2026-03-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_teacher_to_subjects"
down_revision: Union[str, Sequence[str], None] = "050c14d17469"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subjects", sa.Column("teacher_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_subjects_teacher_id_users",
        "subjects",
        "users",
        ["teacher_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_subjects_teacher_id_users", "subjects", type_="foreignkey")
    op.drop_column("subjects", "teacher_id")
