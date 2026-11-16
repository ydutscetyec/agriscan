"""p9: engineering principles taken from PROMISE, pinned as tests.

Each test names the PROMISE page it comes from. They exist so a later change cannot
quietly undo a principle: the text generator cannot be handed more than it needs, a
failing generator cannot leave a half-written result, and the deterministic stages give
the same answer for the same input.
"""

from __future__ import annotations

import inspect
import itertools

import pytest
from PIL import Image
from sqlalchemy import text

from app.extensions import SessionLocal
from app.inference import apply_uncertainty, build_detector, build_palay_gate, compute_severity
from app.services import quality, recommendations
from app.services.growth_stage import derive_growth_stage
from tests.conftest import auth_headers, login
from tests.factories import sharp_image

_SEED = itertools.count(95000)

RECORDS = [{
    "condition_id": 3,
    "identification_cues": "Brown oval lesions on the leaf.",
    "cultural_measures": "Keep the field drained between irrigations.",
    "preventive_measures": "Use clean seed.",
    "monitoring_guidance": "Walk the field every few days.",
    "when_to_call": "Call a technician if lesions reach the flag leaf.",
}]
FACTS = {
    "condition_code": "brown_spot", "condition_name": "Brown spot",
    "severity_band": "moderate", "growth_stage": "vegetative",
    # everything below must never reach the generator
    "condition_id": 3, "field_id": 9, "farmer_name": "Test Farmer", "lat": 6.37, "lon": 124.74,
}


class SpyPhraser(recommendations.Phraser):
    name = "spy"

    def __init__(self, output="Walk the field every few days.", error=None):
        self.output, self.error, self.seen = output, error, None

    def phrase(self, facts, records):
        self.seen = dict(facts)
        if self.error:
            raise self.error
        return self.output


# ------------------------------------------- consistent outputs for equivalent inputs
# PROMISE p. xxv: rules and calculations are tested "to ensure consistent outputs for
# equivalent inputs".


def _run_stages(path, cfg):
    verdict = quality.assess(str(path), cfg)
    gate = build_palay_gate(cfg).is_palay(str(path))
    predictions = build_detector(cfg).predict(str(path), "phone")
    decision = apply_uncertainty(predictions, 0.5, 0.1)
    with Image.open(path) as im:
        width, height = im.size
    severity = compute_severity(predictions, width, height)
    return repr((verdict, gate, predictions, decision, severity))


def test_the_deterministic_stages_give_one_answer_for_one_image(tmp_path, cfg):
    """Quality gate, palay gate, uncertainty and severity, repeated.

    The detector here is the stub, which is deterministic by construction. This pins
    the stages around the model. Whether trained YOLO weights give identical output on
    identical input has to be tested when those weights exist.
    """
    path = tmp_path / "leaf.jpg"
    path.write_bytes(sharp_image(240, next(_SEED)))
    outputs = {_run_stages(path, cfg) for _ in range(6)}
    assert len(outputs) == 1


def test_growth_stage_is_a_pure_function_of_its_inputs(cfg):
    import datetime as dt

    planted, seen = dt.date(2026, 7, 1), dt.date(2026, 9, 1)
    results = {repr(derive_growth_stage(planted, seen, cfg)) for _ in range(5)}
    assert len(results) == 1


# --------------------------------------------------------------- minimised AI context
# PROMISE pp. xviii, xxvii: the AI receives "minimized participant context".


def test_the_generator_receives_only_the_minimised_facts(monkeypatch, cfg):
    spy = SpyPhraser()
    monkeypatch.setattr(recommendations, "build_phraser", lambda _cfg: spy)
    recommendations.generate(FACTS, RECORDS, cfg)
    assert spy.seen is not None
    assert set(spy.seen) == set(recommendations.PHRASER_FACT_KEYS)
    for leaked in ("condition_id", "field_id", "farmer_name", "lat", "lon"):
        assert leaked not in spy.seen


def test_the_generator_has_no_database_handle():
    """PROMISE p. 17: AI functions "do not calculate, modify, or confirm" the result.

    The structural guarantee is that the generator is given no session to write with.
    If a later change adds one, this fails and the change has to be argued for.
    """
    assert set(inspect.signature(recommendations.generate).parameters) == {
        "facts", "records", "cfg",
    }


# ----------------------------------------------------- fallback when the AI fails
# PROMISE pp. xxvii to xxviii: "appropriate fallback behavior" for AI services.


def test_a_failing_generator_falls_back_instead_of_failing(monkeypatch, cfg):
    spy = SpyPhraser(error=RuntimeError("service unavailable"))
    monkeypatch.setattr(recommendations, "build_phraser", lambda _cfg: spy)
    result = recommendations.generate(FACTS, RECORDS, cfg)
    assert result["text"]
    assert result["validated"] is True
    assert result["generated_by"] != "spy"


def test_ungrounded_specifics_are_suppressed(monkeypatch, cfg):
    spy = SpyPhraser(output="Spray 500 g/ha of mancozeb twice a week.")
    monkeypatch.setattr(recommendations, "build_phraser", lambda _cfg: spy)
    result = recommendations.generate(FACTS, RECORDS, cfg)
    assert result["validated"] is False
    assert result["text"] == recommendations.FALLBACK
    assert result["problems"]


def test_no_matching_knowledge_gives_the_fallback_and_never_calls_the_generator(
    monkeypatch, cfg
):
    spy = SpyPhraser()
    monkeypatch.setattr(recommendations, "build_phraser", lambda _cfg: spy)
    result = recommendations.generate(FACTS, [], cfg)
    assert result["text"] == recommendations.FALLBACK
    assert spy.seen is None


# -------------------------------------------------- administrator accountability
# PROMISE pp. xxiv, xxix: "sensitive administrative activities will be recorded".


def _audit_actions():
    session = SessionLocal()
    rows = session.execute(text("SELECT action FROM audit_log ORDER BY id DESC LIMIT 20"))
    return [r[0] for r in rows]


def test_creating_an_account_is_recorded(client, users):
    admin = login(client, "t_admin")
    resp = client.post(
        "/users",
        headers=auth_headers(admin),
        json={"name": "Audit Probe", "role": "farmer", "password": "a-long-enough-pw-9"},
    )
    assert resp.status_code in (200, 201), resp.get_json()
    assert "create_user" in _audit_actions()


def test_deleting_a_field_is_recorded(client, users):
    admin = login(client, "t_admin")
    created = client.post(
        "/fields", headers=auth_headers(admin),
        json={"name": "p9 audit field", "farm_id": users["farm_a"].id},
    ).get_json()
    resp = client.delete(f"/fields/{created['id']}", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert "delete_field" in _audit_actions()
