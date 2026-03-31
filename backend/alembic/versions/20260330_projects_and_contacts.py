"""Agregar tablas projects y contacts para la página web.

Revision ID: 20260330_projects_and_contacts
Revises: 20260320_charges, 20260320_service_request_attachments
Create Date: 2026-03-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260330_projects_and_contacts"
down_revision: Union[str, Sequence[str]] = (
    "20260320_charges",
    "20260320_service_request_attachments",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("short_description", sa.String(), nullable=True),
        sa.Column(
            "category",
            sa.Enum("portfolio", "evento", name="project_category"),
            nullable=False,
            server_default="portfolio",
        ),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("telefono", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("programa", sa.String(), nullable=True),
        sa.Column("mensaje", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("nuevo", "contactado", "inscrito", name="contact_status"),
            nullable=False,
            server_default="nuevo",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("contacts")
    op.drop_table("projects")
    op.execute("DROP TYPE IF EXISTS contact_status")
    op.execute("DROP TYPE IF EXISTS project_category")
