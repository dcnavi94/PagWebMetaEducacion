"""Tests de los endpoints de la API."""
import io
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from app import models, import_csv
from app.admin_backfill import backfill_student_enrollments_from_legacy
from app.curriculum import get_configured_curriculum, get_public_curriculum, get_subject_credits
from app.curriculum_credits import CURRICULUM_CREDITS
from app.config import settings


class TestRoot:
    """Tests del endpoint raíz."""

    def test_root_returns_welcome(self, client):
        """GET / debe devolver mensaje de bienvenida."""
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()
        assert "Plataforma" in response.json()["message"]


class TestAuth:
    """Tests de autenticación."""

    def test_login_success(self, client, admin_user):
        """Login correcto devuelve token."""
        response = client.post(
            "/token",
            data={"username": admin_user.username, "password": "admin123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, admin_user):
        """Login con contraseña incorrecta devuelve 401."""
        response = client.post(
            "/token",
            data={"username": admin_user.username, "password": "wrong"},
        )
        assert response.status_code == 401


class TestCatalogs:
    """Catálogos (carreras y modalidades)."""

    def test_list_careers_requires_auth(self, client, auth_headers_student):
        resp = client.get("/catalogs/careers", headers=auth_headers_student)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_career_admin(self, client, auth_headers_admin):
        resp = client.post(
            "/admin/catalogs/careers",
            headers=auth_headers_admin,
            json={"name": "Ingeniería Civil", "description": "Construcción"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Ingeniería Civil"

    def test_create_modality_admin(self, client, auth_headers_admin):
        resp = client.post(
            "/admin/catalogs/modalities",
            headers=auth_headers_admin,
            json={"name": "En línea"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "En línea"

    def test_login_nonexistent_user(self, client):
        """Login con usuario inexistente devuelve 401."""
        response = client.post(
            "/token",
            data={"username": "noexiste", "password": "cualquiera"},
        )
        assert response.status_code == 401

    def test_public_curriculum_loader_reads_software_page(self):
        curriculum = get_public_curriculum("Ingeniería en Software")
        assert curriculum
        assert any(item["semester"] == "1" for item in curriculum)
        assert any("Software" in item["name"] or "Programación" in item["name"] for item in curriculum)

    def test_public_curriculum_loader_returns_empty_for_unknown_career(self):
        assert get_public_curriculum("Carrera inexistente") == []

    def test_configured_curriculum_is_grouped_by_semester(self):
        curriculum = get_configured_curriculum("Ingeniería en Software")
        assert curriculum
        assert any(item["semester"] == "1" for item in curriculum)
        assert any("credits" in item for item in curriculum)

    def test_curriculum_credits_default_to_eight(self):
        assert get_subject_credits("Ingeniería en Software", "Materia Inventada") == 8


class TestUsersMe:
    """Tests del perfil de usuario."""

    def test_get_me_requires_auth(self, client):
        """GET /users/me sin token devuelve 401."""
        response = client.get("/users/me")
        assert response.status_code == 401

    def test_get_me_returns_user(self, client, auth_headers_student, student_user):
        """GET /users/me con token devuelve el usuario."""
        response = client.get("/users/me", headers=auth_headers_student)
        assert response.status_code == 200
        assert response.json()["username"] == student_user.username
        assert response.json()["full_name"] == student_user.full_name


class TestAdminStats:
    """Tests de estadísticas de administración."""

    def test_admin_stats_requires_admin(self, client, auth_headers_student):
        """GET /admin/stats como alumno devuelve 403."""
        response = client.get("/admin/stats", headers=auth_headers_student)
        assert response.status_code == 403

    def test_admin_stats_returns_data(self, client, auth_headers_admin):
        """GET /admin/stats como admin devuelve estadísticas."""
        response = client.get("/admin/stats", headers=auth_headers_admin)
        assert response.status_code == 200
        data = response.json()
        assert "total_students" in data
        assert "total_income" in data
        assert "pending_services" in data
        assert "total_teachers" in data


class TestAdminReports:
    """Reportes operativos de la fase 7."""

    def test_overview_report_returns_operational_metrics(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="O1", is_active=True)
        subject = models.Subject(name="Estadistica", credits=8, semester="3", career="Ingeniería")
        db_session.add_all([cycle, group, subject])
        db_session.flush()
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="3",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        assignment = models.SubjectAssignment(subject_id=subject.id, teacher_id=teacher_user.id, cycle_id=cycle.id)
        db_session.add_all([enrollment, assignment])
        db_session.flush()
        course_enrollment = models.CourseEnrollment(
            student_enrollment_id=enrollment.id,
            assignment_id=assignment.id,
            attempt_type=models.AttemptType.REGULAR,
            status=models.GradeStatus.APROBADA,
        )
        db_session.add(course_enrollment)
        db_session.flush()
        db_session.add(
            models.Grade(
                student_id=student_user.id,
                subject_id=subject.id,
                assignment_id=assignment.id,
                course_enrollment_id=course_enrollment.id,
                score=9.0,
                status=models.GradeStatus.APROBADA,
            )
        )
        db_session.commit()

        response = client.get("/admin/reports/overview", headers=auth_headers_admin)

        assert response.status_code == 200
        body = response.json()
        assert body["total_students"] >= 1
        assert body["teachers_with_assignments"] >= 1
        assert body["average_final_score"] >= 9.0

    def test_enrollment_status_report_can_filter_by_group(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="Filtro-A", is_active=True)
        other_group = models.Group(name="Filtro-B", is_active=True)
        other_student = models.User(
            username="2024777",
            email="otro_alumno@test.com",
            full_name="Otro Alumno",
            hashed_password="hash",
            role=models.UserRole.STUDENT,
        )
        db_session.add_all([cycle, group, other_group, other_student])
        db_session.flush()
        db_session.add_all([
            models.StudentEnrollment(
                student_id=student_user.id,
                cycle_id=cycle.id,
                group_id=group.id,
                semester="1",
                enrollment_status=models.EnrollmentStatus.INSCRITO,
                is_active=True,
            ),
            models.StudentEnrollment(
                student_id=other_student.id,
                cycle_id=cycle.id,
                group_id=other_group.id,
                semester="1",
                enrollment_status=models.EnrollmentStatus.BAJA_TEMPORAL,
                is_active=False,
            ),
        ])
        db_session.commit()

        response = client.get("/admin/reports/enrollment-status?group_name=Filtro-A", headers=auth_headers_admin)

        assert response.status_code == 200
        rows = response.json()
        assert rows == [{"enrollment_status": "Inscrito", "total_students": 1}]

    def test_enrollment_summary_report_returns_rows(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="R1", is_active=True)
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle=cycle,
            group=group,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        db_session.add_all([cycle, group, enrollment])
        db_session.commit()

        response = client.get("/admin/reports/enrollment-summary", headers=auth_headers_admin)

        assert response.status_code == 200
        rows = response.json()
        assert any(row["group_name"] == "R1" and row["total_students"] >= 1 for row in rows)

    def test_grade_outcomes_report_returns_approval_counts(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        student_two = models.User(
            username="2024998",
            email="alumno2@test.com",
            full_name="Alumno Dos",
            hashed_password="hash",
            role=models.UserRole.STUDENT,
        )
        subject = models.Subject(name="Algebra", credits=8, semester="1", career="Ingeniería")
        db_session.add_all([cycle, student_two, subject])
        db_session.flush()
        assignment = models.SubjectAssignment(subject_id=subject.id, teacher_id=teacher_user.id, cycle_id=cycle.id)
        db_session.add(assignment)
        db_session.flush()
        db_session.add_all(
            [
                models.Grade(
                    student_id=student_user.id,
                    subject_id=subject.id,
                    assignment_id=assignment.id,
                    score=8.0,
                    status=models.GradeStatus.APROBADA,
                ),
                models.Grade(
                    student_id=student_two.id,
                    subject_id=subject.id,
                    assignment_id=assignment.id,
                    score=5.0,
                    status=models.GradeStatus.REPROBADA,
                ),
            ]
        )
        db_session.commit()

        response = client.get("/admin/reports/grade-outcomes", headers=auth_headers_admin)

        assert response.status_code == 200
        rows = response.json()
        assert any(
            row["subject_name"] == "Algebra"
            and row["approved_count"] == 1
            and row["failed_count"] == 1
            for row in rows
        )

    def test_finance_summary_report_returns_amounts(self, client, auth_headers_admin, db_session, student_user):
        now = datetime.utcnow()
        db_session.add_all(
            [
                models.Charge(
                    student_id=student_user.id,
                    charge_type=models.ChargeType.TUITION,
                    concept="Colegiatura Abril",
                    period_label="2026-04",
                    amount=1000,
                    due_date=now - timedelta(days=5),
                    status=models.PaymentStatus.VENCIDO,
                ),
                models.Charge(
                    student_id=student_user.id,
                    charge_type=models.ChargeType.ENROLLMENT,
                    concept="Inscripcion 2026-1",
                    period_label="2026-1",
                    amount=1500,
                    due_date=now + timedelta(days=5),
                    status=models.PaymentStatus.PAGADO,
                ),
            ]
        )
        db_session.commit()

        response = client.get("/admin/reports/finance-summary", headers=auth_headers_admin)

        assert response.status_code == 200
        body = response.json()
        assert body["total_charges"] >= 2
        assert body["paid_amount"] >= 1500
        assert body["overdue_amount"] >= 1000

    def test_finance_and_service_reports_support_date_filters(self, client, auth_headers_admin, db_session, student_user):
        now = datetime.utcnow()
        db_session.add_all(
            [
                models.Charge(
                    student_id=student_user.id,
                    charge_type=models.ChargeType.TUITION,
                    concept="Colegiatura Antigua",
                    period_label="2026-01",
                    amount=900,
                    due_date=now - timedelta(days=40),
                    status=models.PaymentStatus.VENCIDO,
                ),
                models.Charge(
                    student_id=student_user.id,
                    charge_type=models.ChargeType.TUITION,
                    concept="Colegiatura Vigente",
                    period_label="2026-03",
                    amount=1200,
                    due_date=now - timedelta(days=2),
                    status=models.PaymentStatus.VENCIDO,
                ),
                models.ServiceRequest(
                    student_id=student_user.id,
                    type="Constancia",
                    status=models.ServiceRequestStatus.EN_PROCESO,
                    request_date=now - timedelta(days=25),
                ),
                models.ServiceRequest(
                    student_id=student_user.id,
                    type="Constancia",
                    status=models.ServiceRequestStatus.LISTO,
                    request_date=now - timedelta(days=1),
                ),
            ]
        )
        db_session.commit()

        date_from = (now - timedelta(days=7)).date().isoformat()
        finance_response = client.get(f"/admin/reports/finance-summary?date_from={date_from}", headers=auth_headers_admin)
        service_response = client.get(f"/admin/reports/service-summary?date_from={date_from}", headers=auth_headers_admin)

        assert finance_response.status_code == 200
        finance = finance_response.json()
        assert finance["total_charges"] == 1
        assert finance["overdue_amount"] == 1200

        assert service_response.status_code == 200
        service_rows = service_response.json()
        assert len(service_rows) == 1
        assert service_rows[0]["status"] == models.ServiceRequestStatus.LISTO.value

    def test_blocked_students_report_returns_overdue_info(self, client, auth_headers_admin, db_session, student_user):
        student_user.user_status = models.UserStatus.BLOQUEADO
        db_session.add(
            models.Charge(
                student_id=student_user.id,
                charge_type=models.ChargeType.TUITION,
                concept="Colegiatura Marzo",
                period_label="2026-03",
                amount=1100,
                due_date=datetime.utcnow() - timedelta(days=10),
                status=models.PaymentStatus.VENCIDO,
            )
        )
        db_session.commit()

        response = client.get("/admin/reports/blocked-students", headers=auth_headers_admin)

        assert response.status_code == 200
        rows = response.json()
        assert any(
            row["username"] == student_user.username
            and row["overdue_charges"] >= 1
            and row["overdue_amount"] >= 1100
            for row in rows
        )

    def test_teacher_workload_and_service_summary_reports_return_rows(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="Carga-1", is_active=True)
        subject = models.Subject(name="Logica", credits=8, semester="1", career="Ingeniería")
        db_session.add_all([cycle, group, subject])
        db_session.flush()
        assignment = models.SubjectAssignment(subject_id=subject.id, teacher_id=teacher_user.id, cycle_id=cycle.id)
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="1",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        service = models.ServiceRequest(
            student_id=student_user.id,
            type="Kardex",
            status=models.ServiceRequestStatus.EN_PROCESO,
            request_date=datetime.utcnow() + timedelta(days=1),
        )
        db_session.add_all([assignment, enrollment, service])
        db_session.flush()
        db_session.add(
            models.CourseEnrollment(
                student_enrollment_id=enrollment.id,
                assignment_id=assignment.id,
                attempt_type=models.AttemptType.REGULAR,
                status=models.GradeStatus.CURSANDO,
            )
        )
        db_session.commit()

        workload_response = client.get("/admin/reports/teacher-workload", headers=auth_headers_admin)
        service_response = client.get("/admin/reports/service-summary", headers=auth_headers_admin)

        assert workload_response.status_code == 200
        assert any(row["teacher_username"] == teacher_user.username for row in workload_response.json())
        assert service_response.status_code == 200
        assert any(row["service_type"] == "Kardex" for row in service_response.json())


class TestAdminStudents:
    """Tests de gestión de alumnos."""

    def test_list_students_requires_admin(self, client, auth_headers_student):
        """GET /admin/students como alumno devuelve 403."""
        response = client.get("/admin/students", headers=auth_headers_student)
        assert response.status_code == 403

    def test_list_students_empty(self, client, auth_headers_admin):
        """GET /admin/students sin alumnos devuelve lista vacía."""
        response = client.get("/admin/students", headers=auth_headers_admin)
        assert response.status_code == 200
        assert response.json() == []

    def test_create_student(self, client, auth_headers_admin):
        """POST /admin/students crea un alumno."""
        response = client.post(
            "/admin/students",
            headers=auth_headers_admin,
            json={
                "username": "2024999",
                "email": "nuevo@test.com",
                "full_name": "Nuevo Alumno",
                "password": "pass123",
                "role": "student",
                "carrera": "Ingeniería",
                "semestre": "1",
                "grupo": "B",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "2024999"
        assert data["role"] == "student"

    def test_create_student_assigns_curriculum_subjects(self, client, auth_headers_admin, db_session, monkeypatch):
        monkeypatch.setitem(
            CURRICULUM_CREDITS,
            "Ingeniería en Software",
            {
                "1": [{"name": "Programacion I", "credits": 8}],
                "2": [{"name": "Bases de Datos", "credits": 8}],
            },
        )
        software_subjects = [
            models.Subject(name="Programacion I", credits=8, semester="1", career="Ingeniería en Software"),
            models.Subject(name="Bases de Datos", credits=8, semester="2", career="Ingeniería en Software"),
        ]
        telematica_subject = models.Subject(
            name="Redes I",
            credits=8,
            semester="1",
            career="Ingeniería en Telemática",
        )
        db_session.add_all([*software_subjects, telematica_subject])
        db_session.commit()

        response = client.post(
            "/admin/students",
            headers=auth_headers_admin,
            json={
                "username": "2024888",
                "email": "curricula@test.com",
                "full_name": "Alumno Curricula",
                "password": "pass123",
                "role": "student",
                "carrera": "Ingeniería en Software",
                "semestre": "1",
                "grupo": "A",
            },
        )

        assert response.status_code == 200
        created_student = response.json()
        grades = (
            db_session.query(models.Grade)
            .filter(models.Grade.student_id == created_student["id"])
            .all()
        )

        assert len(grades) == 2
        assert {grade.subject.name for grade in grades} == {"Programacion I", "Bases de Datos"}
        assert {grade.status for grade in grades} == {
            models.GradeStatus.CURSANDO,
            models.GradeStatus.PROXIMAMENTE,
        }

    def test_create_student_bootstraps_subjects_from_public_curriculum(self, client, auth_headers_admin, db_session, monkeypatch):
        monkeypatch.setitem(
            CURRICULUM_CREDITS,
            "Ingeniería en Telemática",
            {
                "1": [{"name": "Materia Base 1", "credits": 12}],
                "2": [{"name": "Materia Base 2", "credits": 6}],
            },
        )
        monkeypatch.setattr(
            "app.curriculum.get_public_curriculum",
            lambda career_name: [
                {"name": "Materia Base 1", "semester": "1"},
                {"name": "Materia Base 2", "semester": "2"},
            ] if career_name == "Ingeniería en Telemática" else [],
        )

        response = client.post(
            "/admin/students",
            headers=auth_headers_admin,
            json={
                "username": "2024777",
                "email": "bootstrap@test.com",
                "full_name": "Alumno Bootstrap",
                "password": "pass123",
                "role": "student",
                "carrera": "Ingeniería en Telemática",
                "semestre": "1",
                "grupo": "A",
            },
        )

        assert response.status_code == 200
        db_session.expire_all()
        created_student = (
            db_session.query(models.User)
            .filter(models.User.username == "2024777")
            .first()
        )
        subjects = db_session.query(models.Subject).filter(models.Subject.career == "Ingeniería en Telemática").all()
        grades = db_session.query(models.Grade).filter(models.Grade.student_id == created_student.id).all()

        assert {subject.name for subject in subjects} == {"Materia Base 1", "Materia Base 2"}
        assert {subject.name: subject.credits for subject in subjects} == {"Materia Base 1": 12, "Materia Base 2": 6}
        assert len(grades) == 2

    def test_create_student_completes_partial_curriculum_when_career_already_has_one_subject(
        self, client, auth_headers_admin, db_session, monkeypatch
    ):
        db_session.add(
            models.Subject(
                name="PRUEBA",
                credits=5,
                semester="2",
                career="Ingeniería en Software",
            )
        )
        db_session.commit()

        monkeypatch.setitem(
            CURRICULUM_CREDITS,
            "Ingeniería en Software",
            {
                "1": [{"name": "Programacion I", "credits": 8}],
                "2": [{"name": "PRUEBA", "credits": 5}],
                "3": [{"name": "Bases de Datos", "credits": 8}],
            },
        )

        response = client.post(
            "/admin/students",
            headers=auth_headers_admin,
            json={
                "username": "2024666",
                "email": "partial@test.com",
                "full_name": "Alumno Parcial",
                "password": "pass123",
                "role": "student",
                "carrera": "Ingeniería en Software",
                "semestre": "1",
                "grupo": "A",
            },
        )

        assert response.status_code == 200
        created_student = response.json()
        subjects = (
            db_session.query(models.Subject)
            .filter(models.Subject.career == "Ingeniería en Software")
            .all()
        )
        grades = (
            db_session.query(models.Grade)
            .filter(models.Grade.student_id == created_student["id"])
            .all()
        )

        assert {subject.name for subject in subjects} == {"PRUEBA", "Programacion I", "Bases de Datos"}
        assert {grade.subject.name for grade in grades} == {"PRUEBA", "Programacion I", "Bases de Datos"}

    def test_create_student_accepts_semester_labels_from_admin_ui(self, client, auth_headers_admin, db_session, monkeypatch):
        monkeypatch.setitem(
            CURRICULUM_CREDITS,
            "Ingeniería en Software",
            {
                "1": [{"name": "Programacion I", "credits": 8}],
                "2": [{"name": "Bases de Datos", "credits": 8}],
            },
        )
        db_session.add_all([
            models.Subject(name="Programacion I", credits=8, semester="1", career="Ingeniería en Software"),
            models.Subject(name="Bases de Datos", credits=8, semester="2", career="Ingeniería en Software"),
        ])
        db_session.commit()

        response = client.post(
            "/admin/students",
            headers=auth_headers_admin,
            json={
                "username": "2024887",
                "email": "semestre-label@test.com",
                "full_name": "Alumno Semestre Label",
                "password": "pass123",
                "role": "student",
                "carrera": "Ingeniería en Software",
                "semestre": "1er Semestre",
                "grupo": "A",
            },
        )

        assert response.status_code == 200
        assert response.json()["semestre"] == "1er Semestre"

    def test_update_student_semester_refreshes_curriculum_statuses(self, client, auth_headers_admin, db_session, monkeypatch):
        monkeypatch.setitem(
            CURRICULUM_CREDITS,
            "Ingeniería en Software",
            {
                "1": [{"name": "Programacion I", "credits": 8}],
                "2": [{"name": "Bases de Datos", "credits": 8}],
            },
        )
        db_session.add_all([
            models.Subject(name="Programacion I", credits=8, semester="1", career="Ingeniería en Software"),
            models.Subject(name="Bases de Datos", credits=8, semester="2", career="Ingeniería en Software"),
        ])
        db_session.commit()

        create_response = client.post(
            "/admin/students",
            headers=auth_headers_admin,
            json={
                "username": "2024665",
                "email": "refresh-curriculum@test.com",
                "full_name": "Alumno Refresh",
                "password": "pass123",
                "role": "student",
                "carrera": "Ingeniería en Software",
                "semestre": "1",
                "grupo": "A",
            },
        )
        assert create_response.status_code == 200

        update_response = client.put(
            "/admin/students/2024665",
            headers=auth_headers_admin,
            json={"semestre": "2do Semestre"},
        )
        assert update_response.status_code == 200

        created_student = db_session.query(models.User).filter_by(username="2024665").first()
        grades = db_session.query(models.Grade).filter(models.Grade.student_id == created_student.id).all()
        statuses = {grade.subject.name: grade.status for grade in grades}

        assert update_response.json()["semestre"] == "2do Semestre"
        assert statuses["Programacion I"] == models.GradeStatus.REPROBADA
        assert statuses["Bases de Datos"] == models.GradeStatus.CURSANDO

    def test_create_student_duplicate_username(self, client, auth_headers_admin, student_user):
        """POST /admin/students con matrícula duplicada devuelve 400."""
        response = client.post(
            "/admin/students",
            headers=auth_headers_admin,
            json={
                "username": student_user.username,
                "email": "otro@test.com",
                "full_name": "Otro",
                "password": "pass123",
                "role": "student",
            },
        )
        assert response.status_code == 400

    def test_get_student_full_profile(self, client, auth_headers_admin, student_user):
        resp = client.get(f"/admin/students/{student_user.username}/full", headers=auth_headers_admin)
        assert resp.status_code == 200
        assert resp.json()["username"] == student_user.username

    def test_enroll_student_creates_course_enrollment(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(
            name="Bases de Datos",
            credits=8,
            semester="2",
            career="Ingeniería",
        )
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.commit()

        response = client.post(
            "/admin/enrollments",
            headers=auth_headers_admin,
            json={"username": student_user.username, "assignment_id": assignment.id},
        )

        assert response.status_code == 200
        grade = (
            db_session.query(models.Grade)
            .filter(models.Grade.student_id == student_user.id, models.Grade.assignment_id == assignment.id)
            .first()
        )
        assert grade is not None
        assert grade.course_enrollment_id is not None

        course_enrollment = (
            db_session.query(models.CourseEnrollment)
            .filter(models.CourseEnrollment.id == grade.course_enrollment_id)
            .first()
        )
        assert course_enrollment is not None
        assert course_enrollment.assignment_id == assignment.id


class TestAdminSubjects:
    """Tests de gestión de materias."""

    def test_list_subjects(self, client, auth_headers_admin):
        """GET /admin/subjects devuelve lista de materias."""
        response = client.get("/admin/subjects", headers=auth_headers_admin)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_subject(self, client, auth_headers_admin):
        """POST /admin/subjects crea una materia."""
        response = client.post(
            "/admin/subjects",
            headers=auth_headers_admin,
            json={
                "name": "Matemáticas",
                "credits": 8,
                "semester": "1er Semestre",
                "career": "Ingeniería",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Matemáticas"
        assert data["credits"] == 8

    def test_update_subject_assigns_teacher(self, client, auth_headers_admin, teacher_user):
        create_resp = client.post(
            "/admin/subjects",
            headers=auth_headers_admin,
            json={
                "name": "Historia",
                "credits": 6,
                "semester": "3",
                "career": "Humanidades",
            },
        )
        subject_id = create_resp.json()["id"]

        update_resp = client.put(
            f"/admin/subjects/{subject_id}",
            headers=auth_headers_admin,
            json={"teacher_username": teacher_user.username},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["teacher_id"] == teacher_user.id


class TestStudentGrades:
    """Tests de calificaciones del alumno."""

    def test_get_grades_returns_list(self, client, auth_headers_student):
        """GET /users/me/grades devuelve lista de calificaciones."""
        response = client.get("/users/me/grades", headers=auth_headers_student)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_grades_includes_course_enrollment_without_grade(
        self, client, auth_headers_student, db_session, student_user, teacher_user
    ):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Redes", credits=6, semester="2", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        student_enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
        )
        db_session.add_all([assignment, student_enrollment])
        db_session.flush()

        course_enrollment = models.CourseEnrollment(
            student_enrollment_id=student_enrollment.id,
            assignment_id=assignment.id,
            attempt_type=models.AttemptType.REGULAR,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(course_enrollment)
        db_session.commit()

        response = client.get("/users/me/grades", headers=auth_headers_student)

        assert response.status_code == 200
        grades = response.json()
        assert any(
            item["description"] == "Redes"
            and item["course_enrollment_id"] == course_enrollment.id
            and item["status"] == "Cursando"
            and item["score"] is None
            for item in grades
        )

    def test_get_grades_hides_unassigned_curriculum_placeholders(
        self, client, auth_headers_student, db_session, student_user
    ):
        subject = models.Subject(name="Materia Placeholder", credits=6, semester="6", career="Ingeniería")
        db_session.add(subject)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            attempt_type=models.AttemptType.REGULAR,
            status=models.GradeStatus.PROXIMAMENTE,
        )
        db_session.add(grade)
        db_session.commit()

        response = client.get("/users/me/grades", headers=auth_headers_student)

        assert response.status_code == 200
        grades = response.json()
        assert not any(item["description"] == "Materia Placeholder" for item in grades)


class TestStudentPayments:
    """Tests de pagos del alumno."""

    def test_get_payments_returns_list(self, client, auth_headers_student):
        """GET /users/me/payments devuelve lista de pagos."""
        response = client.get("/users/me/payments", headers=auth_headers_student)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestTeacherEndpoints:
    """Tests de endpoints de docente."""

    def test_teacher_subjects_requires_teacher(self, client, auth_headers_student):
        """GET /teacher/subjects como alumno devuelve 403."""
        response = client.get("/teacher/subjects", headers=auth_headers_student)
        assert response.status_code == 403

    def test_teacher_subjects_returns_list(self, client, auth_headers_teacher):
        """GET /teacher/subjects como docente devuelve materias."""
        response = client.get("/teacher/subjects", headers=auth_headers_teacher)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_teacher_can_list_students_by_subject(self, client, auth_headers_teacher, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Algebra Lineal", credits=7, semester="2", career="Ingenieria")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        student_enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
        )
        db_session.add_all([assignment, student_enrollment])
        db_session.flush()

        course_enrollment = models.CourseEnrollment(
            student_enrollment_id=student_enrollment.id,
            assignment_id=assignment.id,
            attempt_type=models.AttemptType.REGULAR,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(course_enrollment)
        db_session.commit()

        resp = client.get(f"/teacher/students/{assignment.id}", headers=auth_headers_teacher)
        assert resp.status_code == 200
        assert any(
            item["username"] == student_user.username
            and item["course_enrollment_id"] == course_enrollment.id
            and item["grade_id"] is None
            for item in resp.json()
        )


class TestTeacherGrades:
    """Flujos específicos de docente sobre calificaciones."""

    def test_teacher_can_update_grade(self, client, auth_headers_teacher, db_session, student_user, teacher_user):
        """PUT /teacher/grades/{id} permite actualizar calificación y estado."""
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(
            name="Fisica",
            credits=6,
            semester="2",
            career="Ingeniería",
        )
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=assignment.id,
            score=5,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(grade)
        db_session.commit()

        response = client.put(
            f"/teacher/grades/{grade.id}",
            headers=auth_headers_teacher,
            json={"score": 8.5, "status": "Aprobada"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["score"] == 8.5
        assert body["status"] == "Aprobada"

    def test_teacher_cannot_update_grade_twice(self, client, auth_headers_teacher, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Quimica", credits=6, semester="2", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=assignment.id,
            score=None,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(grade)
        db_session.commit()

        first = client.put(
            f"/teacher/grades/{grade.id}",
            headers=auth_headers_teacher,
            json={"score": 7.5},
        )
        assert first.status_code == 200

        second = client.put(
            f"/teacher/grades/{grade.id}",
            headers=auth_headers_teacher,
            json={"score": 8.0},
        )
        assert second.status_code == 403

    def test_teacher_grade_of_five_is_failed(self, client, auth_headers_teacher, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Algebra", credits=6, semester="2", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=assignment.id,
            score=None,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(grade)
        db_session.commit()

        response = client.put(
            f"/teacher/grades/{grade.id}",
            headers=auth_headers_teacher,
            json={"score": 5},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "Reprobada"

    def test_admin_can_correct_teacher_locked_grade(self, client, auth_headers_teacher, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Estadistica", credits=6, semester="2", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=assignment.id,
            score=None,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(grade)
        db_session.commit()

        first = client.put(
            f"/teacher/grades/{grade.id}",
            headers=auth_headers_teacher,
            json={"score": 7.0},
        )
        assert first.status_code == 200

        admin_fix = client.put(
            f"/admin/grades/{grade.id}",
            headers=auth_headers_admin,
            json={"score": 9.0},
        )
        assert admin_fix.status_code == 200
        assert admin_fix.json()["score"] == 9.0

    def test_teacher_receives_admin_notification(self, client, auth_headers_teacher, auth_headers_admin, db_session, teacher_user):
        notice = client.post(
            "/admin/notifications/messages",
            headers=auth_headers_admin,
            json={
                "recipient_role": "teacher",
                "recipient_username": teacher_user.username,
                "title": "Cierre de actas",
                "message": "Recuerda capturar tus calificaciones hoy.",
                "level": "warning",
            },
        )
        assert notice.status_code == 200

        response = client.get("/teacher/notifications", headers=auth_headers_teacher)
        assert response.status_code == 200
        items = response.json()["items"]
        assert any(item["title"] == "Cierre de actas" for item in items)

    def test_student_receives_admin_notification(self, client, auth_headers_admin, auth_headers_student, db_session, student_user):
        notice = client.post(
            "/admin/notifications/messages",
            headers=auth_headers_admin,
            json={
                "recipient_role": "student",
                "recipient_username": student_user.username,
                "title": "Aviso escolar",
                "message": "Revisa tu portal para novedades administrativas.",
                "level": "info",
            },
        )
        assert notice.status_code == 200

        response = client.get("/users/me/notifications", headers=auth_headers_student)
        assert response.status_code == 200
        items = response.json()["items"]
        assert any(item["title"] == "Aviso escolar" for item in items)

class TestAdminCourseEnrollments:
    """Carga académica administrativa sobre CourseEnrollment."""

    def test_admin_can_create_course_enrollment(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Calculo I", credits=8, semester="1", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.commit()

        response = client.post(
            "/admin/course-enrollments",
            headers=auth_headers_admin,
            json={"username": student_user.username, "assignment_id": assignment.id},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["assignment_id"] == assignment.id
        assert body["attempt_type"] == "Regular"

        course_enrollment = db_session.query(models.CourseEnrollment).filter_by(id=body["id"]).first()
        assert course_enrollment is not None
        linked_grade = db_session.query(models.Grade).filter_by(course_enrollment_id=course_enrollment.id).first()
        assert linked_grade is not None
        assert linked_grade.assignment_id == assignment.id

    def test_admin_cannot_duplicate_same_course_opportunity(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Calculo II", credits=8, semester="2", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.commit()

        first = client.post(
            "/admin/course-enrollments",
            headers=auth_headers_admin,
            json={"username": student_user.username, "assignment_id": assignment.id},
        )
        assert first.status_code == 200

        second = client.post(
            "/admin/course-enrollments",
            headers=auth_headers_admin,
            json={"username": student_user.username, "assignment_id": assignment.id},
        )
        assert second.status_code == 400

    def test_admin_can_create_extraordinary_course_enrollment(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Fisica II", credits=8, semester="2", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.flush()

        failed_grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=assignment.id,
            attempt_type=models.AttemptType.REGULAR,
            score=4.0,
            status=models.GradeStatus.REPROBADA,
        )
        db_session.add(failed_grade)
        db_session.commit()

        response = client.post(
            "/admin/course-enrollments/extraordinary",
            headers=auth_headers_admin,
            json={"username": student_user.username, "assignment_id": assignment.id},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["attempt_type"] == "Extemporaneo"
        linked_grade = db_session.query(models.Grade).filter_by(course_enrollment_id=body["id"]).first()
        assert linked_grade is not None
        assert linked_grade.attempt_type == models.AttemptType.EXTEMPORANEO

    def test_admin_can_drop_course_enrollment(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Quimica I", credits=8, semester="1", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        student_enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            semester="1",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
        )
        db_session.add_all([assignment, student_enrollment])
        db_session.flush()

        course_enrollment = models.CourseEnrollment(
            student_enrollment_id=student_enrollment.id,
            assignment_id=assignment.id,
            attempt_type=models.AttemptType.REGULAR,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(course_enrollment)
        db_session.commit()

        response = client.put(
            f"/admin/course-enrollments/{course_enrollment.id}/drop",
            headers=auth_headers_admin,
            json={},
        )

        assert response.status_code == 200
        db_session.refresh(course_enrollment)
        assert course_enrollment.dropped_at is not None

    def test_admin_can_create_retake_with_failed_history(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle_old = models.SchoolCycle(
            period="2025-3",
            start_date=datetime.utcnow() - timedelta(days=200),
            end_date=datetime.utcnow() - timedelta(days=90),
            monthly_amount=1000,
            is_active=False,
        )
        cycle_new = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Estatica", credits=8, semester="2", career="Ingeniería")
        db_session.add_all([cycle_old, cycle_new, subject])
        db_session.flush()

        old_assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle_old.id,
        )
        new_assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle_new.id,
        )
        db_session.add_all([old_assignment, new_assignment])
        db_session.flush()

        old_grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=old_assignment.id,
            attempt_type=models.AttemptType.REGULAR,
            score=5.0,
            status=models.GradeStatus.REPROBADA,
        )
        db_session.add(old_grade)
        db_session.commit()

        response = client.post(
            "/admin/course-enrollments/retake",
            headers=auth_headers_admin,
            json={"username": student_user.username, "assignment_id": new_assignment.id},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["assignment_id"] == new_assignment.id
        assert body["attempt_type"] == "Recursa"


class TestAdminGroups:
    """Gestión de grupos reales."""

    def test_admin_can_create_group_with_tutor(self, client, auth_headers_admin, db_session, teacher_user):
        response = client.post(
            "/admin/groups",
            headers=auth_headers_admin,
            json={"name": "A", "tutor_id": teacher_user.id, "is_active": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "A"
        assert body["tutor_id"] == teacher_user.id

    def test_admin_can_update_group_tutor(self, client, auth_headers_admin, db_session, teacher_user):
        another_teacher = models.User(
            username="PROF777",
            email="otro_docente@test.com",
            full_name="Otro Docente",
            hashed_password="hash",
            role=models.UserRole.TEACHER,
        )
        group = models.Group(name="B", tutor_id=teacher_user.id, is_active=True)
        db_session.add_all([another_teacher, group])
        db_session.commit()

        response = client.put(
            f"/admin/groups/{group.id}",
            headers=auth_headers_admin,
            json={"tutor_id": another_teacher.id},
        )

        assert response.status_code == 200
        assert response.json()["tutor_id"] == another_teacher.id

    def test_admin_can_list_group_students(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="C", is_active=True)
        db_session.add_all([cycle, group])
        db_session.flush()
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
        )
        db_session.add(enrollment)
        db_session.commit()

        response = client.get(f"/admin/groups/{group.id}/students", headers=auth_headers_admin)

        assert response.status_code == 200
        students = response.json()
        assert any(item["student"]["username"] == student_user.username for item in students)

    def test_admin_can_list_formal_groups_without_legacy_user_group_fields(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="Legacy-Free", is_active=True)
        db_session.add_all([cycle, group])
        db_session.flush()

        student_user.grupo = None
        student_user.carrera = None
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
        )
        db_session.add(enrollment)
        db_session.commit()

        response = client.get("/admin/groups", headers=auth_headers_admin)

        assert response.status_code == 200
        rows = response.json()
        assert any(row["grupo"] == "Legacy-Free" and row["total"] >= 1 for row in rows)

    def test_bulk_group_enrollment_uses_student_enrollment_membership(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="SE-A", is_active=True)
        db_session.add_all([cycle, group])
        db_session.flush()

        student_user.grupo = None
        student_user.carrera = None
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="1",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        db_session.add(enrollment)
        db_session.commit()

        response = client.put(
            "/admin/group-actions/bulk-enrollment",
            headers=auth_headers_admin,
            json={"grupo": "SE-A", "enrollment_status": "Baja Temporal"},
        )

        assert response.status_code == 200
        db_session.refresh(enrollment)
        assert enrollment.enrollment_status == models.EnrollmentStatus.BAJA_TEMPORAL

    def test_bulk_group_assign_uses_student_enrollment_membership(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="SE-B", is_active=True)
        subject = models.Subject(name="Programacion II", credits=8, semester="2", career="Ingenieria")
        db_session.add_all([cycle, group, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        student_user.grupo = None
        student_user.carrera = None
        db_session.add_all([assignment, enrollment])
        db_session.commit()

        response = client.post(
            "/admin/group-actions/bulk-assign",
            headers=auth_headers_admin,
            json={"grupo": "SE-B", "assignment_id": assignment.id},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["enrolled"] == 1
        grade = (
            db_session.query(models.Grade)
            .filter(
                models.Grade.student_id == student_user.id,
                models.Grade.assignment_id == assignment.id,
            )
            .first()
        )
        assert grade is not None

    def test_move_group_does_not_create_duplicate_enrollment_for_same_cycle(
        self, client, auth_headers_admin, db_session, student_user
    ):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        db_session.add(cycle)
        db_session.commit()

        first = client.put(
            "/admin/student-enrollments/move-group",
            headers=auth_headers_admin,
            json={"username": student_user.username, "group_name": "A"},
        )
        assert first.status_code == 200

        second = client.put(
            "/admin/student-enrollments/move-group",
            headers=auth_headers_admin,
            json={"username": student_user.username, "group_name": "B"},
        )
        assert second.status_code == 200

        enrollments = (
            db_session.query(models.StudentEnrollment)
            .filter(
                models.StudentEnrollment.student_id == student_user.id,
                models.StudentEnrollment.cycle_id == cycle.id,
            )
            .all()
        )
        assert len(enrollments) == 1
        assert enrollments[0].group.name == "B"


class TestAdminMigrationAudit:
    """Auditoría de conteos entre modelo legacy y nuevo."""

    def test_admin_migration_audit_returns_counts(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="Audit-A", is_active=True)
        db_session.add_all([cycle, group])
        db_session.flush()

        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        db_session.add(enrollment)
        db_session.commit()

        response = client.get("/admin/migration-audit", headers=auth_headers_admin)

        assert response.status_code == 200
        body = response.json()
        assert body["active_cycle_period"] == "2026-1"
        assert body["student_enrollments_in_active_cycle"] >= 1
        assert "grades_total" in body
        assert "grades_without_course_enrollment" in body

    def test_admin_can_download_student_boleta_pdf(self, client, auth_headers_admin, db_session, student_user):
        subject = models.Subject(
            name="Programacion",
            credits=8,
            semester="1",
            career="Ingeniería",
        )
        grade = models.Grade(
            student_id=student_user.id,
            subject_id=1,
            score=8.0,
            status=models.GradeStatus.APROBADA,
        )
        db_session.add(subject)
        db_session.flush()
        grade.subject_id = subject.id
        db_session.add(grade)
        db_session.commit()

        response = client.get(f"/admin/students/{student_user.username}/boleta", headers=auth_headers_admin)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert response.content.startswith(b"%PDF")


class TestAdminBackfill:
    """Backfill desde modelo legacy al nuevo modelo escolar."""

    def test_backfill_creates_group_and_student_enrollment(self, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        student_user.carrera = "Ingeniería"
        student_user.semestre = "2"
        student_user.grupo = "Legacy-A"
        student_user.enrollment_status = models.EnrollmentStatus.INSCRITO
        db_session.add(cycle)
        db_session.commit()

        result = backfill_student_enrollments_from_legacy(db_session, apply_changes=True)

        assert result["enrollments_created"] >= 1
        group = db_session.query(models.Group).filter(models.Group.name == "Legacy-A").first()
        assert group is not None
        enrollment = (
            db_session.query(models.StudentEnrollment)
            .filter(
                models.StudentEnrollment.student_id == student_user.id,
                models.StudentEnrollment.cycle_id == cycle.id,
            )
            .first()
        )
        assert enrollment is not None
        assert enrollment.group_id == group.id
        assert enrollment.semester == "2"

    def test_backfill_only_missing_keeps_existing_enrollment(self, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        group = models.Group(name="Existing-A", is_active=True)
        db_session.add_all([cycle, group])
        db_session.flush()

        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            group_id=group.id,
            semester="1",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        db_session.add(enrollment)
        student_user.grupo = "Changed-Legacy"
        student_user.semestre = "3"
        db_session.commit()

        result = backfill_student_enrollments_from_legacy(
            db_session,
            only_missing=True,
            apply_changes=True,
        )

        assert result["enrollments_unchanged"] >= 1
        db_session.refresh(enrollment)
        assert enrollment.group_id == group.id
        assert enrollment.semester == "1"


class TestAdminTeachers:
    """Gestión de docentes por admin."""

    def test_admin_can_get_student_academic_history(self, client, auth_headers_admin, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Circuitos", credits=8, semester="3", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=assignment.id,
            score=8.0,
            status=models.GradeStatus.APROBADA,
        )
        db_session.add(grade)
        db_session.commit()

        response = client.get(f"/admin/students/{student_user.username}/academic-history", headers=auth_headers_admin)

        assert response.status_code == 200
        history = response.json()
        assert any(
            item["subject_name"] == "Circuitos"
            and item["cycle"] == "2026-1"
            and item["final_score"] == 8.0
            for item in history
        )

    def test_create_and_update_teacher(self, client, auth_headers_admin):
        create_resp = client.post(
            "/admin/teachers",
            headers=auth_headers_admin,
            json={
                "username": "PROF002",
                "email": "nuevo_docente@test.com",
                "full_name": "Nuevo Docente",
                "password": "docente123",
                "role": "teacher",
            },
        )
        assert create_resp.status_code == 200
        teacher = create_resp.json()
        assert teacher["username"] == "PROF002"

        update_resp = client.put(
            f"/admin/teachers/{teacher['username']}",
            headers=auth_headers_admin,
            json={"full_name": "Docente Actualizado"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["full_name"] == "Docente Actualizado"


class TestAdminPayments:
    """Pagos administrados por el administrador."""

    def test_create_and_update_payment(self, client, auth_headers_admin, student_user):
        due_date = (datetime.utcnow() + timedelta(days=10)).isoformat()
        create_resp = client.post(
            "/admin/payments",
            headers=auth_headers_admin,
            json={
                "student_username": student_user.username,
                "concept": "Inscripción",
                "amount": 1200.5,
                "due_date": due_date,
                "status": "Pendiente",
            },
        )
        assert create_resp.status_code == 200
        payment = create_resp.json()
        assert payment["concept"] == "Inscripción"
        payment_id = payment["id"]

        update_resp = client.put(
            f"/admin/payments/{payment_id}",
            headers=auth_headers_admin,
            json={"status": "Pagado"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "Pagado"

    def test_create_charge_creates_linked_payment(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=1,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        db_session.add(cycle)
        db_session.flush()
        enrollment.cycle_id = cycle.id
        db_session.add(enrollment)
        db_session.commit()

        due_date = (datetime.utcnow() + timedelta(days=10)).isoformat()
        response = client.post(
            "/admin/charges",
            headers=auth_headers_admin,
            json={
                "student_username": student_user.username,
                "cycle_id": cycle.id,
                "charge_type": "Inscripcion",
                "concept": "Inscripcion 2026-1",
                "period_label": "2026-1",
                "amount": 1500,
                "due_date": due_date,
                "status": "Pendiente",
            },
        )

        assert response.status_code == 200
        charge = response.json()
        assert charge["concept"] == "Inscripcion 2026-1"
        linked_payment = db_session.query(models.Payment).filter(models.Payment.charge_id == charge["id"]).first()
        assert linked_payment is not None
        assert linked_payment.amount == 1500

    def test_generate_cycle_payments_creates_charges_and_payments(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=40),
            monthly_amount=1200,
            is_active=True,
        )
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=1,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        student_user.enrollment_status = models.EnrollmentStatus.INSCRITO
        db_session.add(cycle)
        db_session.flush()
        enrollment.cycle_id = cycle.id
        db_session.add(enrollment)
        db_session.commit()

        response = client.post("/admin/school-cycle/generate-payments", headers=auth_headers_admin)

        assert response.status_code == 200
        assert response.json()["payments_created"] >= 1
        charges = db_session.query(models.Charge).filter(models.Charge.student_id == student_user.id).all()
        payments = db_session.query(models.Payment).filter(models.Payment.student_id == student_user.id).all()
        assert len(charges) >= 1
        assert len(payments) >= 1
        assert any(payment.charge_id for payment in payments)

    def test_cannot_create_duplicate_charge_for_same_enrollment_and_period(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=1,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        db_session.add(cycle)
        db_session.flush()
        enrollment.cycle_id = cycle.id
        db_session.add(enrollment)
        db_session.commit()

        due_date = (datetime.utcnow() + timedelta(days=10)).isoformat()
        payload = {
            "student_username": student_user.username,
            "cycle_id": cycle.id,
            "charge_type": "Colegiatura",
            "concept": "Colegiatura Marzo 2026",
            "period_label": "2026-03",
            "amount": 1200,
            "due_date": due_date,
            "status": "Pendiente",
        }
        first = client.post("/admin/charges", headers=auth_headers_admin, json=payload)
        assert first.status_code == 200

        second = client.post("/admin/charges", headers=auth_headers_admin, json=payload)
        assert second.status_code == 400

    def test_cannot_update_charge_into_duplicate_period(self, client, auth_headers_admin, db_session, student_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=1,
            semester="2",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
            is_active=True,
        )
        db_session.add(cycle)
        db_session.flush()
        enrollment.cycle_id = cycle.id
        db_session.add(enrollment)
        db_session.flush()

        due = datetime.utcnow() + timedelta(days=10)
        charge_a = models.Charge(
            student_id=student_user.id,
            student_enrollment_id=enrollment.id,
            charge_type=models.ChargeType.TUITION,
            concept="Colegiatura Abril 2026",
            period_label="2026-04",
            amount=1200,
            due_date=due,
            status=models.PaymentStatus.PENDIENTE,
        )
        charge_b = models.Charge(
            student_id=student_user.id,
            student_enrollment_id=enrollment.id,
            charge_type=models.ChargeType.TUITION,
            concept="Colegiatura Mayo 2026",
            period_label="2026-05",
            amount=1200,
            due_date=due + timedelta(days=30),
            status=models.PaymentStatus.PENDIENTE,
        )
        db_session.add_all([charge_a, charge_b])
        db_session.commit()

        response = client.put(
            f"/admin/charges/{charge_b.id}",
            headers=auth_headers_admin,
            json={"concept": "Colegiatura Abril 2026", "period_label": "2026-04"},
        )

        assert response.status_code == 400


class TestServices:
    """Flujos de servicios escolares."""

    def _create_service(self, client, auth_headers_admin, student_username):
        payload = {
            "student_username": student_username,
            "type": "Constancia",
            "status": "En Proceso",
            "request_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        }
        return client.post("/admin/services", headers=auth_headers_admin, json=payload)

    def test_create_service_request(self, client, auth_headers_admin, student_user):
        """POST /admin/services crea un trámite."""
        response = self._create_service(client, auth_headers_admin, student_user.username)
        assert response.status_code == 200
        data = response.json()
        assert data["student"]["username"] == student_user.username
        assert data["status"] == "En Proceso"

    def test_update_service_status(self, client, auth_headers_admin, student_user):
        """PUT /admin/services/{id} actualiza el estado del trámite."""
        created = self._create_service(client, auth_headers_admin, student_user.username).json()
        service_id = created["id"]

        response = client.put(
            f"/admin/services/{service_id}",
            headers=auth_headers_admin,
            json={"status": "Listo"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Listo"

    def test_user_services_lists_created_requests(self, client, auth_headers_admin, auth_headers_student, student_user):
        created = self._create_service(client, auth_headers_admin, student_user.username).json()
        resp = client.get("/users/me/services", headers=auth_headers_student)
        assert resp.status_code == 200
        assert any(item["id"] == created["id"] for item in resp.json())

    def test_student_can_request_service_for_today(self, client, auth_headers_student):
        payload = {
            "type": "Kardex",
            "request_date": datetime.utcnow().date().isoformat(),
        }
        resp = client.post("/users/me/services", headers=auth_headers_student, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "Kardex"
        assert body["status"] == "En Proceso"

    def test_student_can_request_service_with_attachment(self, client, auth_headers_student):
        response = client.post(
            "/users/me/services/with-document",
            headers=auth_headers_student,
            data={
                "type": "Constancia de Estudios",
                "request_date": datetime.utcnow().date().isoformat(),
            },
            files={"file": ("constancia.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["attachment_filename"] == "constancia.pdf"


class TestUploads:
    """Cargas de archivos de usuario."""

    def test_upload_document_saves_file(self, client, auth_headers_student, student_user):
        """POST /upload-document guarda el archivo en el directorio de uploads del usuario."""
        filename = "comprobante.pdf"
        files = {"file": (filename, b"%PDF-1.4 test", "application/pdf")}

        response = client.post("/upload-document", headers=auth_headers_student, files=files)
        assert response.status_code == 200
        body = response.json()
        assert body["filename"] == filename

        user_dir = Path(settings.UPLOAD_DIR) / student_user.username
        saved_path = user_dir / filename
        try:
            assert saved_path.exists()
            assert saved_path.read_bytes() == b"%PDF-1.4 test"
        finally:
            if user_dir.exists():
                shutil.rmtree(user_dir, ignore_errors=True)


class TestImportCSV:
    """Importación de calificaciones desde CSV."""

    def test_import_grades_creates_subjects_and_grades(self, db_session, student_user, monkeypatch):
        """import_grades debe crear materias y calificaciones nuevas desde CSV válido."""
        csv_file = Path(__file__).resolve().parent / "calificaciones_test.csv"
        csv_file.write_text("username,description,period,score\n2024001,Algebra,1,95\n", encoding="utf-8")

        # Redefinir ruta a CSV de prueba
        monkeypatch.setattr(import_csv, "CSV_PATH", csv_file)

        try:
            import_csv.import_grades()
        finally:
            csv_file.unlink(missing_ok=True)

        grade = (
            db_session.query(models.Grade)
            .join(models.Subject)
            .filter(models.Subject.name == "Algebra", models.Grade.student_id == student_user.id)
            .first()
        )
        assert grade is not None
        assert grade.score == 9.5
        assert grade.status in (models.GradeStatus.APROBADA, "Aprobada")


class TestUserExtras:
    """Otros endpoints de usuario."""

    def test_courses_returns_progress(self, client, auth_headers_student, db_session, student_user, teacher_user):
        subject = models.Subject(
            name="Programación",
            credits=8,
            semester="1",
            career="Ingeniería",
            modality="virtual",
        )
        db_session.add(subject)
        db_session.flush()
        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            score=7.0,
            status=models.GradeStatus.APROBADA,
        )
        db_session.add(grade)
        db_session.commit()

        resp = client.get("/users/me/courses", headers=auth_headers_student)
        assert resp.status_code == 200
        courses = resp.json()
        assert any(c["name"] == "Programación" and c["score"] == 7.0 for c in courses)

    def test_courses_include_course_enrollment_without_grade(
        self, client, auth_headers_student, db_session, student_user, teacher_user
    ):
        cycle = models.SchoolCycle(
            period="2026-2",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(
            name="Bases de Datos II",
            credits=8,
            semester="3",
            career="Ingeniería",
            modality="virtual",
        )
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        student_enrollment = models.StudentEnrollment(
            student_id=student_user.id,
            cycle_id=cycle.id,
            semester="3",
            enrollment_status=models.EnrollmentStatus.INSCRITO,
        )
        db_session.add_all([assignment, student_enrollment])
        db_session.flush()

        course_enrollment = models.CourseEnrollment(
            student_enrollment_id=student_enrollment.id,
            assignment_id=assignment.id,
            attempt_type=models.AttemptType.REGULAR,
            status=models.GradeStatus.CURSANDO,
        )
        db_session.add(course_enrollment)
        db_session.commit()

        resp = client.get("/users/me/courses", headers=auth_headers_student)

        assert resp.status_code == 200
        courses = resp.json()
        assert any(
            c["name"] == "Bases de Datos II"
            and c["course_enrollment_id"] == course_enrollment.id
            and c["status"] == "Cursando"
            and c["score"] == 0
            for c in courses
        )

    def test_user_academic_history_returns_final_score(self, client, auth_headers_student, db_session, student_user, teacher_user):
        cycle = models.SchoolCycle(
            period="2026-1",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=120),
            monthly_amount=1000,
            is_active=True,
        )
        subject = models.Subject(name="Programacion Avanzada", credits=8, semester="4", career="Ingeniería")
        db_session.add_all([cycle, subject])
        db_session.flush()

        assignment = models.SubjectAssignment(
            subject_id=subject.id,
            teacher_id=teacher_user.id,
            cycle_id=cycle.id,
        )
        db_session.add(assignment)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            assignment_id=assignment.id,
            score=9.0,
            status=models.GradeStatus.APROBADA,
        )
        db_session.add(grade)
        db_session.commit()

        resp = client.get("/users/me/academic-history", headers=auth_headers_student)
        assert resp.status_code == 200
        history = resp.json()
        assert any(
            item["subject_name"] == "Programacion Avanzada"
            and item["final_score"] == 9.0
            for item in history
        )

    def test_user_academic_history_hides_unassigned_curriculum_placeholders(
        self, client, auth_headers_student, db_session, student_user
    ):
        subject = models.Subject(name="Curricula Oculta", credits=5, semester="7", career="Ingeniería")
        db_session.add(subject)
        db_session.flush()

        grade = models.Grade(
            student_id=student_user.id,
            subject_id=subject.id,
            attempt_type=models.AttemptType.REGULAR,
            status=models.GradeStatus.PROXIMAMENTE,
        )
        db_session.add(grade)
        db_session.commit()

        resp = client.get("/users/me/academic-history", headers=auth_headers_student)

        assert resp.status_code == 200
        history = resp.json()
        assert not any(item["subject_name"] == "Curricula Oculta" for item in history)

    def test_documents_empty_list(self, client, auth_headers_student):
        resp = client.get("/users/me/documents", headers=auth_headers_student)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_documents_returns_existing_files(self, client, auth_headers_student, student_user):
        user_dir = Path(settings.UPLOAD_DIR) / student_user.username
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = user_dir / "doc.pdf"
        file_path.write_bytes(b"pdf-content")

        resp = client.get("/users/me/documents", headers=auth_headers_student)
        assert resp.status_code == 200
        files = resp.json()
        assert any(item["filename"] == "doc.pdf" for item in files)

        shutil.rmtree(user_dir, ignore_errors=True)


class TestAuthRefresh:
    """Refresco de tokens."""

    def test_refresh_token_returns_new_pair(self, client, student_user):
        login_resp = client.post(
            "/token",
            data={"username": student_user.username, "password": "alumno123"},
        )
        refresh = login_resp.json()["refresh_token"]

        resp = client.post("/token/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
