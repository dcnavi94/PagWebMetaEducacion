"""Hacer student_id nullable y agregar group_id a student_schedule_entries.

Revision ID: 20260615_schedules_updates
Revises: ddf07225b9bf
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_schedules_updates"
down_revision: Union[str, Sequence[str], None] = "ddf07225b9bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('student_schedule_entries', 'student_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('student_schedule_entries', sa.Column('group_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_student_schedule_entries_group_id_groups',
        'student_schedule_entries',
        'groups',
        ['group_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    op.drop_constraint('fk_student_schedule_entries_group_id_groups', 'student_schedule_entries', type_='foreignkey')
    op.drop_column('student_schedule_entries', 'group_id')
    op.alter_column('student_schedule_entries', 'student_id', existing_type=sa.Integer(), nullable=False)
