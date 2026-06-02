from typing import List, Optional, Any, Dict
import os
import app.main
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response, Request, Security
from sqlalchemy.orm import Session
from datetime import datetime, date
from app import models, schemas, auth, curriculum, moodle_client, import_csv, curriculum_credits
from app.config import settings
from app.database import get_db
from app.dependencies import admin_required, teacher_or_admin, services_or_admin, oauth2_scheme
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import logging
import csv
from io import StringIO
import io

router = APIRouter()

@router.get("/admin/students", response_model=list[schemas.UserListItem], summary="Listar alumnos", tags=["Administracion"])
def get_all_students(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from sqlalchemy import func as _func
    avg_subq = (
        db.query(
            models.Grade.student_id,
            _func.avg(models.Grade.score).label("average_score"),
        )
        .filter(models.Grade.score.isnot(None))
        .group_by(models.Grade.student_id)
        .subquery()
    )
    students = (
        db.query(
            models.User.id,
            models.User.username,
            models.User.email,
            models.User.full_name,
            models.User.curp,
            models.User.seg_unique_key,
            models.User.role,
            models.User.moodle_id,
            models.User.user_status,
            models.User.enrollment_status,
            models.User.career_id,
            models.User.carrera,
            models.User.modality_id,
            models.User.modalidad,
            models.User.semestre,
            models.User.grupo,
            avg_subq.c.average_score,
        )
        .outerjoin(avg_subq, avg_subq.c.student_id == models.User.id)
        .filter(models.User.role == models.UserRole.STUDENT)
        .order_by(models.User.id.asc())
        .all()
    )
    return [row._asdict() for row in students]


@router.post("/admin/students", response_model=schemas.User, summary="Crear alumno", tags=["Administracion"])
def create_student(student: schemas.UserCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == student.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="La matricula/usuario ya esta registrada")

    career = None
    if student.career_id:
        career = db.query(models.Career).filter(models.Career.id == student.career_id).first()
        if not career:
            raise HTTPException(status_code=400, detail="Carrera no encontrada")
    elif student.carrera:
        career = db.query(models.Career).filter(models.Career.name == student.carrera).first()
        if not career:
            career = models.Career(name=student.carrera)
            db.add(career)
            db.flush()

    modality = None
    if student.modality_id:
        modality = db.query(models.Modality).filter(models.Modality.id == student.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
    elif student.modalidad:
        modality = db.query(models.Modality).filter(models.Modality.name == student.modalidad).first()
        if not modality:
            modality = models.Modality(name=student.modalidad)
            db.add(modality)
            db.flush()

    hashed_password = auth.get_password_hash(student.password)
    new_user = models.User(
        username=student.username,
        email=student.email,
        full_name=student.full_name,
        curp=student.curp,
        seg_unique_key=student.seg_unique_key,
        role=models.UserRole.STUDENT,
        hashed_password=hashed_password,
        career_id=career.id if career else None,
        carrera=career.name if career else student.carrera,
        modality_id=modality.id if modality else None,
        modalidad=modality.name if modality else student.modalidad,
        semestre=student.semestre,
        grupo=student.grupo,
    )
    db.add(new_user)
    db.flush()
    app.main._assign_curriculum_to_student(db, new_user.id, career.name if career else student.carrera)
    app.main._sync_student_enrollment_from_legacy(db, new_user, reason="Alta de alumno")
    db.commit()
    db.refresh(new_user)
    return new_user


@router.put("/admin/students/{username}", response_model=schemas.User, summary="Actualizar alumno", tags=["Administracion"])
def update_student(username: str, student_update: schemas.UserUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    if student_update.full_name is not None:
        db_user.full_name = student_update.full_name
    if student_update.email is not None:
        db_user.email = student_update.email
    if student_update.curp is not None:
        db_user.curp = student_update.curp
    if student_update.seg_unique_key is not None:
        db_user.seg_unique_key = student_update.seg_unique_key
    if student_update.password:
        db_user.hashed_password = auth.get_password_hash(student_update.password)
    if student_update.user_status is not None:
        db_user.user_status = student_update.user_status
    if student_update.enrollment_status is not None:
        db_user.enrollment_status = student_update.enrollment_status
    if student_update.career_id is not None:
        career = db.query(models.Career).filter(models.Career.id == student_update.career_id).first()
        if not career:
            raise HTTPException(status_code=400, detail="Carrera no encontrada")
        db_user.career_id = career.id
        db_user.carrera = career.name
    if hasattr(student_update, "carrera") and student_update.carrera is not None:
        career = db.query(models.Career).filter(models.Career.name == student_update.carrera).first()
        if not career and student_update.carrera:
            career = models.Career(name=student_update.carrera)
            db.add(career)
            db.flush()
        if career:
            db_user.career_id = career.id
            db_user.carrera = career.name
    if student_update.modality_id is not None:
        modality = db.query(models.Modality).filter(models.Modality.id == student_update.modality_id).first()
        if not modality:
            raise HTTPException(status_code=400, detail="Modalidad no encontrada")
        db_user.modality_id = modality.id
        db_user.modalidad = modality.name
    if hasattr(student_update, "modalidad") and student_update.modalidad is not None:
        modality = db.query(models.Modality).filter(models.Modality.name == student_update.modalidad).first()
        if not modality and student_update.modalidad:
            modality = models.Modality(name=student_update.modalidad)
            db.add(modality)
            db.flush()
        if modality:
            db_user.modality_id = modality.id
            db_user.modalidad = modality.name
    if student_update.semestre is not None:
        db_user.semestre = student_update.semestre
    if student_update.grupo is not None:
        db_user.grupo = student_update.grupo

    app.main._sync_student_enrollment_from_legacy(db, db_user, reason="Actualizacion de alumno")

    db.commit()
    db.refresh(db_user)

    # Reforzar la currícula al editar carrera o semestre desde el panel.
    if db_user.carrera and (
        student_update.career_id is not None
        or (hasattr(student_update, "carrera") and student_update.carrera is not None)
        or student_update.semestre is not None
    ):
        app.main._assign_curriculum_to_student(db, db_user.id, db_user.carrera)
        db.commit()

    db.refresh(db_user)
    return db_user


@router.delete("/admin/students/{username}", status_code=204, summary="Eliminar alumno", tags=["Administracion"])
def delete_student(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(
        models.User.username == username,
        models.User.role == models.UserRole.STUDENT,
    ).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    enrollment_ids = [
        enrollment.id
        for enrollment in db.query(models.StudentEnrollment.id).filter(
            models.StudentEnrollment.student_id == db_user.id
        ).all()
    ]

    if enrollment_ids:
        db.query(models.CourseEnrollment).filter(
            models.CourseEnrollment.student_enrollment_id.in_(enrollment_ids)
        ).delete(synchronize_session=False)

    db.query(models.Payment).filter(models.Payment.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.Charge).filter(models.Charge.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.ServiceRequest).filter(models.ServiceRequest.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.StudentDocument).filter(models.StudentDocument.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.Grade).filter(models.Grade.student_id == db_user.id).delete(synchronize_session=False)
    db.query(models.StudentEnrollment).filter(models.StudentEnrollment.student_id == db_user.id).delete(synchronize_session=False)
    db.delete(db_user)
    db.commit()


@router.get("/admin/students/{username}/full", summary="Perfil completo de alumno con docentes", tags=["Administracion"])
def get_student_full_profile(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    grades_data = []
    for g in db_user.grades:
        teacher_name = None
        cycle_period = None
        if g.assignment:
            if g.assignment.teacher:
                teacher_name = g.assignment.teacher.full_name or g.assignment.teacher.username
            if g.assignment.cycle:
                cycle_period = g.assignment.cycle.period
        grades_data.append({
            "id": g.id,
            "subject_id": g.subject_id,
            "subject_name": g.subject.name if g.subject else None,
            "subject_semester": g.subject.semester if g.subject else None,
            "subject_credits": g.subject.credits if g.subject else None,
            "assignment_id": g.assignment_id,
            "course_enrollment_id": g.course_enrollment_id,
            "teacher": teacher_name,
            "cycle": cycle_period,
            "score": g.score,
            "status": g.status,
            "attempt_type": g.attempt_type,
        })

    return {
        "id": db_user.id,
        "username": db_user.username,
        "full_name": db_user.full_name,
        "email": db_user.email,
        "curp": db_user.curp,
        "seg_unique_key": db_user.seg_unique_key,
        "role": db_user.role,
        "user_status": db_user.user_status,
        "enrollment_status": db_user.enrollment_status,
        "carrera": db_user.carrera,
        "career_id": db_user.career_id,
        "modalidad": db_user.modalidad,
        "modality_id": db_user.modality_id,
        "semestre": db_user.semestre,
        "grupo": db_user.grupo,
        "academic_advisor_id": db_user.academic_advisor_id,
        "grades": grades_data,
        "payments": [{"id": p.id, "concept": p.concept, "amount": p.amount, "status": p.status, "due_date": str(p.due_date)} for p in db_user.payments],
        "charges": [{"id": c.id, "concept": c.concept, "amount": c.amount, "status": c.status, "due_date": str(c.due_date)} for c in db_user.charges],
        "service_requests": [{"id": r.id, "type": r.type, "status": r.status} for r in db_user.service_requests],
        "documents": [
            {
                "id": doc.id,
                "document_type": doc.document_type,
                "filename": doc.filename,
                "content_type": doc.content_type,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            }
            for doc in sorted(db_user.student_documents, key=lambda item: item.uploaded_at or datetime.min, reverse=True)
        ],
    }


@router.get("/admin/students/{username}/documents", summary="Documentos escaneados de alumno", tags=["Administracion"])
def list_student_documents(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    rows = (
        db.query(models.StudentDocument)
        .filter(models.StudentDocument.student_id == student.id)
        .order_by(models.StudentDocument.uploaded_at.desc(), models.StudentDocument.id.desc())
        .all()
    )
    return {
        "count": len(rows),
        "items": [
            {
                "id": row.id,
                "document_type": row.document_type,
                "filename": row.filename,
                "content_type": row.content_type,
                "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
            }
            for row in rows
        ],
    }


@router.post("/admin/students/{username}/documents", summary="Subir documento escaneado de alumno", tags=["Administracion"])
async def upload_student_document(
    username: str,
    document_type: str = Form("Documento"),
    file: UploadFile = File(...),
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    original_filename, stored_relative_path = app.main._store_student_document(student_username=student.username, file=file)
    doc = models.StudentDocument(
        student_id=student.id,
        document_type=(document_type or "Documento").strip() or "Documento",
        filename=original_filename,
        file_path=stored_relative_path,
        content_type=file.content_type,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {
        "id": doc.id,
        "document_type": doc.document_type,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
    }


@router.get("/admin/students/{username}/documents/{document_id}", summary="Descargar documento escaneado de alumno", tags=["Administracion"])
def download_student_document(
    username: str,
    document_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    doc = (
        db.query(models.StudentDocument)
        .join(models.User, models.User.id == models.StudentDocument.student_id)
        .filter(models.User.username == username, models.StudentDocument.id == document_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    file_path = app.main._student_document_absolute_path(doc.file_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path=str(file_path), filename=doc.filename, media_type=doc.content_type)


@router.delete("/admin/students/{username}/documents/{document_id}", summary="Eliminar documento escaneado de alumno", tags=["Administracion"])
def delete_student_document(
    username: str,
    document_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    doc = (
        db.query(models.StudentDocument)
        .join(models.User, models.User.id == models.StudentDocument.student_id)
        .filter(models.User.username == username, models.StudentDocument.id == document_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    file_path = app.main._student_document_absolute_path(doc.file_path)
    db.delete(doc)
    db.commit()
    if file_path and file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass
    return {"ok": True, "deleted_document_id": document_id}


@router.get("/admin/students/{username}/boleta", summary="Boleta de calificaciones en PDF", tags=["Administracion"])
def get_student_boleta_pdf(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    from fpdf import FPDF
    from fastapi.responses import Response as FastAPIResponse

    student = db.query(models.User).filter(models.User.username == username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    grades = (
        db.query(models.Grade)
        .filter(models.Grade.student_id == student.id)
        .order_by(models.Grade.id.asc())
        .all()
    )

    def safe(s: object, maxlen: int = 999) -> str:
        normalized = str(s or "-").replace("—", "-").replace("–", "-")
        normalized = normalized.encode("latin-1", errors="replace").decode("latin-1")
        return normalized[:maxlen]

    approved = sum(1 for g in grades if str(g.status) == "Aprobada")
    failed = sum(1 for g in grades if str(g.status) == "Reprobada")
    in_prog = sum(1 for g in grades if str(g.status) == "Cursando")
    scored = [g.score for g in grades if g.score is not None]
    avg = round(sum(scored) / len(scored), 2) if scored else 0.0

    folio = f"BOL-{username}-{int(datetime.utcnow().timestamp()) % 1000000:06d}"
    generated_at = datetime.utcnow()

    class BoletaPDF(FPDF):
        def header(self):
            self.set_fill_color(22, 52, 125)
            self.rect(0, 0, 210, 32, "F")
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 17)
            self.set_xy(12, 8)
            self.cell(186, 8, safe("Universidad Unives"), align="L")
            self.set_font("Helvetica", "", 10)
            self.set_xy(12, 18)
            self.cell(186, 6, safe("Boleta Oficial de Calificaciones"), align="L")
            self.set_text_color(35, 35, 35)
            self.ln(18)

        def footer(self):
            self.set_y(-12)
            self.set_draw_color(210, 214, 224)
            self.line(10, self.get_y(), 200, self.get_y())
            self.set_y(-9)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(110, 118, 135)
            footer = f"Pagina {self.page_no()} | Generado el {generated_at.strftime('%d/%m/%Y %H:%M')} UTC"
            self.cell(0, 5, safe(footer), align="C")

    pdf = BoletaPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_fill_color(245, 247, 251)
    pdf.set_draw_color(223, 228, 238)
    pdf.rect(10, 36, 190, 30, style="DF")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(97, 107, 127)
    pdf.set_xy(14, 40)
    pdf.cell(90, 5, safe(f"Folio: {folio}"), align="L")
    pdf.cell(82, 5, safe(f"Fecha: {generated_at.strftime('%d/%m/%Y')}"), align="R")

    info_rows = [
        ("Alumno", safe(student.full_name, 55), "Matricula", safe(student.username, 24)),
        ("Carrera", safe(student.carrera, 55), "Semestre", safe(student.semestre, 24)),
        ("Correo", safe(student.email, 55), "Grupo", safe(student.grupo, 24)),
    ]
    y = 48
    for label_left, value_left, label_right, value_right in info_rows:
        pdf.set_xy(14, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(24, 5, safe(label_left + ":"), align="L")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(70, 5, value_left, align="L")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(24, 5, safe(label_right + ":"), align="L")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(42, 5, value_right, align="L")
        y += 6

    summary_y = 72
    card_w = 45
    summary_cards = [
        ("Aprobadas", str(approved), (22, 163, 74)),
        ("Reprobadas", str(failed), (220, 53, 69)),
        ("En curso", str(in_prog), (245, 158, 11)),
        ("Promedio", str(avg), (37, 99, 235)),
    ]
    x = 10
    for label, value, color in summary_cards:
        pdf.set_fill_color(*color)
        pdf.rect(x, summary_y, card_w, 18, style="F")
        pdf.set_xy(x, summary_y + 3)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(card_w, 4, safe(label), align="C")
        pdf.set_xy(x, summary_y + 8)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(card_w, 6, safe(value), align="C")
        x += card_w + 3

    pdf.set_text_color(35, 35, 35)
    pdf.set_xy(10, 96)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 7, safe("Boleta por Cuatrimestre"), align="L")
    pdf.ln(10)

    def _subject_for_grade(grade: models.Grade):
        if grade.subject:
            return grade.subject
        if grade.assignment and grade.assignment.subject:
            return grade.assignment.subject
        return None

    def _grade_term_number(grade: models.Grade) -> Optional[int]:
        subject = app.main._subject_for_grade(grade)
        semester_label = subject.semester if subject else None
        if not semester_label:
            return None
        parsed = app.main._parse_semester_num(semester_label)
        return parsed if parsed > 0 else None

    def _grade_subject_name(grade: models.Grade) -> str:
        subject = app.main._subject_for_grade(grade)
        return safe(subject.name if subject else "-", 60)

    def _grade_subject_id(grade: models.Grade) -> str:
        subject = app.main._subject_for_grade(grade)
        return safe(subject.id if subject and subject.id is not None else grade.id, 10)

    def _cuatrimestre_label(number: int) -> str:
        return f"{number} Cuatrimestre"

    headers = ["ID", "Materia", "Cuatrimestre", "Calificacion"]
    col_widths = [20, 96, 38, 36]
    row_height = 7
    grades_by_term: dict[int, list[models.Grade]] = {term: [] for term in range(1, 10)}
    for grade in grades:
        term_number = app.main._grade_term_number(grade)
        if term_number and term_number in grades_by_term:
            grades_by_term[term_number].append(grade)

    for term in range(1, 10):
        if pdf.get_y() > 250:
            pdf.add_page()

        term_grades = sorted(
            grades_by_term.get(term, []),
            key=lambda item: (app.main._grade_subject_name(item).lower(), item.id or 0),
        )
        scored = [float(g.score) for g in term_grades if g.score is not None]
        term_avg = round(sum(scored) / len(scored), 2) if scored else None

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(22, 52, 125)
        pdf.cell(190, 6, safe(app.main._cuatrimestre_label(term)), align="L")
        pdf.ln(7)

        pdf.set_fill_color(22, 52, 125)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        for header, width in zip(headers, col_widths):
            pdf.cell(width, 8, safe(header), border=1, align="C", fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(35, 35, 35)

        if term_grades:
            alternate = False
            for grade in term_grades:
                if pdf.get_y() > 268:
                    pdf.add_page()
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(22, 52, 125)
                    pdf.cell(190, 6, safe(app.main._cuatrimestre_label(term) + " (continuacion)"), align="L")
                    pdf.ln(7)
                    pdf.set_fill_color(22, 52, 125)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_font("Helvetica", "B", 8)
                    for header, width in zip(headers, col_widths):
                        pdf.cell(width, 8, safe(header), border=1, align="C", fill=True)
                    pdf.ln()
                    pdf.set_font("Helvetica", "", 8)
                    pdf.set_text_color(35, 35, 35)

                fill = (255, 255, 255) if not alternate else (247, 250, 255)
                alternate = not alternate
                pdf.set_fill_color(*fill)
                values = [
                    app.main._grade_subject_id(grade),
                    app.main._grade_subject_name(grade),
                    safe(app.main._cuatrimestre_label(term), 18),
                    safe(round(grade.score, 1) if grade.score is not None else "-", 12),
                ]
                aligns = ["C", "L", "C", "C"]
                for value, width, align in zip(values, col_widths, aligns):
                    pdf.cell(width, row_height, safe(value, 60), border=1, align=align, fill=True)
                pdf.ln()
        else:
            pdf.set_fill_color(248, 250, 252)
            pdf.set_text_color(90, 98, 112)
            pdf.cell(sum(col_widths), 8, safe("Sin materias registradas."), border=1, align="C", fill=True)
            pdf.ln()
            pdf.set_text_color(35, 35, 35)

        pdf.set_fill_color(236, 242, 255)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(col_widths[0] + col_widths[1] + col_widths[2], 8, safe("Promedio del cuatrimestre"), border=1, align="R", fill=True)
        pdf.cell(col_widths[3], 8, safe(term_avg if term_avg is not None else "-", 12), border=1, align="C", fill=True)
        pdf.ln(12)

    pdf.ln(8)
    pdf.set_text_color(35, 35, 35)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(95, 6, safe("Firmas"), align="L")
    pdf.ln(14)
    line_y = pdf.get_y()
    pdf.set_draw_color(140, 148, 165)
    pdf.line(18, line_y, 82, line_y)
    pdf.line(128, line_y, 192, line_y)
    pdf.set_y(line_y + 2)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(90, 98, 112)
    pdf.set_x(18)
    pdf.cell(64, 5, safe("Director(a) General"), align="C")
    pdf.set_x(128)
    pdf.cell(64, 5, safe("Secretaria Academica"), align="C")

    pdf.ln(14)
    pdf.set_x(10)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(120, 126, 140)
    pdf.multi_cell(
        190,
        4,
        safe(
            "Documento generado electronicamente por el Sistema Administrativo de Universidad Unives. "
            "Valido como consulta interna. Para tramites oficiales solicite documento sellado en Secretaria Academica.",
            280,
        ),
        align="C",
    )

    raw_pdf = pdf.output(dest="S")
    pdf_bytes = raw_pdf if isinstance(raw_pdf, (bytes, bytearray)) else str(raw_pdf).encode("latin-1", errors="replace")
    return FastAPIResponse(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=boleta_{username}.pdf"},
    )


@router.get("/admin/students/{username}/academic-history", response_model=list[schemas.AcademicHistoryItem], summary="Historial academico del alumno", tags=["Administracion"])
def get_student_academic_history(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    return app.main._get_academic_history_for_student(db, student.id)


@router.put("/admin/students/{username}/password", summary="Resetear contraseña de alumno", tags=["Administracion"])
def reset_student_password(username: str, body: dict, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    new_password = body.get("password", "").strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    db_user.hashed_password = auth.get_password_hash(new_password)
    db.commit()
    return {"detail": "Contraseña actualizada"}


@router.put("/admin/students/{username}/advisor", summary="Asignar asesor academico directo a un alumno", tags=["Administracion"])
def assign_student_advisor(
    username: str,
    payload: schemas.StudentAdvisorAssign,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.role == models.UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    advisor = None
    if payload.teacher_id is not None:
        advisor = (
            db.query(models.User)
            .filter(models.User.id == payload.teacher_id, models.User.role == models.UserRole.TEACHER)
            .first()
        )
        if not advisor:
            raise HTTPException(status_code=404, detail="Docente asesor no encontrado")

    student.academic_advisor_id = advisor.id if advisor else None
    db.commit()
    db.refresh(student)

    if advisor:
        app.main._ensure_notification_schema(db)
        db.add(models.NotificationMessage(
            recipient_role=models.UserRole.STUDENT,
            recipient_user_id=student.id,
            created_by_user_id=current_user.id,
            target_scope="user",
            category="advisor",
            title="Asesor académico asignado",
            message=f"Tu asesor académico actual es {advisor.full_name or advisor.username}.",
            level="info",
            is_active=True,
        ))
        db.commit()

    return {
        "ok": True,
        "student_username": student.username,
        "academic_advisor_id": student.academic_advisor_id,
        "advisor_name": advisor.full_name if advisor else None,
    }


@router.post("/admin/students/{username}/moodle-sync", summary="Sincronizar alumno con Moodle", tags=["Administracion"])
async def sync_student_moodle(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == username, models.User.role == models.UserRole.STUDENT).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    evidence = await app.main._sync_student_to_moodle(db, user=db_user)
    if not evidence.get("success"):
        raise HTTPException(status_code=502, detail={"message": "No fue posible sincronizar el alumno con Moodle", "moodle_error": app.main._latest_moodle_error(), "evidence": evidence})
    return {"message": "Alumno sincronizado exitosamente con Moodle", "moodle_id": db_user.moodle_id, "evidence": evidence}


@router.get("/admin/students/{username}/pasaporte", response_model=schemas.PasaporteOut, summary="Pasaporte digital de alumno (admin)", tags=["Administracion"])
def admin_read_student_pasaporte(username: str, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(models.User.username == username).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    active_enrollment = app.main._get_active_student_enrollment(db, student.id)
    career_name = ""
    if active_enrollment and active_enrollment.career:
        career_name = active_enrollment.career.name or ""
    if not career_name:
        career_name = student.carrera or ""
    is_university = "preparatoria" not in career_name.lower() and "prepa" not in career_name.lower()
    thesis = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student.id).first()
    ss_records = db.query(models.SocialServiceRecord).filter(models.SocialServiceRecord.student_id == student.id).all()
    return schemas.PasaporteOut(
        is_university=is_university,
        thesis=schemas.ThesisOut.model_validate(thesis) if thesis else None,
        social_services=[schemas.SocialServiceOut.model_validate(r) for r in ss_records],
    )


@router.put("/admin/students/{student_id}/pasaporte/thesis", summary="Actualizar tesis de alumno (admin)", tags=["Admin"])
def admin_update_thesis(
    student_id: int,
    data: schemas.ThesisAdminUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.SERVICES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")
    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    record = db.query(models.ThesisRecord).filter(models.ThesisRecord.student_id == student_id).first()
    if not record:
        record = models.ThesisRecord(student_id=student_id)
        db.add(record)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(record, field, value)
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return schemas.ThesisOut.model_validate(record)


@router.put("/admin/students/{student_id}/pasaporte/social-service/{service_type}", summary="Actualizar servicio social de alumno (admin)", tags=["Admin"])
def admin_update_social_service(
    student_id: int,
    service_type: str,
    data: schemas.SocialServiceAdminUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.SERVICES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")
    student = db.query(models.User).filter(models.User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    valid_types = [e.value for e in models.SocialServiceType]
    if service_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {valid_types}")
    record = (
        db.query(models.SocialServiceRecord)
        .filter(models.SocialServiceRecord.student_id == student_id, models.SocialServiceRecord.service_type == service_type)
        .first()
    )
    if not record:
        record = models.SocialServiceRecord(student_id=student_id, service_type=service_type)
        db.add(record)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(record, field, value)
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return schemas.SocialServiceOut.model_validate(record)


