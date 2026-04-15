"""Seed inicial de proyectos de portafolio y eventos institucionales.

Revision ID: 20260415_seed_projects_and_events
Revises: 20260415_extracurricular_courses
Create Date: 2026-04-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260415_seed_projects_and_events"
down_revision: Union[str, Sequence[str]] = "20260415_extracurricular_courses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_projects = sa.table(
    "projects",
    sa.column("title"),
    sa.column("short_description"),
    sa.column("category"),
    sa.column("image_url"),
    sa.column("date"),
    sa.column("location"),
    sa.column("is_active"),
)


def upgrade() -> None:
    # ── Portafolio de alumnos ──────────────────────────────────────────────
    op.bulk_insert(
        _projects,
        [
            {
                "title": "Vehículo Autónomo IoT",
                "short_description": "Robot construido desde cero con sensores programados por nuestros alumnos de 4to cuatrimestre de Ing. en Telemática.",
                "category": "portfolio",
                "image_url": "assets/robot_creation.png",
                "date": None,
                "location": None,
                "is_active": True,
            },
            {
                "title": "App Móvil de Gestión",
                "short_description": "Plataforma móvil diseñada con UI/UX de vanguardia y arquitectura en la nube. Proyecto integrador de Ing. en Software.",
                "category": "portfolio",
                "image_url": "assets/app_mockup.png",
                "date": None,
                "location": None,
                "is_active": True,
            },
            {
                "title": "Implementación Cibersegura",
                "short_description": "Configuración de servidores y protección de datos en el laboratorio tecnológico. Proyecto colaborativo Telemática & Software.",
                "category": "portfolio",
                "image_url": "assets/cyber_network.png",
                "date": None,
                "location": None,
                "is_active": True,
            },
            {
                "title": "Dron de Rescate AI",
                "short_description": "Quadcopter programado para misiones de reconocimiento usando AI. Proyecto de estadía de Ing. en Telemática.",
                "category": "portfolio",
                "image_url": "assets/drone_project.png",
                "date": None,
                "location": None,
                "is_active": True,
            },
            {
                "title": "Startup E-commerce",
                "short_description": "Tienda online funcional con pagos descentralizados desarrollada como proyecto integrador por alumnos de Ing. en Software.",
                "category": "portfolio",
                "image_url": "assets/ecommerce_app.png",
                "date": None,
                "location": None,
                "is_active": True,
            },
            {
                "title": "Prototipo Smart Home",
                "short_description": "Sistema domótico programado en C++ usando microcontroladores en el laboratorio de preparatoria — área de Informática.",
                "category": "portfolio",
                "image_url": "assets/smart_home_board.png",
                "date": None,
                "location": None,
                "is_active": True,
            },
        ],
    )

    # ── Eventos institucionales ────────────────────────────────────────────
    op.bulk_insert(
        _projects,
        [
            {
                "title": "Hackathon Axolot 2026",
                "short_description": "48 horas de desarrollo intensivo. Compite, aprende y gana premios en nuestro hackathon anual.",
                "category": "evento",
                "image_url": "assets/evento-hackathon.png",
                "date": "2026-05-10 09:00:00",
                "location": "Campus MetaEducación — San José Iturbide",
                "is_active": True,
            },
            {
                "title": "Expo Proyectos Cuatrimestre",
                "short_description": "Los mejores proyectos del cuatrimestre en exhibición para empresas y familias. Entrada libre.",
                "category": "evento",
                "image_url": "assets/events.png",
                "date": "2026-06-20 10:00:00",
                "location": "Auditorio MetaEducación",
                "is_active": True,
            },
            {
                "title": "Día de Puertas Abiertas",
                "short_description": "Conoce las instalaciones, habla con alumnos y docentes, y resuelve todas tus dudas antes de inscribirte.",
                "category": "evento",
                "image_url": "assets/axolotl_student.png",
                "date": "2026-05-24 10:00:00",
                "location": "Campus MetaEducación — San José Iturbide",
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    # Eliminar solo los registros sembrados (por título)
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM projects WHERE title IN ("
            "'Vehículo Autónomo IoT','App Móvil de Gestión','Implementación Cibersegura',"
            "'Dron de Rescate AI','Startup E-commerce','Prototipo Smart Home',"
            "'Hackathon Axolot 2026','Expo Proyectos Cuatrimestre','Día de Puertas Abiertas'"
            ")"
        )
    )
