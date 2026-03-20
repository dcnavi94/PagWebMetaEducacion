"""add attachment fields to service requests

Revision ID: 20260320_service_request_attachments
Revises: 20260320_group_tutor
Create Date: 2026-03-20 02:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260320_service_request_attachments"
down_revision = "20260320_group_tutor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_requests", sa.Column("attachment_filename", sa.String(), nullable=True))
    op.add_column("service_requests", sa.Column("attachment_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_requests", "attachment_path")
    op.drop_column("service_requests", "attachment_filename")
