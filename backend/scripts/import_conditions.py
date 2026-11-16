"""Add conditions to the taxonomy from a CSV.

    python -m scripts.import_conditions missing_conditions.csv

Columns: code, common_name, category, scientific_name, plant_part, aerial_allowed.
`code` must equal the model's class name exactly. `category` is one of the values in
app.models.CONDITION_CATEGORIES. Existing codes are left untouched, never overwritten.
"""

from __future__ import annotations

import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import get_config  # noqa: E402
from app.extensions import SessionLocal, init_engine  # noqa: E402
from app.models import CONDITION_CATEGORIES, Condition  # noqa: E402


def load_rows(path: pathlib.Path) -> tuple[list[dict], list[str]]:
    rows, errors = [], []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for n, raw in enumerate(csv.DictReader(fh), start=2):
            code = (raw.get("code") or "").strip()
            name = (raw.get("common_name") or "").strip()
            cat = (raw.get("category") or "").strip().lower()
            if not code:
                continue
            if not name:
                errors.append(f"line {n}: '{code}' has no common_name")
            if cat not in CONDITION_CATEGORIES:
                errors.append(f"line {n}: '{code}' category '{cat}' is not one of "
                              + ", ".join(CONDITION_CATEGORIES))
            rows.append({
                "code": code[:80], "common_name": name[:160], "category": cat,
                "scientific_name": (raw.get("scientific_name") or "").strip() or None,
                "plant_part": (raw.get("plant_part") or "").strip() or None,
                "aerial_allowed": (raw.get("aerial_allowed") or "").strip().lower() in ("1", "true", "yes"),
            })
    return rows, errors


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    rows, errors = load_rows(pathlib.Path(sys.argv[1]))
    if errors:
        print("Nothing imported. Fix these first:")
        for e in errors:
            print("  " + e)
        return 1
    cfg = get_config()
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()
    added = skipped = 0
    for r in rows:
        if session.execute(select(Condition).where(Condition.code == r["code"])).scalar_one_or_none():
            skipped += 1
            continue
        session.add(Condition(tier=2, **r))
        added += 1
    session.commit()
    print(f"Added {added} condition(s); {skipped} already existed and were left as they were.")
    SessionLocal.remove()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
