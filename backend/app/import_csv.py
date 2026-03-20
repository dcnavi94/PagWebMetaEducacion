import os
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app import models
from app.config import settings

CSV_PATH = Path("/app/calificaciones.csv")
MAX_BYTES = settings.MAX_CSV_SIZE_MB * 1024 * 1024


def _validate_csv_file(path: Path) -> None:
    if path.suffix.lower() != ".csv":
        raise ValueError("El archivo de calificaciones debe tener extension .csv")
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el archivo {path}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"El archivo CSV excede {settings.MAX_CSV_SIZE_MB} MB permitidos")

def import_grades():
    db = SessionLocal()
    try:
        _validate_csv_file(CSV_PATH)
        # Load CSV
        df = pd.read_csv(CSV_PATH)
        
        # Clean data
        df = df.fillna('')
        
        # Keep track of subjects to avoid duplicates
        subjects_cache = {}
        
        # Get all users to map usernames to ids
        users = db.query(models.User).all()
        user_map = {u.username: u.id for u in users}
        
        print(f"Found {len(users)} users in database.")
        
        grades_to_add = []
        subjects_to_add = []
        
        # First pass: collect unique subjects
        for _, row in df.iterrows():
            subject_name = str(row['description']).strip()
            period = str(row['period']).strip()
            
            if not subject_name:
                continue
                
            cache_key = f"{subject_name}_{period}"
            if cache_key not in subjects_cache:
                # Check if it exists in DB
                db_subject = db.query(models.Subject).filter(
                    models.Subject.name == subject_name,
                    models.Subject.semester == period
                ).first()
                
                if db_subject:
                    subjects_cache[cache_key] = db_subject.id
                else:
                    new_subject = models.Subject(
                        name=subject_name,
                        credits=0, # Default
                        semester=period,
                        career="General" # Default
                    )
                    db.add(new_subject)
                    db.flush() # To get the ID
                    subjects_cache[cache_key] = new_subject.id
        
        print(f"Processed {len(subjects_cache)} unique subjects.")
        
        # Second pass: add grades
        count = 0
        for _, row in df.iterrows():
            username = str(row['username']).strip()
            subject_name = str(row['description']).strip()
            period = str(row['period']).strip()
            
            try:
                score = float(row['score']) if row['score'] != '' else None
            except ValueError:
                score = None
            if score is not None and score > 10:
                score = round(score / 10, 2)
                
            if not username or not subject_name or username not in user_map:
                continue
                
            cache_key = f"{subject_name}_{period}"
            subject_id = subjects_cache.get(cache_key)
            
            if not subject_id:
                continue
                
            # Determine status
            status = "Cursando"
            if score is not None:
                if score >= 6 and score <= 10:
                    status = "Aprobada"
                else:
                    status = "Reprobada"
            
            # Check if grade already exists for this student and subject
            existing_grade = db.query(models.Grade).filter(
                models.Grade.student_id == user_map[username],
                models.Grade.subject_id == subject_id
            ).first()
            
            if not existing_grade:
                new_grade = models.Grade(
                    student_id=user_map[username],
                    subject_id=subject_id,
                    score=score,
                    status=status
                )
                db.add(new_grade)
                count += 1
                
            if count % 100 == 0:
                db.commit()
                
        db.commit()
        print(f"Successfully imported {count} grades.")
        
    except Exception as e:
        print(f"Error importing data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import_grades()
