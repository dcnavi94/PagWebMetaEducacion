"""Agregar tabla extracurricular_courses para cursos administrables en la landing.

Revision ID: 20260415_extracurricular_courses
Revises: 20260330_communities
Create Date: 2026-04-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260415_extracurricular_courses"
down_revision: Union[str, Sequence[str]] = "20260330_communities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extracurricular_courses",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=True),
        sa.Column("color", sa.String(), nullable=False, server_default="blue"),
        sa.Column("icon", sa.String(), nullable=False, server_default="bi-book"),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("whatsapp_text", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Seed: los 6 cursos que estaban hardcodeados en index.html
    op.bulk_insert(
        sa.table(
            "extracurricular_courses",
            sa.column("title"), sa.column("description"), sa.column("level"),
            sa.column("color"), sa.column("icon"), sa.column("image_url"),
            sa.column("whatsapp_text"), sa.column("sort_order"), sa.column("is_active"),
        ),
        [
            {
                "title": "Programación en C++",
                "description": "Fundamentos del lenguaje: variables, ciclos, funciones y estructuras de datos. Ideal para comenzar desde cero con lógica de programación.",
                "level": "Básico",
                "color": "blue",
                "icon": "bi-cpu",
                "image_url": "assets/cyber_network.png",
                "whatsapp_text": "Quiero inscribirme al curso de C++ Básico",
                "sort_order": 1,
                "is_active": True,
            },
            {
                "title": "Programación en C++",
                "description": "Programación orientada a objetos, manejo de memoria, STL y proyectos prácticos para consolidar habilidades de desarrollo en C++.",
                "level": "Intermedio",
                "color": "blue",
                "icon": "bi-code-slash",
                "image_url": "assets/proyecto-software.png",
                "whatsapp_text": "Quiero inscribirme al curso de C++ Intermedio",
                "sort_order": 2,
                "is_active": True,
            },
            {
                "title": "Inglés Técnico",
                "description": "Comunicación oral, escrita y vocabulario técnico en inglés orientado al entorno profesional de tecnología e ingeniería.",
                "level": "Idiomas",
                "color": "green",
                "icon": "bi-translate",
                "image_url": "assets/convenio_idiomas.png",
                "whatsapp_text": "Quiero inscribirme al curso de Inglés",
                "sort_order": 3,
                "is_active": True,
            },
            {
                "title": "Modelado 3D",
                "description": "Creación de modelos tridimensionales con software profesional para diseño industrial, arquitectura y producción digital.",
                "level": "Diseño",
                "color": "purple",
                "icon": "bi-box",
                "image_url": "assets/drone_project.png",
                "whatsapp_text": "Quiero inscribirme al curso de Modelado 3D",
                "sort_order": 4,
                "is_active": True,
            },
            {
                "title": "Soldadura",
                "description": "Técnicas de soldadura MIG, TIG y arco eléctrico con práctica directa en taller. Certificación al concluir el curso.",
                "level": "Industrial",
                "color": "orange",
                "icon": "bi-fire",
                "image_url": "assets/robot_creation.png",
                "whatsapp_text": "Quiero inscribirme al curso de Soldadura",
                "sort_order": 5,
                "is_active": True,
            },
            {
                "title": "Impresión 3D",
                "description": "Configuración de impresoras, diseño de piezas con software de laminado y producción de prototipos funcionales desde cero.",
                "level": "Fabricación",
                "color": "pink",
                "icon": "bi-printer",
                "image_url": "assets/proyecto-robotica.png",
                "whatsapp_text": "Quiero inscribirme al curso de Impresión 3D",
                "sort_order": 6,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("extracurricular_courses")
