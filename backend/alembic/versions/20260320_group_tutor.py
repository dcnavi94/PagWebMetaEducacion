"""Agregar tutor_id a groups.

Revision ID: 20260320_group_tutor
Revises: 20260320_grade_locking
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260320_group_tutor"
down_revision: Union[str, Sequence[str], None] = "20260320_grade_locking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("tutor_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_groups_tutor_id_users",
        "groups",
        "users",
        ["tutor_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_groups_tutor_id_users", "groups", type_="foreignkey")
    op.drop_column("groups", "tutor_id")
