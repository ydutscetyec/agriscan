"""Processing versions: which configuration produced a result.

Adapted from PROMISE (pp. xviii, 21), where each screening result carries the version of
the rule set that produced it. A detection already names its model. A processing version
names everything else that shaped the result — the gates in front of the model and the
method that turns its output into a severity — so a researcher can answer
"how did AGRISCAN produce this result?" from the database alone.

The snapshot is hashed. Identical configuration yields the identical hash, so every
detection produced under one configuration shares one row, and any change to a setting
produces a new row rather than rewriting history.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ProcessingVersion

# Bump when the pipeline CODE changes behaviour without any configuration change
# (a new gate, a different order of stages, a changed severity formula).
PIPELINE_VERSION = "1.0.0"


def _num(value: float) -> float:
    # Rounded so a float's binary representation cannot make two equal settings hash apart.
    return round(float(value), 6)


def snapshot(cfg, conf_threshold: float, margin_threshold: float, severity_method: str) -> dict:
    """The configuration that shapes a result, as plain data.

    `conf_threshold` and `margin_threshold` are the EFFECTIVE values used for this image:
    the model row overrides the configuration default, and a model row can be edited
    later, so the value actually applied is captured here rather than inferred.
    """
    return {
        "pipeline_version": PIPELINE_VERSION,
        "quality_gate": {
            "blur_laplacian_var_min": _num(cfg.QG_BLUR_LAPLACIAN_VAR_MIN),
            "luma_min": _num(cfg.QG_LUMA_MIN),
            "luma_max": _num(cfg.QG_LUMA_MAX),
            "clip_fraction_max": _num(cfg.QG_CLIP_FRACTION_MAX),
        },
        "palay_gate": {"impl": cfg.PALAY_GATE_IMPL, "conf_min": _num(cfg.PALAY_CONF_MIN)},
        "detector": {"impl": cfg.DETECTOR_IMPL},
        "uncertainty": {
            "conf_threshold": _num(conf_threshold),
            "margin_threshold": _num(margin_threshold),
        },
        "severity": {"method": severity_method},
    }


def config_hash(snap: dict) -> str:
    canonical = json.dumps(snap, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_or_create(session, snap: dict) -> int:
    """Return the id for this snapshot, creating the row the first time it is seen."""
    digest = config_hash(snap)
    row = session.execute(
        select(ProcessingVersion).where(ProcessingVersion.config_hash == digest)
    ).scalar_one_or_none()
    if row is not None:
        return row.id

    try:
        # A savepoint, so a lost race with another worker rolls back only this insert.
        with session.begin_nested():
            row = ProcessingVersion(
                config_hash=digest,
                pipeline_version=snap["pipeline_version"],
                config_json=json.dumps(snap, sort_keys=True),
            )
            session.add(row)
            session.flush()
        return row.id
    except IntegrityError:
        existing = session.execute(
            select(ProcessingVersion).where(ProcessingVersion.config_hash == digest)
        ).scalar_one()
        return existing.id
