"""Agregar tablas thesis_records y social_service_records para el Pasaporte Digital.

Revision ID: 20260426_pasaporte_digital
Revises: 20260415_testimonials
Create Date: 2026-04-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260426_pasaporte_digital"
down_revision: Union[str, Sequence[str]] = "20260415_testimonials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

THESIS_STATUS_VALUES = [
    "Sin Iniciar", "Perfil", "Protocolo", "Marco Teorico",
    "Diseño", "Implementacion", "Pruebas", "Redaccion",
    "Revisiones", "Defensa", "Titulado",
]
SS_STATUS_VALUES = ["Pendiente", "Registrado", "En Servicio", "Completado", "Liberado"]
SS_TYPE_VALUES = ["Universitario", "Seguro Social"]


def upgrade() -> None:
    conn = op.get_bind()

    # Create enum types only if they don't exist
    sa.Enum(*SS_STATUS_VALUES, name="social_service_status").create(conn, checkfirst=True)
    sa.Enum(*SS_TYPE_VALUES, name="social_service_type").create(conn, checkfirst=True)

    # thesis_status: create or replace with the canonical 11 values
    conn.execution_options(isolation_level="AUTOCOMMIT")
    has_type = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'thesis_status'")
    ).scalar()
    if has_type:
        # Migrate column to text, drop old enum, recreate with new values
        conn.execute(sa.text("ALTER TABLE thesis_records ALTER COLUMN status DROP DEFAULT"))
        conn.execute(sa.text("ALTER TABLE thesis_records ALTER COLUMN status TYPE text"))
        conn.execute(sa.text("DROP TYPE thesis_status"))
    vals = ", ".join(f"'{v}'" for v in THESIS_STATUS_VALUES)
    conn.execute(sa.text(f"CREATE TYPE thesis_status AS ENUM ({vals})"))
    conn.execute(sa.text(
        "ALTER TABLE thesis_records ALTER COLUMN status TYPE thesis_status "
        "USING status::thesis_status"
    ))
    conn.execute(sa.text(
        "ALTER TABLE thesis_records ALTER COLUMN status SET DEFAULT 'Sin Iniciar'"
    ))
    conn.execution_options(isolation_level="READ_COMMITTED")

    # Create tables if they don't exist yet
    inspector = sa.inspect(conn)
    if "thesis_records" not in inspector.get_table_names():
        thesis_status_col = sa.Enum(*THESIS_STATUS_VALUES, name="thesis_status", create_type=False)
        op.create_table(
            "thesis_records",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("director", sa.String(), nullable=True),
            sa.Column("institution", sa.String(), nullable=True),
            sa.Column("status", thesis_status_col, nullable=False, server_default="Sin Iniciar"),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if "social_service_records" not in inspector.get_table_names():
        ss_status_col = sa.Enum(*SS_STATUS_VALUES, name="social_service_status", create_type=False)
        ss_type_col = sa.Enum(*SS_TYPE_VALUES, name="social_service_type", create_type=False)
        op.create_table(
            "social_service_records",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("service_type", ss_type_col, nullable=False),
            sa.Column("institution", sa.String(), nullable=True),
            sa.Column("status", ss_status_col, nullable=False, server_default="Pendiente"),
            sa.Column("hours_required", sa.Integer(), nullable=True, server_default="480"),
            sa.Column("hours_completed", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("start_date", sa.DateTime(), nullable=True),
            sa.Column("end_date", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("student_id", "service_type", name="uq_social_service_student_type"),
        )


def downgrade() -> None:
    op.drop_table("social_service_records")
    op.drop_table("thesis_records")
    sa.Enum(name="social_service_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="social_service_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="thesis_status").drop(op.get_bind(), checkfirst=True)
