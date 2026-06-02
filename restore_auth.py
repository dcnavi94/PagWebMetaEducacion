import re

with open('temp_main.py', 'r', encoding='utf-16') as f:
    lines = f.readlines()

auth_lines = []
is_auth = False

for line in lines:
    if line.startswith('@app.post("/token"'):
        is_auth = True
    if is_auth:
        if line.startswith('@app.get("/users/me"'):
            break
        auth_lines.append(line.replace('@app.', '@router.'))

COMMON_IMPORTS = """from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response, Request, Security
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, moodle_client, import_csv, curriculum_credits
from app.database import get_db
from app.dependencies import admin_required, teacher_or_admin, services_or_admin, oauth2_scheme
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import csv
from io import StringIO
import io
from fastapi.security import OAuth2PasswordRequestForm
from app.main import _get_client_ip, _enforce_login_rate_limit, _reset_login_attempts

router = APIRouter()
"""

with open('backend/app/routers/auth.py', 'w', encoding='utf-8') as f:
    f.write(COMMON_IMPORTS)
    f.writelines(auth_lines)

print("Auth restored successfully.")
