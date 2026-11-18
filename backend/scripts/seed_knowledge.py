"""Seed the knowledge base with clearly-marked placeholder records.

Every row is content_status='PLACEHOLDER'. Placeholders exist so the pipeline can be
exercised end to end before the team has entered real guidance; they are not agronomy
and the UI labels them as unusable. Replace the text with material from DA, PhilRice,
BPI or IRRI, attach a knowledge_sources row, and set content_status='REVIEWED'.

Usage:  python -m scripts.seed_knowledge
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import get_config  # noqa: E402
from app.extensions import SessionLocal, init_engine  # noqa: E402
from app.models import Condition, KnowledgeBase, KnowledgeSource  # noqa: E402

PLACEHOLDER = (
    "PLACEHOLDER — no reviewed agronomic content has been entered for this condition yet."
)

# Only non-chemical, non-dosage guidance is ever placeheld. Nothing here names a
# product, a rate or an interval, so a placeholder can never leak a chemical claim.
#
# The first group is the original Tier 1 demo taxonomy (seeded by scripts.seed).
# The second group is modelA_v2's real 25-class output (imported via
# scripts.import_conditions scripts/conditions_modelA_v2.csv before this script
# runs). Both are harmless to keep: "unknown" and the snake_case codes are still
# load-bearing for the worker's fallback path, and a code this script can't find
# is silently skipped rather than erroring.
CONDITIONS = [
    "healthy", "bacterial_leaf_blight", "rice_blast", "brown_spot",
    "hopperburn", "nitrogen_deficiency", "lodging", "flooding", "unknown",
    # modelA_v2 (registered 2026-11, YOLO26n-cls, ground track)
    "Healthy Rice plant", "Bacterial Leaf Blight-Streak", "Brown Spot",
    "Narrow Brown Spot", "Leaf Blast", "Neck-Panicle Blast", "Sheath Blight",
    "Sheath Rot", "Stem Rot", "False Smut", "Tungro", "Grassy Stunt Virus",
    "Ragged Stunt Virus", "Hopper", "Rice Black Bug", "Rice Bug", "Stem Borer",
    "Thrips", "Leaf Miner-Whorl Maggot", "Nutrient Deficiency", "Abiotic Stress",
    "Flooding", "Lodging-Physical Damage", "Vertebrate Damage", "Weed Presence",
]

SOURCES = [
    ("Rice Doctor", "International Rice Research Institute", 2024, None,
     "Condition fact sheets"),
    ("Rice Crop Manager", "Philippine Rice Research Institute", 2024, None,
     "Field management guidance"),
]


def main() -> int:
    cfg = get_config()
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()

    for title, publisher, year, url, locator in SOURCES:
        exists = session.execute(
            select(KnowledgeSource).where(KnowledgeSource.title == title)
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                KnowledgeSource(
                    title=title, publisher=publisher, year=year, url=url, locator=locator
                )
            )
    session.commit()

    source = session.execute(select(KnowledgeSource)).scalars().first()

    added = 0
    for code in CONDITIONS:
        cond = session.execute(
            select(Condition).where(Condition.code == code)
        ).scalar_one_or_none()
        if cond is None:
            continue
        exists = session.execute(
            select(KnowledgeBase).where(KnowledgeBase.condition_id == cond.id)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        session.add(
            KnowledgeBase(
                condition_id=cond.id,
                identification_cues=PLACEHOLDER,
                cultural_measures=PLACEHOLDER,
                preventive_measures=PLACEHOLDER,
                monitoring_guidance=PLACEHOLDER,
                when_to_call=(
                    "Contact your municipal agricultural technician before applying "
                    "any treatment."
                ),
                source_id=source.id if source else None,
                content_status="PLACEHOLDER",
            )
        )
        added += 1
    session.commit()

    print(f"Knowledge base rows added: {added} (all content_status=PLACEHOLDER)")
    print("These are NOT agronomic guidance. Replace them before any field use.")
    SessionLocal.remove()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
