"""Agrega constraint de rango para score en grades.

Revision ID: 20260318_grade_score_check
Revises: 20260318_enums_ondelete
Create Date: 2026-03-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260318_grade_score_check"
down_revision: Union[str, Sequence[str], None] = "20260318_enums_ondelete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_grades_score_range",
        "grades",
        "score >= 0 AND score <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_grades_score_range",
        "grades",
        type_="check",
    )
