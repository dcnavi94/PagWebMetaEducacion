from fastapi.security import OAuth2PasswordBearer
from app import auth, models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
admin_required = auth.require_roles(models.UserRole.ADMIN)
teacher_or_admin = auth.require_roles(models.UserRole.TEACHER, models.UserRole.ADMIN)
services_or_admin = auth.require_roles(models.UserRole.SERVICES, models.UserRole.ADMIN)
