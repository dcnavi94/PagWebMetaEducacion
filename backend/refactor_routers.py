import re
import os

with open('app/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

routers = {
    'public_web': [],
    'admin_web': [],
    'other': []
}

def determine_router(url, tags):
    if 'Web Pública' in tags: return 'public_web'
    if 'Admin Web' in tags: return 'admin_web'
    return 'other'

is_endpoint = False
main_py_new = []

i = 0
while i < len(lines):
    line = lines[i]
    if line.startswith('@app.') and any(method in line for method in ['.get(', '.post(', '.put(', '.delete(', '.patch(']):
        is_endpoint = True
        endpoint_lines = []
        
        # Collect decorators
        while i < len(lines) and not (lines[i].startswith('def ') or lines[i].startswith('async def ')):
            endpoint_lines.append(lines[i])
            i += 1
            
        combined_dec = "".join(endpoint_lines)
        m_url = re.search(r'@app\.(?:get|post|put|delete|patch)\(\s*"([^"]+)"', combined_dec)
        m_tags = re.search(r'tags=\[([^\]]+)\]', combined_dec)
        url = m_url.group(1) if m_url else ""
        tags = m_tags.group(1) if m_tags else ""
        
        router_name = determine_router(url, tags)
        
        # Collect function def line
        endpoint_lines.append(lines[i])
        i += 1
        
        # Collect body
        while i < len(lines):
            # break if we see a top-level decorator or top-level function/class
            if (lines[i].startswith('@') or lines[i].startswith('def ') or lines[i].startswith('async def ') or lines[i].startswith('class ')) and not lines[i].startswith(' '):
                break
            endpoint_lines.append(lines[i])
            i += 1
            
        # Clean trailing newlines
        while endpoint_lines and endpoint_lines[-1].strip() == '':
            endpoint_lines.pop()
            
        # Replace @app. with @router.
        for j in range(len(endpoint_lines)):
            if endpoint_lines[j].startswith('@app.'):
                endpoint_lines[j] = endpoint_lines[j].replace('@app.', '@router.', 1)
                
        routers[router_name].extend(endpoint_lines)
        routers[router_name].append('\n\n')
        continue
    else:
        if not ("# --- Include Routers ---" in line or "from app.routers import" in line or "app.include_router(" in line):
            main_py_new.append(line)
        i += 1

COMMON_IMPORTS = """from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, moodle_client, import_csv, curriculum_credits
from app.database import get_db
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import csv
from io import StringIO
import io

router = APIRouter()

"""

os.makedirs('app/routers', exist_ok=True)
with open('app/routers/__init__.py', 'w', encoding='utf-8') as f:
    pass

for name, lines in routers.items():
    if lines and name != 'other':
        with open(f'app/routers/{name}.py', 'w', encoding='utf-8') as f:
            f.write(COMMON_IMPORTS)
            f.writelines(lines)
    elif lines and name == 'other':
        print(f"WARNING: Found {len(lines)} lines of endpoints that didn't match any router. Appending to main_py_new")
        for j in range(len(lines)):
            lines[j] = lines[j].replace('@router.', '@app.', 1)
        main_py_new.extend(lines)

includes = "\n# --- Include Routers ---\n"
for filename in os.listdir('app/routers'):
    if filename.endswith('.py') and filename != '__init__.py':
        name = filename[:-3]
        includes += f"from app.routers import {name}\n"
        includes += f"app.include_router({name}.router)\n"

main_py_new.append(includes)

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.writelines(main_py_new)

print("Refactor completed successfully.")
