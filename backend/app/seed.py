import pandas as pd
from .database import SessionLocal, engine
from . import models, auth
from .curriculum import seed_all_curricula
import os
import time
from sqlalchemy import text

def seed_db():
    db = None
    retries = 10
    while retries > 0:
        try:
            models.Base.metadata.create_all(bind=engine)
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            print("Conexión exitosa a la base de datos.")
            break
        except Exception as e:
            print(f"Error conectando a la BD: {e}. Reintentando en 5s...")
            time.sleep(5)
            retries -= 1
    
    if not db:
        print("No se pudo conectar a la base de datos después de varios intentos.")
        return

    try:
        # Check if we already have users
        if db.query(models.User).count() > 0:
            print("La base de datos ya tiene usuarios. Saltando seeding...")
            db.close()
            return

        # 1. Crear usuarios por defecto para roles especiales
        special_users = [
            {
                "username": "admin",
                "full_name": "Administrador",
                "email": "admin@unives.edu.mx",
                "role": models.UserRole.ADMIN,
                "password": "Unives12345"
            },
            {
                "username": "servicios",
                "full_name": "Servicios Escolares",
                "email": "servicios@unives.edu.mx",
                "role": models.UserRole.SERVICES,
                "password": "Unives12345"
            },
            {
                "username": "profesor_demo",
                "full_name": "Profesor Demo",
                "email": "profesor@unives.edu.mx",
                "role": models.UserRole.TEACHER,
                "password": "Unives12345"
            },
            {
                "username": "alumno_demo",
                "full_name": "Alumno Demo",
                "email": "alumno@unives.edu.mx",
                "role": models.UserRole.STUDENT,
                "password": "Unives12345"
            }
        ]

        for u in special_users:
            db_user = models.User(
                username=u["username"],
                email=u["email"],
                full_name=u["full_name"],
                role=u["role"],
                hashed_password=auth.get_password_hash(u["password"])
            )
            db.add(db_user)

        # 1.1 Sembrar la currícula base de las carreras públicas
        seed_all_curricula(db)

        # 2. Cargar alumnos desde CSV
        csv_path = "alumnos_2026-03-06.csv"
        if os.path.exists(csv_path):
            print(f"Cargando alumnos desde {csv_path}...")
            try:
                df = pd.read_csv(csv_path)
                for _, row in df.iterrows():
                    # Matrícula,Nombre,Email,Carrera,Modalidad,Semestre,Grupo
                    username = str(row['Matrícula']).strip()
                    email = str(row['Email']).strip() if pd.notna(row['Email']) else f"{username}@example.com"
                    
                    # Evitar duplicados
                    if db.query(models.User).filter(models.User.username == username).first():
                        continue
                        
                    db_user = models.User(
                        username=username,
                        email=email,
                        full_name=str(row['Nombre']).strip(),
                        role=models.UserRole.STUDENT,
                        hashed_password=auth.get_password_hash("Unives12345"),
                        carrera=str(row['Carrera']).strip() if pd.notna(row['Carrera']) else None,
                        semestre=str(row['Semestre']).strip() if pd.notna(row['Semestre']) else None,
                        grupo=str(row['Grupo']).strip() if pd.notna(row['Grupo']) else None
                    )
                    db.add(db_user)
                print(f"Se cargaron {len(df)} alumnos exitosamente.")
            except Exception as e:
                print(f"Error al cargar el CSV: {e}")
        else:
            print(f"No se encontró el archivo {csv_path}")

        db.commit()
        print("Commit de base de datos completado.")
    except Exception as e:
        print(f"Error durante el seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
