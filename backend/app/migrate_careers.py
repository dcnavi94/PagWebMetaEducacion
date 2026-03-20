from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app import models

models.Base.metadata.create_all(bind=engine)

def migrate_careers():
    db = SessionLocal()
    try:
        # Create careers
        careers_data = [
            "Ingeniería en Telemática",
            "Ingeniería en Software",
            "Lic. en Administración",
            "Bachillerato General",
            "Preparatoria"
        ]
        
        career_map = {}
        for c_name in careers_data:
            career = db.query(models.Career).filter(models.Career.name == c_name).first()
            if not career:
                career = models.Career(name=c_name)
                db.add(career)
                db.flush()
            career_map[c_name] = career.id
            
        db.commit()
        
        # Update users
        users = db.query(models.User).all()
        count = 0
        for user in users:
            old_carrera = str(user.carrera).strip() if user.carrera else ""
            
            new_carrera_name = old_carrera
            
            # Apply rules
            if old_carrera == "Ingeniería en Software":
                new_carrera_name = "Ingeniería en Telemática"
            elif old_carrera == "4":
                new_carrera_name = "Ingeniería en Software"
            elif old_carrera == "0" or old_carrera == "Preparatoria":
                new_carrera_name = "Preparatoria"
                
            # Update string field for backwards compatibility
            user.carrera = new_carrera_name
            
            # Link to relational table
            if new_carrera_name in career_map:
                user.career_id = career_map[new_carrera_name]
            else:
                # If it's a new career not in our list, add it
                if new_carrera_name and new_carrera_name != "None" and new_carrera_name != "nan":
                    new_career = models.Career(name=new_carrera_name)
                    db.add(new_career)
                    db.flush()
                    career_map[new_carrera_name] = new_career.id
                    user.career_id = new_career.id
                    
            count += 1
            
        db.commit()
        print(f"Successfully migrated {count} users and created relational careers.")
        
    except Exception as e:
        print(f"Error migrating data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_careers()