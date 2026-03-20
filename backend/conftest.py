"""
Configuración global de pytest.
Configura BD SQLite en memoria y fixtures compartidos.
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Configurar entorno ANTES de importar la app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test_secret_key_32_chars_minimum!!"
os.environ["ENVIRONMENT"] = "development"
# Evitar escribir en rutas absolutas del contenedor (/app/uploads)
os.environ["UPLOAD_DIR"] = str(Path(__file__).resolve().parent / "uploads_test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# Importar después de configurar env (usa SQLite en memoria)
from app.database import Base, engine, get_db
from app.main import app
from app import models, auth

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Crear esquema al arrancar la suite
Base.metadata.create_all(bind=engine)


def override_get_db():
    """Sesión de BD para tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    """Sesión de BD limpia por test. Tablas ya creadas por app.main."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    """Cliente HTTP con BD de test."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session):
    """Usuario admin para tests."""
    user = models.User(
        username="admin_test",
        email="admin@test.com",
        full_name="Admin Test",
        hashed_password=auth.get_password_hash("admin123"),
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def student_user(db_session):
    """Usuario alumno para tests."""
    user = models.User(
        username="2024001",
        email="alumno@test.com",
        full_name="Alumno Test",
        hashed_password=auth.get_password_hash("alumno123"),
        role="student",
        carrera="Ingeniería",
        semestre="2",
        grupo="A",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def teacher_user(db_session):
    """Usuario docente para tests."""
    user = models.User(
        username="PROF001",
        email="profesor@test.com",
        full_name="Profesor Test",
        hashed_password=auth.get_password_hash("prof123"),
        role="teacher",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(client, admin_user):
    """Token JWT del admin."""
    response = client.post(
        "/token",
        data={"username": admin_user.username, "password": "admin123"},
    )
    return response.json()["access_token"]


@pytest.fixture
def student_token(client, student_user):
    """Token JWT del alumno."""
    response = client.post(
        "/token",
        data={"username": student_user.username, "password": "alumno123"},
    )
    return response.json()["access_token"]


@pytest.fixture
def teacher_token(client, teacher_user):
    """Token JWT del docente."""
    response = client.post(
        "/token",
        data={"username": teacher_user.username, "password": "prof123"},
    )
    return response.json()["access_token"]


@pytest.fixture
def auth_headers_admin(admin_token):
    """Headers con Bearer token de admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def auth_headers_student(student_token):
    """Headers con Bearer token de alumno."""
    return {"Authorization": f"Bearer {student_token}"}


@pytest.fixture
def auth_headers_teacher(teacher_token):
    """Headers con Bearer token de docente."""
    return {"Authorization": f"Bearer {teacher_token}"}


@pytest.fixture
def tmp_path():
    """Directorio temporal controlado (evita problemas de permisos en OneDrive/tmp)."""
    base = Path(__file__).resolve().parent / "tmp_files"
    base.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="pytest-", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
