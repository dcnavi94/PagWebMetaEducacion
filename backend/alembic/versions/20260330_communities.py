"""Agregar tabla communities para Comunidades de la Legión Axolot.

Revision ID: 20260330_communities
Revises: 20260330_projects_and_contacts
Create Date: 2026-03-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260330_communities"
down_revision: Union[str, Sequence[str]] = "20260330_projects_and_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communities",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("icon", sa.String(), nullable=False, server_default="bi-people-fill"),
        sa.Column(
            "color",
            sa.Enum("blue", "pink", "orange", "purple", "green", "teal", name="community_color"),
            nullable=False,
            server_default="blue",
        ),
        sa.Column("frequency", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Datos iniciales — las 5 comunidades originales
    op.bulk_insert(
        sa.table(
            "communities",
            sa.column("name"), sa.column("description"), sa.column("icon"),
            sa.column("color"), sa.column("frequency"), sa.column("member_count"),
            sa.column("sort_order"), sa.column("is_active"),
        ),
        [
            {"name": "Exploradores Axolot",  "description": "Salidas y experiencias para desarrollar liderazgo, trabajo en equipo y resiliencia entre los alumnos.", "icon": "bi-tree-fill",    "color": "blue",   "frequency": "Trimestral", "member_count": 38, "sort_order": 1, "is_active": True},
            {"name": "Código Axolot",        "description": "Programación aplicada, hackathons y proyectos reales para que los alumnos desarrollen experiencia desde el inicio.", "icon": "bi-code-slash", "color": "pink",   "frequency": "Semanal",    "member_count": 72, "sort_order": 2, "is_active": True},
            {"name": "Estrategia Axolot",    "description": "Análisis, práctica y torneos para fortalecer el pensamiento lógico, la concentración y la toma de decisiones.", "icon": "bi-grid-3x3",   "color": "orange", "frequency": "Mensual",    "member_count": 24, "sort_order": 3, "is_active": True},
            {"name": "Lectura Axolot",       "description": "Lecturas sobre tecnología, emprendimiento y desarrollo personal para ampliar la visión de la comunidad estudiantil.", "icon": "bi-book-fill",  "color": "purple", "frequency": "Mensual",    "member_count": 45, "sort_order": 4, "is_active": True},
            {"name": "English Axolot",       "description": "Sesiones de conversación, vocabulario técnico y preparación para certificaciones que abren oportunidades globales.", "icon": "bi-translate",  "color": "green",  "frequency": "Semanal",    "member_count": 61, "sort_order": 5, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("communities")
    op.execute("DROP TYPE IF EXISTS community_color")
