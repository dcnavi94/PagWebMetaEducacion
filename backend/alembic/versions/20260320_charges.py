"""Agregar charges y vinculo desde payments.

Revision ID: 20260320_charges
Revises: 20260320_group_tutor
Create Date: 2026-03-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260320_charges"
down_revision: Union[str, Sequence[str], None] = "20260320_group_tutor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


charge_type_enum = sa.Enum(
    "Colegiatura",
    "Inscripcion",
    "Reinscripcion",
    "Tramite",
    "Recargo",
    "Beca",
    "Otro",
    name="charge_type",
)

charge_status_enum = sa.Enum(
    "Pendiente",
    "Pagado",
    "Vencido",
    name="charge_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    charge_type_enum.create(bind, checkfirst=True)
    charge_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "charges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("student_enrollment_id", sa.Integer(), nullable=True),
        sa.Column("charge_type", charge_type_enum, nullable=False, server_default="Otro"),
        sa.Column("concept", sa.String(), nullable=False),
        sa.Column("period_label", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("due_date", sa.DateTime(), nullable=False),
        sa.Column("status", charge_status_enum, nullable=False, server_default="Pendiente"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_enrollment_id"], ["student_enrollments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_charges_id"), "charges", ["id"], unique=False)

    op.add_column("payments", sa.Column("charge_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_payments_charge_id_charges",
        "payments",
        "charges",
        ["charge_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_payments_charge_id_charges", "payments", type_="foreignkey")
    op.drop_column("payments", "charge_id")
    op.drop_index(op.f("ix_charges_id"), table_name="charges")
    op.drop_table("charges")

    bind = op.get_bind()
    charge_status_enum.drop(bind, checkfirst=True)
    charge_type_enum.drop(bind, checkfirst=True)
