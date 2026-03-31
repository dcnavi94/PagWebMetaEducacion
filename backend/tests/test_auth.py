"""Tests unitarios del módulo de autenticación."""
import pytest
from app import auth


class TestPasswordHashing:
    """Tests de hash y verificación de contraseñas."""

    def test_get_password_hash_returns_string(self):
        """El hash debe ser un string no vacío."""
        hashed = auth.get_password_hash("test123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != "test123"

    def test_verify_password_correct(self):
        """Contraseña correcta debe verificar."""
        hashed = auth.get_password_hash("mi_contraseña")
        assert auth.verify_password("mi_contraseña", hashed) is True

    def test_verify_password_incorrect(self):
        """Contraseña incorrecta no debe verificar."""
        hashed = auth.get_password_hash("correcta")
        assert auth.verify_password("incorrecta", hashed) is False

    def test_different_passwords_different_hashes(self):
        """Contraseñas distintas deben producir hashes distintos."""
        h1 = auth.get_password_hash("pass1")
        h2 = auth.get_password_hash("pass2")
        assert h1 != h2


class TestJWT:
    """Tests de creación y decodificación de tokens JWT."""

    def test_create_access_token_returns_string(self):
        """create_access_token debe devolver un string."""
        token = auth.create_access_token(data={"sub": "user1", "role": "student"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_data(self):
        """El token debe poder decodificarse y contener los datos."""
        from jose import jwt
        from app.config import settings

        data = {"sub": "2024001", "role": "admin"}
        token = auth.create_access_token(data=data)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["sub"] == "2024001"
        assert payload["role"] == "admin"
        assert "exp" in payload
