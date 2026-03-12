from sqlalchemy import Column, Integer, String, Enum
from .database import Base
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"
    SERVICES = "services"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)  # Matrícula
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    role = Column(String, default=UserRole.STUDENT)
    carrera = Column(String, nullable=True)
    semestre = Column(String, nullable=True)
    grupo = Column(String, nullable=True)
