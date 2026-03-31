"""CLI para backfill de inscripciones y grupos desde el modelo legacy."""

import argparse
import json

from sqlalchemy.exc import SQLAlchemyError

from .admin_backfill import backfill_student_enrollments_from_legacy
from .database import SessionLocal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill de StudentEnrollment y Group desde User legacy")
    parser.add_argument("--cycle-id", type=int, default=None, help="Ciclo destino; por defecto usa el ciclo activo")
    parser.add_argument("--only-missing", action="store_true", help="Solo crea inscripciones faltantes")
    parser.add_argument("--limit", type=int, default=None, help="Limita el numero de alumnos evaluados")
    parser.add_argument("--apply", action="store_true", help="Aplica cambios; sin este flag solo hace dry-run")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = backfill_student_enrollments_from_legacy(
            db,
            cycle_id=args.cycle_id,
            only_missing=args.only_missing,
            limit=args.limit,
            apply_changes=args.apply,
        )
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, SQLAlchemyError) as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "hint": "Verifica DATABASE_URL y asegúrate de que la base de datos esté disponible antes de ejecutar el backfill.",
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
