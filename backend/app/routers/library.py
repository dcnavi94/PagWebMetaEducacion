from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app import auth, models, schemas
from app.database import get_db
from app.dependencies import admin_required
from app.config import settings

router = APIRouter(tags=["Biblioteca"])
LIBRARY_UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "library"
LIBRARY_FILE_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
}


def _validate_resource_type(value: str) -> str:
    allowed = {item.value for item in models.LibraryResourceType}
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"Tipo de recurso invalido. Opciones: {sorted(allowed)}")
    return value


def _loan_payload(item: models.LibraryLoanRequest) -> dict:
    return {
        "id": item.id,
        "book_id": item.book_id,
        "student_id": item.student_id,
        "status": item.status,
        "student_note": item.student_note,
        "admin_note": item.admin_note,
        "requested_at": item.requested_at,
        "approved_at": item.approved_at,
        "loaned_at": item.loaned_at,
        "due_at": item.due_at,
        "returned_at": item.returned_at,
        "updated_at": item.updated_at,
        "book": item.book,
        "student_username": item.student.username if item.student else None,
        "student_name": item.student.full_name if item.student else None,
    }


@router.get("/library/files/{stored_name}")
def get_library_file(stored_name: str):
    safe_name = Path(stored_name).name
    file_path = (LIBRARY_UPLOAD_DIR / safe_name).resolve()
    if file_path.parent != LIBRARY_UPLOAD_DIR.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(file_path)


@router.get("/library/resources", response_model=List[schemas.LibraryVirtualResourceOut])
def list_virtual_resources(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.LibraryVirtualResource).filter(models.LibraryVirtualResource.is_active == True)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            models.LibraryVirtualResource.title.ilike(term),
            models.LibraryVirtualResource.description.ilike(term),
            models.LibraryVirtualResource.category.ilike(term),
            models.LibraryVirtualResource.author.ilike(term),
        ))
    return query.order_by(models.LibraryVirtualResource.category, models.LibraryVirtualResource.title).all()


@router.get("/library/books", response_model=List[schemas.LibraryBookOut])
def list_books(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.LibraryBook).filter(models.LibraryBook.is_active == True)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            models.LibraryBook.title.ilike(term),
            models.LibraryBook.author.ilike(term),
            models.LibraryBook.isbn.ilike(term),
            models.LibraryBook.category.ilike(term),
        ))
    return query.order_by(models.LibraryBook.title).all()


