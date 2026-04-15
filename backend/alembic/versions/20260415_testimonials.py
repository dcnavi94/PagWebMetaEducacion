"""Agregar tablas success_stories y testimonial_reels.

Revision ID: 20260415_testimonials
Revises: 20260415_seed_projects_and_events
Create Date: 2026-04-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260415_testimonials"
down_revision: Union[str, Sequence[str]] = "20260415_seed_projects_and_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "success_stories",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("quote", sa.String(), nullable=False),
        sa.Column("photo_url", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "testimonial_reels",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("badge_text", sa.String(), nullable=False),
        sa.Column("badge_color", sa.String(), nullable=False, server_default="pink"),
        sa.Column("quote", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("video_url", sa.String(), nullable=False),
        sa.Column("poster_url", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Seed historias de éxito
    op.bulk_insert(
        sa.table("success_stories",
            sa.column("name"), sa.column("role"), sa.column("company"),
            sa.column("quote"), sa.column("photo_url"), sa.column("sort_order"), sa.column("is_active"),
        ),
        [
            {"name": "Andrew", "role": "Desarrollador de Software", "company": None,
             "quote": "MetaEducación me dio las bases para trabajar en proyectos de clase mundial. Los retos técnicos que enfrenté aquí fueron clave para mi crecimiento.",
             "photo_url": "assets/andrew.png", "sort_order": 1, "is_active": True},
            {"name": "Michelle", "role": "Ingeniera de Procesos", "company": "Kostal",
             "quote": "La formación práctica me abrió las puertas para trabajar en empresas importantes como Kostal. El enfoque en soluciones reales marca la diferencia.",
             "photo_url": "assets/michelle.png", "sort_order": 2, "is_active": True},
            {"name": "Jose Maria", "role": "Socio y Co-fundador", "company": "Identidad Films",
             "quote": "Desde que estudié aquí supe que quería emprender. Hoy dirijo mi propia casa productora gracias a la visión que MetaEducación fomenta en sus alumnos.",
             "photo_url": "assets/jose_maria.png", "sort_order": 3, "is_active": True},
        ],
    )

    # Seed reels testimoniales
    op.bulk_insert(
        sa.table("testimonial_reels",
            sa.column("badge_text"), sa.column("badge_color"), sa.column("quote"),
            sa.column("description"), sa.column("video_url"), sa.column("poster_url"),
            sa.column("sort_order"), sa.column("is_active"),
        ),
        [
            {"badge_text": "Alumno", "badge_color": "pink",
             "quote": "Llegué con muchas dudas y aquí encontré un lugar donde sí puedo avanzar",
             "description": "Cuando entras a la Legión Axolot, dejas de estudiar solo.",
             "video_url": "assets/rvoe.mp4", "poster_url": "assets/axolotl_student.png",
             "sort_order": 1, "is_active": True},
            {"badge_text": "Padre de familia", "badge_color": "warning",
             "quote": "No solo nos dieron información, nos hicieron sentir acompañados en la decisión",
             "description": "Una familia tranquila apoya mejor a su hijo. Por eso aquí siempre hay alguien disponible para hablar.",
             "video_url": "assets/rvoe.mp4", "poster_url": "assets/axo-polo-success.png",
             "sort_order": 2, "is_active": True},
            {"badge_text": "Profesor", "badge_color": "blue",
             "quote": "Detrás de cada alumno hay una historia, por eso aquí el acompañamiento importa tanto",
             "description": "El seguimiento no es opcional aquí; es parte del modelo educativo.",
             "video_url": "assets/rvoe.mp4", "poster_url": "assets/axolotl_scientist.png",
             "sort_order": 3, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("testimonial_reels")
    op.drop_table("success_stories")
