"""Agrega valor Proximamente al enum grade_status.

Revision ID: 20260319_proximamente
Revises: 20260319_subject_assignments
Create Date: 2026-03-19

"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260319_proximamente"
down_revision: Union[str, Sequence[str], None] = "20260319_subject_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 12+ permite ADD VALUE dentro de una transacción (no se puede usar en la misma tx)
    op.execute("ALTER TYPE grade_status ADD VALUE IF NOT EXISTS 'Proximamente'")


def downgrade() -> None:
    # PostgreSQL no soporta eliminar valores de un enum directamente.
    # Para downgrade completo habría que recrear el tipo; lo dejamos como no-op seguro.
    pass