@router.get("/library/loans/me", response_model=List[schemas.LibraryLoanOut])
def list_my_loans(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    rows = (
        db.query(models.LibraryLoanRequest)
        .options(joinedload(models.LibraryLoanRequest.book), joinedload(models.LibraryLoanRequest.student))
        .filter(models.LibraryLoanRequest.student_id == current_user.id)
        .order_by(models.LibraryLoanRequest.requested_at.desc())
        .all()
    )
    return [_loan_payload(row) for row in rows]


@router.post("/library/loans", response_model=schemas.LibraryLoanOut, status_code=201)
def request_loan(
    data: schemas.LibraryLoanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if current_user.role != models.UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Solo los alumnos pueden solicitar prestamos")
    book = db.query(models.LibraryBook).filter(
        models.LibraryBook.id == data.book_id,
        models.LibraryBook.is_active == True,
    ).first()
    if not book:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    active_statuses = [
        models.LibraryLoanStatus.PENDING,
        models.LibraryLoanStatus.APPROVED,
        models.LibraryLoanStatus.LOANED,
    ]
    duplicate = db.query(models.LibraryLoanRequest).filter(
        models.LibraryLoanRequest.book_id == book.id,
        models.LibraryLoanRequest.student_id == current_user.id,
        models.LibraryLoanRequest.status.in_(active_statuses),
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Ya tienes una solicitud activa para este libro")
    if book.available_copies <= 0:
        raise HTTPException(status_code=409, detail="No hay ejemplares disponibles")
    item = models.LibraryLoanRequest(
        book_id=book.id,
        student_id=current_user.id,
        student_note=data.student_note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    item.book = book
    item.student = current_user
    return _loan_payload(item)


@router.get("/admin/library/resources", response_model=List[schemas.LibraryVirtualResourceOut])
def admin_list_resources(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    return db.query(models.LibraryVirtualResource).order_by(models.LibraryVirtualResource.id.desc()).all()


@router.post("/admin/library/upload", status_code=201)
def admin_upload_library_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(admin_required),
):
    if file.content_type not in LIBRARY_FILE_TYPES:
        raise HTTPException(status_code=415, detail="Tipo de archivo no permitido")
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="El archivo supera el tamaño permitido")
    LIBRARY_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original_name = Path(file.filename or "documento").name
    suffix = Path(original_name).suffix.lower()
    stored_name = f"{uuid4().hex}{suffix}"
    destination = LIBRARY_UPLOAD_DIR / stored_name
    with destination.open("wb") as output:
        output.write(file.file.read())
    return {
        "filename": original_name,
        "url": f"/api/library/files/{stored_name}",
    }


@router.post("/admin/library/resources", response_model=schemas.LibraryVirtualResourceOut, status_code=201)
def admin_create_resource(
    data: schemas.LibraryVirtualResourceCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    payload = data.model_dump()
    payload["resource_type"] = _validate_resource_type(payload["resource_type"])
    item = models.LibraryVirtualResource(**payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/admin/library/resources/{item_id}", response_model=schemas.LibraryVirtualResourceOut)
def admin_update_resource(
    item_id: int,
    data: schemas.LibraryVirtualResourceUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    item = db.query(models.LibraryVirtualResource).filter(models.LibraryVirtualResource.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    payload = data.model_dump(exclude_unset=True)
    if "resource_type" in payload:
        payload["resource_type"] = _validate_resource_type(payload["resource_type"])
    for key, value in payload.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/admin/library/resources/{item_id}", status_code=204)
def admin_delete_resource(
    item_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    item = db.query(models.LibraryVirtualResource).filter(models.LibraryVirtualResource.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    db.delete(item)
    db.commit()


@router.get("/admin/library/books", response_model=List[schemas.LibraryBookOut])
def admin_list_books(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    return db.query(models.LibraryBook).order_by(models.LibraryBook.id.desc()).all()


def _normalized_book_payload(data, current: Optional[models.LibraryBook] = None) -> dict:
    payload = data.model_dump(exclude_unset=current is not None)
    total = payload.get("total_copies", current.total_copies if current else 1)
    available = payload.get("available_copies")
    if available is None:
        available = current.available_copies if current else total
        payload["available_copies"] = available
    if available > total:
        raise HTTPException(status_code=400, detail="Los ejemplares disponibles no pueden superar el total")
    return payload


@router.post("/admin/library/books", response_model=schemas.LibraryBookOut, status_code=201)
def admin_create_book(
    data: schemas.LibraryBookCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    item = models.LibraryBook(**_normalized_book_payload(data))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/admin/library/books/{item_id}", response_model=schemas.LibraryBookOut)
def admin_update_book(
    item_id: int,
    data: schemas.LibraryBookUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    item = db.query(models.LibraryBook).filter(models.LibraryBook.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    for key, value in _normalized_book_payload(data, item).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/admin/library/books/{item_id}", status_code=204)
def admin_delete_book(
    item_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    item = db.query(models.LibraryBook).filter(models.LibraryBook.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    if item.loan_requests:
        item.is_active = False
    else:
        db.delete(item)
    db.commit()


@router.get("/admin/library/loans", response_model=List[schemas.LibraryLoanOut])
def admin_list_loans(
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.LibraryLoanRequest)
        .options(joinedload(models.LibraryLoanRequest.book), joinedload(models.LibraryLoanRequest.student))
        .order_by(models.LibraryLoanRequest.requested_at.desc())
        .all()
    )
    return [_loan_payload(row) for row in rows]


@router.put("/admin/library/loans/{item_id}", response_model=schemas.LibraryLoanOut)
def admin_update_loan(
    item_id: int,
    data: schemas.LibraryLoanStatusUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.LibraryLoanRequest)
        .options(joinedload(models.LibraryLoanRequest.book), joinedload(models.LibraryLoanRequest.student))
        .filter(models.LibraryLoanRequest.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    try:
        new_status = models.LibraryLoanStatus(data.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Estado de prestamo invalido")

    old_status = item.status
    if new_status == models.LibraryLoanStatus.LOANED and old_status != models.LibraryLoanStatus.LOANED:
        if item.book.available_copies <= 0:
            raise HTTPException(status_code=409, detail="No hay ejemplares disponibles")
        item.book.available_copies -= 1
        item.loaned_at = datetime.utcnow()
    elif old_status == models.LibraryLoanStatus.LOANED and new_status in {
        models.LibraryLoanStatus.RETURNED,
        models.LibraryLoanStatus.REJECTED,
    }:
        item.book.available_copies = min(item.book.total_copies, item.book.available_copies + 1)

    item.status = new_status
    item.admin_note = data.admin_note
    item.due_at = data.due_at
    if new_status == models.LibraryLoanStatus.APPROVED:
        item.approved_at = datetime.utcnow()
    if new_status == models.LibraryLoanStatus.RETURNED:
        item.returned_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _loan_payload(item)
