"""Growth stage derivation.

RULE (dat-v1), documented so Chapter 3 can cite it:

    DAT = days after transplanting = observation_date - planting_date

    DAT <  0                      -> not_planted
    0  <= DAT <= VEGETATIVE_END   -> vegetative     (default 0-55)
    VEG_END < DAT <= REPRO_END    -> reproductive   (default 56-90)
    REPRO_END < DAT <= RIPEN_END  -> ripening       (default 91-125)
    DAT >  RIPEN_END              -> post_harvest

Thresholds are configuration, not constants, because they vary by variety. Derived
values are stored on the DETECTION/IMAGE at observation time, never on the field, so a
later change to the rule cannot silently rewrite history.

This is a derivation, not a measurement. It is labelled with rule_version so a reader
can tell which thresholds produced a stored value.
"""

from __future__ import annotations

import datetime as dt

from app.config import Config

NOT_PLANTED = "not_planted"
VEGETATIVE = "vegetative"
REPRODUCTIVE = "reproductive"
RIPENING = "ripening"
POST_HARVEST = "post_harvest"
UNKNOWN = "DATA_REQUIRED"


def derive_growth_stage(
    planting_date: dt.date | None,
    observation_date: dt.date | None,
    cfg: Config,
) -> dict:
    """Return the stage plus the evidence for it.

    Never raises on missing input: an unknown planting date yields DATA_REQUIRED, which
    is a legitimate state, not an error.
    """
    if planting_date is None or observation_date is None:
        return {
            "days_after_planting": None,
            "growth_stage": UNKNOWN,
            "derivation_method": "days_after_transplanting",
            "rule_version": cfg.GS_RULE_VERSION,
            "observation_date": observation_date.isoformat() if observation_date else None,
        }

    dat = (observation_date - planting_date).days

    if dat < 0:
        stage = NOT_PLANTED
    elif dat <= cfg.GS_VEGETATIVE_END_DAT:
        stage = VEGETATIVE
    elif dat <= cfg.GS_REPRODUCTIVE_END_DAT:
        stage = REPRODUCTIVE
    elif dat <= cfg.GS_RIPENING_END_DAT:
        stage = RIPENING
    else:
        stage = POST_HARVEST

    return {
        "days_after_planting": dat,
        "growth_stage": stage,
        "derivation_method": "days_after_transplanting",
        "rule_version": cfg.GS_RULE_VERSION,
        "observation_date": observation_date.isoformat(),
    }
