"""
Configuracion centralizada de la aplicacion.
Lee variables de entorno y valida valores criticos para produccion.
"""
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Cargar .env desde el directorio backend
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").lower()
    return val in ("true", "1", "yes", "on")


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return default


class Settings:
    """Configuracion de la aplicacion."""

    # Entorno
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = _get_bool("DEBUG", False)

    # Base de datos
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://unives_user:unives_password@localhost:5433/plataforma_escolar",
    )

    # Seguridad JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "unives_super_secret_key_12345")
    OLD_SECRET_KEYS: List[str] = [
        key.strip() for key in os.getenv("OLD_SECRET_KEYS", "").split(",") if key.strip()
    ]
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _get_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    REFRESH_TOKEN_EXPIRE_MINUTES: int = _get_int("REFRESH_TOKEN_EXPIRE_MINUTES", 10080)  # 7 dias

    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    # Servidor
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = _get_int("API_PORT", 8000)

    # Almacenamiento
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    ALLOWED_UPLOAD_TYPES: List[str] = [
        t.strip()
        for t in os.getenv(
            "ALLOWED_UPLOAD_TYPES",
            "application/pdf,image/jpeg,image/png,text/csv",
        ).split(",")
        if t.strip()
    ]
    MAX_UPLOAD_SIZE_MB: int = _get_int("MAX_UPLOAD_SIZE_MB", 5)
    MAX_CSV_SIZE_MB: int = _get_int("MAX_CSV_SIZE_MB", 5)

    # Rate limiting
    LOGIN_RATE_MAX_ATTEMPTS: int = _get_int("LOGIN_RATE_MAX_ATTEMPTS", 5)
    LOGIN_RATE_WINDOW_SECONDS: int = _get_int("LOGIN_RATE_WINDOW_SECONDS", 900)  # 15 minutos

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def max_csv_size_bytes(self) -> int:
        return self.MAX_CSV_SIZE_MB * 1024 * 1024

    def validate_production(self) -> None:
        """Valida que la configuracion sea segura para produccion."""
        if not self.is_production:
            return
        if self.DEBUG:
            raise ValueError("DEBUG no puede ser True en produccion")
        if self.SECRET_KEY in (
            "unives_super_secret_key_12345",
            "GENERA_UNA_CLAVE_SEGURA_CON_EL_COMANDO_ANTERIOR",
        ):
            raise ValueError(
                "SECRET_KEY debe ser una clave segura en produccion. "
                "Genera una con: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY debe tener al menos 32 caracteres en produccion")
        if self.CORS_ORIGINS == "*" or not self.cors_origins:
            raise ValueError("CORS_ORIGINS debe listar dominios permitidos en produccion separados por coma")


settings = Settings()
