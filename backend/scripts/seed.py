"""Seed the Tier 1 condition taxonomy, and optionally synthetic demo rows.

Conditions are REFERENCE DATA, not demo data: they are real taxonomy entries and carry
is_demo = FALSE. Users, farms and fields created here are SYNTHETIC and are marked
is_demo = TRUE so every metric and export query can exclude them.

Usage:
    python -m scripts.seed                 # conditions only
    python -m scripts.seed --with-demo     # conditions + synthetic users/farms/fields
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth.security import hash_password  # noqa: E402
from app.config import get_config  # noqa: E402
from app.extensions import SessionLocal, init_engine  # noqa: E402
from app.models import Condition, Farm, Field, ModelVersion, User  # noqa: E402

# Tier 1: trained this cycle. Blast is ONE disease with a plant_part attribute,
# never four separate classes.
TIER1 = [
    ("healthy", "Healthy", None, "healthy", None),
    ("bacterial_leaf_blight", "Bacterial leaf blight", "Xanthomonas oryzae pv. oryzae", "bacterial", None),
    ("rice_blast", "Rice blast", "Pyricularia oryzae", "fungal", "leaf"),
    ("brown_spot", "Brown spot", "Bipolaris oryzae", "fungal", None),
    ("hopperburn", "Hopperburn / planthopper damage", "Nilaparvata lugens", "pest", None),
    ("nitrogen_deficiency", "Nitrogen deficiency", None, "nutritional", None),
    ("lodging", "Lodging", None, "physical", None),
    ("flooding", "Flooding", None, "abiotic", None),
    ("unknown", "Unknown / needs expert review", None, "unknown", None),
]

DEMO_USERS = [
    ("DEMO Admin", "admin", "Poblacion"),
    ("DEMO Technician", "technician", "Poblacion"),
    ("DEMO Farmer A", "farmer", "Libertad"),
    ("DEMO Farmer B", "farmer", "Dajay"),
]

DEMO_PASSWORD = "demo-password-change-me"


def seed_conditions(session) -> int:
    added = 0
    for code, common, sci, category, part in TIER1:
        exists = session.execute(
            select(Condition).where(Condition.code == code)
        ).scalar_one_or_none()
        if exists:
            continue
        session.add(
            Condition(
                code=code,
                common_name=common,
                scientific_name=sci,
                category=category,
                tier=1,
                plant_part=part,
            )
        )
        added += 1
    session.commit()
    return added


def seed_model_slot(session) -> int:
    """Register the not-yet-trained model so the registry is never empty.

    capability_status = DATA_REQUIRED, deployment_status = training. Nothing may be
    served from this row; the worker refuses to run without a 'production' model.
    """
    # One per imaging mode. A drone photo needs an 'aerial' row and a phone photo a
    # 'ground' one; with only the ground row seeded, the first drone image stalled the
    # whole queue with MODEL_NOT_AVAILABLE and nothing explained which mode was missing.
    added = 0
    for mode in ("ground", "aerial"):
        name = f"AGRISCAN-YOLO-v0-untrained-{mode}"
        if session.execute(
            select(ModelVersion).where(ModelVersion.name == name)
        ).scalar_one_or_none():
            continue
        session.add(
            ModelVersion(
                name=name,
                architecture="YOLO26n",
                dataset_version=None,
                trained_at=None,
                metrics_json=None,
                imaging_mode=mode,
                deployment_status="training",
                capability_status="DATA_REQUIRED",
            )
        )
        added += 1
    session.commit()
    return added


def seed_demo(session, cfg) -> dict:
    created = {"users": 0, "farms": 0, "fields": 0}
    users: dict[str, User] = {}
    for name, role, barangay in DEMO_USERS:
        existing = session.execute(
            select(User).where(User.name == name)
        ).scalar_one_or_none()
        if existing:
            users[role if role != "farmer" else name] = existing
            continue
        user = User(
            name=name,
            role=role,
            barangay=barangay,
            password_hash=hash_password(DEMO_PASSWORD, cfg.PASSWORD_MIN_LENGTH),
            is_demo=True,
        )
        session.add(user)
        session.flush()
        users[role if role != "farmer" else name] = user
        created["users"] += 1
    session.commit()

    for farmer_name, farm_name, field_name in [
        ("DEMO Farmer A", "DEMO Farm A", "DEMO Field A1"),
        ("DEMO Farmer B", "DEMO Farm B", "DEMO Field B1"),
    ]:
        owner = session.execute(
            select(User).where(User.name == farmer_name)
        ).scalar_one()
        farm = session.execute(
            select(Farm).where(Farm.name == farm_name)
        ).scalar_one_or_none()
        if farm is None:
            farm = Farm(
                name=farm_name, owner_user_id=owner.id,
                barangay=owner.barangay, is_demo=True,
            )
            session.add(farm)
            session.flush()
            created["farms"] += 1
        field = session.execute(
            select(Field).where(Field.name == field_name)
        ).scalar_one_or_none()
        if field is None:
            session.add(
                Field(
                    farm_id=farm.id,
                    name=field_name,
                    planting_date=dt.date(2026, 7, 1),
                    variety="DEMO variety",
                    area_ha=1.0,
                    is_demo=True,
                )
            )
            created["fields"] += 1
    session.commit()
    return created


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-demo", action="store_true")
    args = parser.parse_args()

    cfg = get_config()
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()

    n_cond = seed_conditions(session)
    n_model = seed_model_slot(session)
    print(f"Conditions added: {n_cond} (Tier 1 reference data, is_demo=FALSE)")
    print(f"Model registry rows added: {n_model} (capability_status=DATA_REQUIRED)")

    if args.with_demo:
        created = seed_demo(session, cfg)
        print(f"SYNTHETIC demo rows added: {created} (all is_demo=TRUE)")
        print(f"Demo password for every seeded account: {DEMO_PASSWORD}")
        print("These are NOT research data. Exclude is_demo=TRUE from every metric.")
    SessionLocal.remove()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
