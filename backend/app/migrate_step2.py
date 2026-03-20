from sqlalchemy import text
from app.database import SessionLocal, engine
from app import models

models.Base.metadata.create_all(bind=engine)

def run():
    db = SessionLocal()
    
    # Add columns to DB if they don't exist
    try:
        db.execute(text('ALTER TABLE users ADD COLUMN modality_id INTEGER REFERENCES modalities(id)'))
        db.commit()
        print("Column modality_id added")
    except Exception as e:
        print("Column modality_id might already exist or error:", e)
        db.rollback()
        
    try:
        db.execute(text('ALTER TABLE users ADD COLUMN modalidad VARCHAR'))
        db.commit()
        print("Column modalidad added")
    except Exception as e:
        print("Column modalidad might already exist or error:", e)
        db.rollback()

    try:
        # Create default modalities
        mods = ["En línea", "Presencial", "Híbrido", "Ejecutiva"]
        mod_map = {}
        for m in mods:
            mod = db.query(models.Modality).filter(models.Modality.name == m).first()
            if not mod:
                mod = models.Modality(name=m)
                db.add(mod)
                db.flush()
            mod_map[m] = mod.id
        db.commit()

        prep_career = db.query(models.Career).filter(models.Career.name == 'Preparatoria').first()

        users = db.query(models.User).all()
        teachers_count = 0
        prep_count = 0

        for u in users:
            c = str(u.carrera).strip() if u.carrera else ""
            
            # If N/A or empty -> teacher
            if c in ['N/A', 'nan', 'None', '', 'NaN']:
                u.role = 'teacher'
                u.carrera = None
                u.career_id = None
                teachers_count += 1
            # If it's a number -> Preparatoria
            elif c.isdigit():
                u.carrera = 'Preparatoria'
                if prep_career:
                    u.career_id = prep_career.id
                prep_count += 1
                
            # Default modality (just an example, you can change this later from frontend)
            if u.role == 'student' and not u.modalidad:
                u.modalidad = "En línea"
                u.modality_id = mod_map["En línea"]

        db.commit()
        print(f"Updated {teachers_count} users to teachers.")
        print(f"Updated {prep_count} users to Preparatoria.")
    except Exception as e:
        print("Error updating users:", e)
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    run()