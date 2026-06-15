from __future__ import annotations
from html import unescape
from pathlib import Path
import re

from sqlalchemy.orm import Session

from . import models
from .curriculum_credits import CURRICULUM_CREDITS


CURRICULUM_PAGES = {
    "Ingeniería en Software": "software.html",
    "Ingeniería en Telemática": "telematica.html",
    "Preparatoria": "preparatoria.html",
}
DEFAULT_SUBJECT_CREDITS = 8


def normalize_text(value: str | None) -> str:
    """Normaliza textos de catálogo para comparar nombres con seguridad."""
    return (value or "").strip().casefold()


def extract_curriculum_from_html(file_path: Path) -> list[dict[str, str]]:
    """Extrae materias por cuatrimestre desde las páginas públicas."""
    if not file_path.exists():
        return []

    content = file_path.read_text(encoding="utf-8")
    cards = re.findall(
        r"<h5[^>]*>\s*(\d+)[^<]*Cuatrimestre\s*</h5>(.*?)</ul>",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    subjects: list[dict[str, str]] = []
    for semester, block in cards:
        items = re.findall(r"<li[^>]*>.*?<div>(.*?)<span", block, flags=re.IGNORECASE | re.DOTALL)
        for raw_name in items:
            clean_name = re.sub(r"<[^>]+>", "", raw_name)
            clean_name = unescape(clean_name).strip()
            if clean_name:
                subjects.append({"name": clean_name, "semester": semester})
    return subjects


def get_public_curriculum(career_name: str | None) -> list[dict[str, str]]:
    """Mapea carrera a su página pública y devuelve la currícula encontrada."""
    if not career_name:
        return []

    normalized_career = normalize_text(career_name)
    page_name = next(
        (page for name, page in CURRICULUM_PAGES.items() if normalize_text(name) == normalized_career),
        None,
    )
    if not page_name:
        return []

    path = Path(__file__).resolve().parent / "public" / page_name
    return extract_curriculum_from_html(path)


def get_configured_curriculum(career_name: str | None) -> list[dict[str, str | int | None]]:
    """Devuelve la currícula configurada agrupada por cuatrimestre en formato plano."""
    if not career_name:
        return []

    normalized_career = normalize_text(career_name)
    configured = next(
        (subjects for name, subjects in CURRICULUM_CREDITS.items() if normalize_text(name) == normalized_career),
        {},
    )
    curriculum: list[dict[str, str | int | None]] = []
    for semester, subjects in configured.items():
        for subject in subjects:
            curriculum.append(
                {
                    "name": subject["name"],
                    "semester": semester,
                    "credits": subject.get("credits"),
                }
            )
    return curriculum


def get_subject_credits(career_name: str, subject_name: str) -> int:
    """Obtiene créditos desde el catálogo editable o usa el valor por defecto."""
    for item in get_configured_curriculum(career_name):
        if normalize_text(str(item["name"])) == normalize_text(subject_name):
            configured_credits = item.get("credits")
            return configured_credits if configured_credits is not None else DEFAULT_SUBJECT_CREDITS
    return DEFAULT_SUBJECT_CREDITS


def ensure_subjects_for_career(db: Session, career_name: str | None) -> None:
    """Completa la currícula base de una carrera sin duplicar materias existentes."""
    if not career_name:
        return

    curriculum = get_configured_curriculum(career_name) or get_public_curriculum(career_name)
    if not curriculum:
        return

    existing_subjects = (
        db.query(models.Subject)
        .filter(models.Subject.career == career_name)
        .all()
    )
    existing_keys = {
        (normalize_text(subject.name), normalize_text(subject.semester))
        for subject in existing_subjects
    }

    for item in curriculum:
        item_key = (
            normalize_text(str(item["name"])),
            normalize_text(str(item["semester"])),
        )
        if item_key in existing_keys:
            continue
        db.add(
            models.Subject(
                name=item["name"],
                credits=get_subject_credits(career_name, item["name"]),
                semester=item["semester"],
                career=career_name,
            )
        )
        existing_keys.add(item_key)
    db.flush()


def seed_all_curricula(db: Session) -> None:
    """Siembra la currícula base de las tres carreras soportadas."""
    for career_name in CURRICULUM_PAGES:
        ensure_subjects_for_career(db, career_name)
