from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app import auth, models, schemas
from app.database import get_db
from app.dependencies import admin_required

router = APIRouter(tags=["Laboratorio"])


def _request_payload(item: models.LabMaterialRequest) -> dict:
    return {
        "id": item.id,
        "material_id": item.material_id,
        "student_id": item.student_id,
        "quantity": item.quantity,
        "status": item.status,
        "project_name": item.project_name,
        "student_note": item.student_note,
        "admin_note": item.admin_note,
        "requested_at": item.requested_at,
        "approved_at": item.approved_at,
        "delivered_at": item.delivered_at,
        "due_at": item.due_at,
        "returned_at": item.returned_at,
        "updated_at": item.updated_at,
        "material": item.material,
        "student_username": item.student.username if item.student else None,
        "student_name": item.student.full_name if item.student else None,
    }


@router.get("/laboratory/materials", response_model=List[schemas.LabMaterialOut])
def list_materials(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.LabMaterial).filter(models.LabMaterial.is_active == True)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            models.LabMaterial.name.ilike(term),
            models.LabMaterial.code.ilike(term),
            models.LabMaterial.category.ilike(term),
            models.LabMaterial.description.ilike(term),
        ))
    return query.order_by(models.LabMaterial.name).all()


@router.get("/laboratory/requests/me", response_model=List[schemas.LabMaterialRequestOut])
def list_my_requests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    rows = (
        db.query(models.LabMaterialRequest)
        .options(joinedload(models.LabMaterialRequest.material), joinedload(models.LabMaterialRequest.student))
        .filter(models.LabMaterialRequest.student_id == current_user.id)
        .order_by(models.LabMaterialRequest.requested_at.desc())
        .all()
    )
    return [_request_payload(row) for row in rows]


@router.post("/laboratory/requests", response_model=schemas.LabMaterialRequestOut, status_code=201)
def create_request(
    data: schemas.LabMaterialRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if current_user.role != models.UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Solo los alumnos pueden solicitar material")
    material = db.query(models.LabMaterial).filter(
        models.LabMaterial.id == data.material_id,
        models.LabMaterial.is_active == True,
    ).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    if data.quantity > material.available_units:
        raise HTTPException(status_code=409, detail="La cantidad solicitada supera las existencias disponibles")
    active = db.query(models.LabMaterialRequest).filter(
        models.LabMaterialRequest.material_id == material.id,
        models.LabMaterialRequest.student_id == current_user.id,
        models.LabMaterialRequest.status.in_([
            models.LibraryLoanStatus.PENDING,
            models.LibraryLoanStatus.APPROVED,
            models.LibraryLoanStatus.LOANED,
        ]),
    ).first()
    if active:
        raise HTTPException(status_code=409, detail="Ya tienes una solicitud activa para este material")
    item = models.LabMaterialRequest(
        material_id=material.id,
        student_id=current_user.id,
        quantity=data.quantity,
        project_name=data.project_name,
        student_note=data.student_note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    item.material = material
    item.student = current_user
    return _request_payload(item)


@router.get("/admin/laboratory/materials", response_model=List[schemas.LabMaterialOut])
def admin_list_materials(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    return db.query(models.LabMaterial).order_by(models.LabMaterial.id.desc()).all()


def _material_payload(data, current: Optional[models.LabMaterial] = None) -> dict:
    payload = data.model_dump(exclude_unset=current is not None)
    total = payload.get("total_units", current.total_units if current else 1)
    available = payload.get("available_units")
    if available is None:
        available = current.available_units if current else total
        payload["available_units"] = available
    if available > total:
        raise HTTPException(status_code=400, detail="Las unidades disponibles no pueden superar el total")
    return payload


@router.post("/admin/laboratory/materials", response_model=schemas.LabMaterialOut, status_code=201)
def admin_create_material(data: schemas.LabMaterialCreate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = models.LabMaterial(**_material_payload(data))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/admin/laboratory/materials/{item_id}", response_model=schemas.LabMaterialOut)
def admin_update_material(item_id: int, data: schemas.LabMaterialUpdate, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.LabMaterial).filter(models.LabMaterial.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    for key, value in _material_payload(data, item).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/admin/laboratory/materials/{item_id}", status_code=204)
def admin_delete_material(item_id: int, current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    item = db.query(models.LabMaterial).filter(models.LabMaterial.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Material no encontrado")
    if item.requests:
        item.is_active = False
    else:
        db.delete(item)
    db.commit()


@router.get("/admin/laboratory/requests", response_model=List[schemas.LabMaterialRequestOut])
def admin_list_requests(current_user: models.User = Depends(admin_required), db: Session = Depends(get_db)):
    rows = (
        db.query(models.LabMaterialRequest)
        .options(joinedload(models.LabMaterialRequest.material), joinedload(models.LabMaterialRequest.student))
        .order_by(models.LabMaterialRequest.requested_at.desc())
        .all()
    )
    return [_request_payload(row) for row in rows]


@router.put("/admin/laboratory/requests/{item_id}", response_model=schemas.LabMaterialRequestOut)
def admin_update_request(
    item_id: int,
    data: schemas.LabMaterialRequestStatusUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.LabMaterialRequest)
        .options(joinedload(models.LabMaterialRequest.material), joinedload(models.LabMaterialRequest.student))
        .filter(models.LabMaterialRequest.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    try:
        new_status = models.LibraryLoanStatus(data.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Estado invalido")
    old_status = item.status
    if new_status == models.LibraryLoanStatus.LOANED and old_status != models.LibraryLoanStatus.LOANED:
        if item.material.available_units < item.quantity:
            raise HTTPException(status_code=409, detail="No hay unidades suficientes")
        item.material.available_units -= item.quantity
        item.delivered_at = datetime.utcnow()
    elif old_status == models.LibraryLoanStatus.LOANED and new_status in {
        models.LibraryLoanStatus.RETURNED,
        models.LibraryLoanStatus.REJECTED,
    }:
        item.material.available_units = min(
            item.material.total_units,
            item.material.available_units + item.quantity,
        )
    item.status = new_status
    item.admin_note = data.admin_note
    item.due_at = data.due_at
    if new_status == models.LibraryLoanStatus.APPROVED:
        item.approved_at = datetime.utcnow()
    if new_status == models.LibraryLoanStatus.RETURNED:
        item.returned_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _request_payload(item)
