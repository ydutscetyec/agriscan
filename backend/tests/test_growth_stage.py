"""Growth stage derivation (rule dat-v1)."""

from __future__ import annotations

import datetime as dt

from app.services.growth_stage import derive_growth_stage

PLANTED = dt.date(2026, 7, 1)


def test_before_planting(cfg):
    out = derive_growth_stage(PLANTED, dt.date(2026, 6, 20), cfg)
    assert out["growth_stage"] == "not_planted"
    assert out["days_after_planting"] == -11


def test_vegetative(cfg):
    out = derive_growth_stage(PLANTED, dt.date(2026, 7, 20), cfg)
    assert out["growth_stage"] == "vegetative"
    assert out["days_after_planting"] == 19


def test_vegetative_boundary_inclusive(cfg):
    out = derive_growth_stage(PLANTED, PLANTED + dt.timedelta(days=cfg.GS_VEGETATIVE_END_DAT), cfg)
    assert out["growth_stage"] == "vegetative"


def test_reproductive_starts_after_boundary(cfg):
    out = derive_growth_stage(
        PLANTED, PLANTED + dt.timedelta(days=cfg.GS_VEGETATIVE_END_DAT + 1), cfg
    )
    assert out["growth_stage"] == "reproductive"


def test_september_observation_is_reproductive_or_ripening(cfg):
    """Sanity check against the real season: July planting, mid-September observation."""
    out = derive_growth_stage(PLANTED, dt.date(2026, 9, 18), cfg)
    assert out["days_after_planting"] == 79
    assert out["growth_stage"] == "reproductive"


def test_ripening(cfg):
    out = derive_growth_stage(PLANTED, dt.date(2026, 10, 15), cfg)
    assert out["growth_stage"] == "ripening"


def test_post_harvest(cfg):
    out = derive_growth_stage(PLANTED, dt.date(2026, 12, 1), cfg)
    assert out["growth_stage"] == "post_harvest"


def test_missing_planting_date_returns_data_required(cfg):
    out = derive_growth_stage(None, dt.date(2026, 9, 18), cfg)
    assert out["growth_stage"] == "DATA_REQUIRED"
    assert out["days_after_planting"] is None


def test_result_carries_rule_version(cfg):
    out = derive_growth_stage(PLANTED, dt.date(2026, 9, 18), cfg)
    assert out["rule_version"] == cfg.GS_RULE_VERSION
    assert out["derivation_method"] == "days_after_transplanting"


def test_api_exposes_growth_stage(client, users):
    from tests.conftest import auth_headers, login

    token = login(client, "t_tech")
    field_id = users["field_farm_a"].id
    body = client.get(
        f"/fields/{field_id}?observation_date=2026-09-18", headers=auth_headers(token)
    ).get_json()
    assert body["growth_stage"]["growth_stage"] == "reproductive"
    assert body["growth_stage"]["days_after_planting"] == 79
