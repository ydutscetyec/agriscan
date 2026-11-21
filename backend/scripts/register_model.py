"""Register trained weights so the worker can use them.

    python -m scripts.register_model --weights runs/classify/train/weights/best.pt ^
        --name AGRISCAN-YOLO26n-cls-v1 --architecture YOLO26n-cls ^
        --dataset-version gdrive-2026-10-19 --mode ground --production

What it does, in order:
  1. Copies the weights to <MODEL_ROOT>/<name>/weights.pt. An existing name is never
     overwritten: a detection must always point at the exact weights that made it.
  2. If ultralytics is installed, reads the model's class names and checks every one
     against the conditions table. The worker drops a prediction whose class is not a
     condition code, so an unmatched class silently never appears. Unmatched names are
     listed, and --write-missing writes them to a CSV for scripts.import_conditions.
  3. Inserts the model_versions row. With --production it also retires the previous
     production model for the same imaging mode, so there is exactly one.

Set AGRISCAN_DETECTOR_IMPL=yolo in backend/.env and restart the worker afterwards.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import get_config  # noqa: E402
from app.extensions import SessionLocal, init_engine  # noqa: E402
from app.models import Condition, ModelVersion  # noqa: E402
from app.services import audit  # noqa: E402


def read_class_names(weights: pathlib.Path) -> list[str] | None:
    try:
        from ultralytics import YOLO
    except ImportError:
        return None
    names = YOLO(str(weights)).names
    if isinstance(names, dict):
        return [str(names[k]) for k in sorted(names)]
    return [str(n) for n in names]


def unmatched_classes(session, class_names: list[str]) -> list[str]:
    """Model class names with no conditions.code row, as the WORKER would resolve them.

    conditions.code is utf8mb4_general_ci, so every lookup the worker makes --
    condition_by_code() issues WHERE code = :code -- is case-insensitive. Comparing
    in Python is not, so an exact-match check reports classes as unmatched that the
    worker resolves without trouble: the model class "Flooding" finds the "flooding"
    row seeded by scripts.seed, and nothing is dropped.

    That false negative is not cosmetic. It blocks --production and invites
    --allow-unmatched, which records the intent "dropping these is fine" for classes
    that are not in fact dropped. Fold both sides instead, so this gate agrees with
    the database it is predicting.

    Folding cannot collapse two distinct rows into one: uq_conditions_code is unique
    on a case-insensitive column, so "flooding" and "Flooding" cannot both exist.
    .lower() rather than .casefold() because general_ci does simple case folding, not
    full Unicode folding, and these codes are ASCII.
    """
    codes = {c.lower() for c in session.execute(select(Condition.code)).scalars()}
    return [n for n in class_names if n.lower() not in codes]


def retire_production(session, mode: str, keep_id: int) -> list[str]:
    rows = session.execute(
        select(ModelVersion)
        .where(ModelVersion.deployment_status == "production")
        .where(ModelVersion.imaging_mode == mode)
        .where(ModelVersion.id != keep_id)
    ).scalars().all()
    for row in rows:
        row.deployment_status = "retired"
    return [r.name for r in rows]


def main() -> int:
    p = argparse.ArgumentParser(description="Register trained weights.")
    p.add_argument("--weights", required=True, type=pathlib.Path)
    p.add_argument("--name", required=True, help="Unique, e.g. AGRISCAN-YOLO26n-cls-v1")
    p.add_argument("--architecture", required=True, help="e.g. YOLO26n-cls")
    p.add_argument("--dataset-version", required=True,
                   help="What it was trained on, e.g. gdrive-2026-10-19. Chapter 4 needs this.")
    p.add_argument("--mode", choices=("ground", "aerial"), default="ground")
    p.add_argument("--conf", type=float, help="Confidence threshold for this model (default from config)")
    p.add_argument("--margin", type=float, help="Top-2 margin threshold for this model")
    p.add_argument("--production", action="store_true", help="Make it the model the worker uses")
    p.add_argument("--allow-unmatched", action="store_true",
                   help="Promote even if some classes are not condition codes")
    p.add_argument("--write-missing", type=pathlib.Path,
                   help="Write unmatched class names to this CSV")
    args = p.parse_args()

    if not args.weights.is_file():
        print(f"No file at {args.weights}")
        return 1

    cfg = get_config()
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()

    if session.execute(select(ModelVersion).where(ModelVersion.name == args.name)).scalar_one_or_none():
        print(f"A model named '{args.name}' is already registered. Use a new name (v2, v3...).")
        return 1

    names = read_class_names(args.weights)
    if names is None:
        print("ultralytics is not installed here, so class names were not checked.\n"
              "  pip install -r requirements-ml.txt   to enable the check.")
        missing = []
    else:
        missing = unmatched_classes(session, names)
        print(f"{len(names)} classes in the model, {len(names) - len(missing)} match condition codes.")
        if missing:
            print("Not condition codes (the worker would drop these):")
            for n in missing:
                print(f"  - {n}")
            if args.write_missing:
                with args.write_missing.open("w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(["code", "common_name", "category", "scientific_name",
                                "plant_part", "aerial_allowed"])
                    for n in missing:
                        w.writerow([n, "", "", "", "", "false"])
                print(f"Wrote {args.write_missing}. Fill in common_name and category, then:\n"
                      f"  python -m scripts.import_conditions {args.write_missing}")
    if missing and args.production and not args.allow_unmatched:
        print("\nNot promoting to production with unmatched classes. Rename the training "
              "folders to condition codes, import the missing conditions, or pass "
              "--allow-unmatched if dropping them is intended.")
        return 1

    target_dir = cfg.model_root_path / args.name
    target_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.weights, target_dir / "weights.pt")

    row = ModelVersion(
        name=args.name,
        architecture=args.architecture,
        dataset_version=args.dataset_version,
        trained_at=dt.datetime.fromtimestamp(args.weights.stat().st_mtime),
        conf_threshold=args.conf,
        margin_threshold=args.margin,
        imaging_mode=args.mode,
        deployment_status="production" if args.production else "staged",
        capability_status="NOT_VALIDATED",
    )
    session.add(row)
    session.flush()
    retired = retire_production(session, args.mode, row.id) if args.production else []
    session.commit()
    audit.record(None, "register_model", "model_version", row.id,
                 {"name": args.name, "production": args.production, "retired": retired})

    print(f"\nRegistered {args.name} ({row.deployment_status}). Weights: {target_dir / 'weights.pt'}")
    if retired:
        print("Retired: " + ", ".join(retired))
    print("capability_status is NOT_VALIDATED until technician-verified results exist.")
    if args.production:
        print("Next: set AGRISCAN_DETECTOR_IMPL=yolo in backend/.env and restart the worker.")
    SessionLocal.remove()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
