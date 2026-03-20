"""Agrega enums de status y ON DELETE en llaves foráneas.

Revision ID: 20260318_enums_ondelete
Revises: add_teacher_to_subjects
Create Date: 2026-03-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260318_enums_ondelete"
down_revision: Union[str, Sequence[str], None] = "add_teacher_to_subjects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


payment_status = sa.Enum("Pendiente", "Pagado", "Vencido", name="payment_status")
grade_status = sa.Enum("Cursando", "Aprobada", "Reprobada", name="grade_status")
service_status = sa.Enum("En Proceso", "Listo", "Entregado", name="service_status")
user_role = sa.Enum("admin", "teacher", "student", "services", name="user_role")


def upgrade() -> None:
    bind = op.get_bind()
    payment_status.create(bind, checkfirst=True)
    grade_status.create(bind, checkfirst=True)
    service_status.create(bind, checkfirst=True)
    user_role.create(bind, checkfirst=True)

    op.execute("UPDATE users SET role = 'student' WHERE role IS NULL")
    op.execute("UPDATE payments SET status = 'Pendiente' WHERE status IS NULL")
    op.execute("UPDATE grades SET status = 'Cursando' WHERE status IS NULL")
    op.execute("UPDATE service_requests SET status = 'En Proceso' WHERE status IS NULL")

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "role",
            existing_type=sa.String(),
            type_=user_role,
            nullable=False,
            server_default="student",
            postgresql_using="role::user_role",
        )
        batch_op.drop_constraint("users_career_id_fkey", type_="foreignkey")
        batch_op.drop_constraint("users_modality_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_users_career_id",
            "careers",
            ["career_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_users_modality_id",
            "modalities",
            ["modality_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column(
            "student_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(),
            type_=payment_status,
            nullable=False,
            server_default="Pendiente",
            postgresql_using="status::payment_status",
        )
        batch_op.drop_constraint("payments_student_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_payments_student_id_users",
            "users",
            ["student_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("subjects") as batch_op:
        batch_op.drop_constraint("fk_subjects_teacher_id_users", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_subjects_teacher_id_users",
            "users",
            ["teacher_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("grades") as batch_op:
        batch_op.alter_column(
            "student_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "subject_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(),
            type_=grade_status,
            nullable=False,
            server_default="Cursando",
            postgresql_using="status::grade_status",
        )
        batch_op.drop_constraint("grades_student_id_fkey", type_="foreignkey")
        batch_op.drop_constraint("grades_subject_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_grades_student_id_users",
            "users",
            ["student_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_grades_subject_id_subjects",
            "subjects",
            ["subject_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("service_requests") as batch_op:
        batch_op.alter_column(
            "student_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(),
            type_=service_status,
            nullable=False,
            server_default="En Proceso",
            postgresql_using="status::service_status",
        )
        batch_op.drop_constraint("service_requests_student_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_service_requests_student_id_users",
            "users",
            ["student_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("service_requests") as batch_op:
        batch_op.drop_constraint("fk_service_requests_student_id_users", type_="foreignkey")
        batch_op.create_foreign_key(
            "service_requests_student_id_fkey",
            "users",
            ["student_id"],
            ["id"],
        )
        batch_op.alter_column(
            "status",
            existing_type=service_status,
            type_=sa.String(),
            nullable=True,
        )
        batch_op.alter_column(
            "student_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

    with op.batch_alter_table("grades") as batch_op:
        batch_op.drop_constraint("fk_grades_subject_id_subjects", type_="foreignkey")
        batch_op.drop_constraint("fk_grades_student_id_users", type_="foreignkey")
        batch_op.create_foreign_key(
            "grades_subject_id_fkey",
            "subjects",
            ["subject_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "grades_student_id_fkey",
            "users",
            ["student_id"],
            ["id"],
        )
        batch_op.alter_column(
            "status",
            existing_type=grade_status,
            type_=sa.String(),
            nullable=True,
        )
        batch_op.alter_column(
            "subject_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.alter_column(
            "student_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

    with op.batch_alter_table("subjects") as batch_op:
        batch_op.drop_constraint("fk_subjects_teacher_id_users", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_subjects_teacher_id_users",
            "users",
            ["teacher_id"],
            ["id"],
        )

    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint("fk_payments_student_id_users", type_="foreignkey")
        batch_op.create_foreign_key(
            "payments_student_id_fkey",
            "users",
            ["student_id"],
            ["id"],
        )
        batch_op.alter_column(
            "status",
            existing_type=payment_status,
            type_=sa.String(),
            nullable=True,
        )
        batch_op.alter_column(
            "student_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("fk_users_modality_id", type_="foreignkey")
        batch_op.drop_constraint("fk_users_career_id", type_="foreignkey")
        batch_op.create_foreign_key(
            "users_modality_id_fkey",
            "modalities",
            ["modality_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "users_career_id_fkey",
            "careers",
            ["career_id"],
            ["id"],
        )
        batch_op.alter_column(
            "role",
            existing_type=user_role,
            type_=sa.String(),
            nullable=True,
        )

    service_status.drop(op.get_bind(), checkfirst=True)
    grade_status.drop(op.get_bind(), checkfirst=True)
    payment_status.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
