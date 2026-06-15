from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.dependencies import admin_required

router = APIRouter(tags=["Horarios"])
ALLOWED_COLORS = {"blue", "green", "orange", "purple", "pink", "teal"}


def _validate_times(start_time: str, end_time: str) -> None:
    if start_time >= end_time:
        raise HTTPException(status_code=400, detail="La hora de salida debe ser posterior a la hora de entrada")


def _validate_color(color: str) -> str:
    return color if color in ALLOWED_COLORS else "blue"


@router.get("/users/me/schedule", response_model=List[schemas.StudentScheduleEntryOut])
def get_my_schedule(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.StudentScheduleEntry)
        .filter(models.StudentScheduleEntry.student_id == current_user.id)
        .order_by(models.StudentScheduleEntry.weekday, models.StudentScheduleEntry.start_time)
        .all()
    )


def _student_by_username(db: Session, username: str) -> models.User:
    student = db.query(models.User).filter(
        models.User.username == username,
        models.User.role == models.UserRole.STUDENT,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")
    return student


@router.get("/admin/students/{username}/schedule", response_model=List[schemas.StudentScheduleEntryOut])
def admin_get_schedule(
    username: str,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = _student_by_username(db, username)
    return (
        db.query(models.StudentScheduleEntry)
        .filter(models.StudentScheduleEntry.student_id == student.id)
        .order_by(models.StudentScheduleEntry.weekday, models.StudentScheduleEntry.start_time)
        .all()
    )


@router.post("/admin/students/{username}/schedule", response_model=schemas.StudentScheduleEntryOut, status_code=201)
def admin_create_schedule_entry(
    username: str,
    data: schemas.StudentScheduleEntryCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = _student_by_username(db, username)
    _validate_times(data.start_time, data.end_time)
    payload = data.model_dump()
    payload["color"] = _validate_color(payload["color"])
    item = models.StudentScheduleEntry(student_id=student.id, **payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/admin/students/{username}/schedule/{item_id}", response_model=schemas.StudentScheduleEntryOut)
def admin_update_schedule_entry(
    username: str,
    item_id: int,
    data: schemas.StudentScheduleEntryUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = _student_by_username(db, username)
    item = db.query(models.StudentScheduleEntry).filter(
        models.StudentScheduleEntry.id == item_id,
        models.StudentScheduleEntry.student_id == student.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    payload = data.model_dump(exclude_unset=True)
    start_time = payload.get("start_time", item.start_time)
    end_time = payload.get("end_time", item.end_time)
    _validate_times(start_time, end_time)
    if "color" in payload:
        payload["color"] = _validate_color(payload["color"])
    for key, value in payload.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/admin/students/{username}/schedule/{item_id}", status_code=204)
def admin_delete_schedule_entry(
    username: str,
    item_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    student = _student_by_username(db, username)
    item = db.query(models.StudentScheduleEntry).filter(
        models.StudentScheduleEntry.id == item_id,
        models.StudentScheduleEntry.student_id == student.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    db.delete(item)
    db.commit()


@router.get("/admin/groups/{group_id}/schedule", response_model=List[schemas.StudentScheduleEntryOut])
def admin_get_group_schedule(
    group_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return (
        db.query(models.StudentScheduleEntry)
        .filter(models.StudentScheduleEntry.group_id == group_id)
        .order_by(models.StudentScheduleEntry.weekday, models.StudentScheduleEntry.start_time)
        .all()
    )


@router.post("/admin/groups/{group_id}/schedule", response_model=schemas.StudentScheduleEntryOut, status_code=201)
def admin_create_group_schedule_entry(
    group_id: int,
    data: schemas.StudentScheduleEntryCreate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    _validate_times(data.start_time, data.end_time)
    payload = data.model_dump()
    payload["color"] = _validate_color(payload["color"])
    item = models.StudentScheduleEntry(group_id=group_id, **payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/admin/groups/{group_id}/schedule/{item_id}", response_model=schemas.StudentScheduleEntryOut)
def admin_update_group_schedule_entry(
    group_id: int,
    item_id: int,
    data: schemas.StudentScheduleEntryUpdate,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    item = db.query(models.StudentScheduleEntry).filter(
        models.StudentScheduleEntry.id == item_id,
        models.StudentScheduleEntry.group_id == group_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    payload = data.model_dump(exclude_unset=True)
    start_time = payload.get("start_time", item.start_time)
    end_time = payload.get("end_time", item.end_time)
    _validate_times(start_time, end_time)
    if "color" in payload:
        payload["color"] = _validate_color(payload["color"])
    for key, value in payload.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/admin/groups/{group_id}/schedule/{item_id}", status_code=204)
def admin_delete_group_schedule_entry(
    group_id: int,
    item_id: int,
    current_user: models.User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    item = db.query(models.StudentScheduleEntry).filter(
        models.StudentScheduleEntry.id == item_id,
        models.StudentScheduleEntry.group_id == group_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    db.delete(item)
    db.commit()
