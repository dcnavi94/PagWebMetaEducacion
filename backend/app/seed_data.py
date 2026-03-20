from sqlalchemy.orm import Session
from .database import SessionLocal, engine
from . import models
from datetime import datetime, timedelta

models.Base.metadata.create_all(bind=engine)

def seed_student_data():
    db = SessionLocal()
    try:
        students = db.query(models.User).filter(models.User.role == "student").all()
        if not students:
            print("No students found to seed data.")
            return

        # Subjects ya no tienen teacher_id; se manejan con SubjectAssignment
        if db.query(models.Subject).count() == 0:
            subjects = [
                models.Subject(name="Matemáticas Avanzadas", credits=8, semester="1er Semestre", career="Ingeniería en Software"),
                models.Subject(name="Programación Orientada a Objetos", credits=10, semester="1er Semestre", career="Ingeniería en Software"),
                models.Subject(name="Bases de Datos", credits=8, semester="2do Semestre", career="Ingeniería en Software")
            ]
            db.add_all(subjects)
            db.commit()

        for student in students:
            if db.query(models.Payment).filter(models.Payment.student_id == student.id).count() == 0:
                payments = [
                    models.Payment(student_id=student.id, concept="Inscripción Semestral", amount=2500.00, due_date=datetime.utcnow() - timedelta(days=30), status="Pagado"),
                    models.Payment(student_id=student.id, concept="Mensualidad Septiembre", amount=1500.00, due_date=datetime.utcnow() - timedelta(days=10), status="Pagado"),
                    models.Payment(student_id=student.id, concept="Mensualidad Octubre", amount=1500.00, due_date=datetime.utcnow() + timedelta(days=20), status="Pendiente")
                ]
                db.add_all(payments)

            if db.query(models.ServiceRequest).filter(models.ServiceRequest.student_id == student.id).count() == 0:
                requests = [
                    models.ServiceRequest(student_id=student.id, type="Constancia de Estudios", status="Entregado", request_date=datetime.utcnow() - timedelta(days=15)),
                    models.ServiceRequest(student_id=student.id, type="Credencial de Estudiante", status="En Proceso", request_date=datetime.utcnow() - timedelta(days=2))
                ]
                db.add_all(requests)

        db.commit()
        print("Data seeded successfully for all students")
    except Exception as e:
        print(f"Error seeding data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_student_data()
