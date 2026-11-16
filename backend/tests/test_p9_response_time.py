"""p9: the response-time harness measures what it says it measures."""

from __future__ import annotations

import pytest

from scripts import response_time_test as rt


class FakeClock:
    """Each reading advances by the next scripted step, so timings are exact."""

    def __init__(self, steps):
        self.steps = iter(steps)
        self.now = 0.0
        self.toggle = False

    def __call__(self):
        # called twice per trial: start then end
        if self.toggle:
            self.now += next(self.steps)
        self.toggle = not self.toggle
        return self.now


def test_time_call_reports_mean_sd_and_max_over_three_trials():
    clock = FakeClock([0.10, 0.20, 0.30])
    out = rt.time_call(lambda: True, 3, clock)
    assert out["trials"] == pytest.approx([0.10, 0.20, 0.30])
    assert out["mean"] == pytest.approx(0.20)
    assert out["sd"] == pytest.approx(0.10)
    assert out["max"] == pytest.approx(0.30)
    assert out["failures"] == 0


def test_a_failed_response_is_not_averaged_in_as_a_fast_one():
    results = iter([True, False, True])
    clock = FakeClock([0.10, 0.50, 0.30])
    out = rt.time_call(lambda: next(results), 3, clock)
    assert out["failures"] == 1
    assert len(out["trials"]) == 2
    assert out["mean"] == pytest.approx(0.20)  # the 0.50 s failure is excluded


def test_all_trials_failing_gives_no_mean():
    out = rt.time_call(lambda: False, 3, FakeClock([0.1, 0.1, 0.1]))
    assert out["mean"] is None and out["failures"] == 3


def test_harness_runs_against_the_real_api(client, users):
    transport = rt.FlaskTransport(client)
    report = rt.run(transport, "t_tech", "correct-horse-battery", trials=3)
    assert report["aborted"] is None
    names = [r["function"] for r in report["results"]]
    assert names[0] == "Sign in"
    assert {"Field list", "Verification queue", "Confusion matrix"} <= set(names)
    for r in report["results"]:
        assert len(r["trials"]) + r["failures"] == 3
        assert r["failures"] == 0, f"{r['function']} failed"


def test_wrong_password_stops_the_test_instead_of_timing_error_pages(client, users):
    report = rt.run(rt.FlaskTransport(client), "t_tech", "wrong-password", trials=3)
    assert report["aborted"] == "Sign-in failed."
    assert [r["function"] for r in report["results"]] == ["Sign in"]


def test_the_report_states_its_conditions_and_does_not_invent_a_target(client, users):
    report = rt.run(rt.FlaskTransport(client), "t_tech", "correct-horse-battery", trials=3)
    text = rt.render(report, 3, None, "http://test")
    assert "Test conditions" in text
    assert "Detections stored" in text
    assert "none given" in text
    assert "Within target" not in text


def test_a_target_adds_a_verdict_column(client, users):
    report = rt.run(rt.FlaskTransport(client), "t_tech", "correct-horse-battery", trials=3)
    text = rt.render(report, 3, 60.0, "http://test")
    assert "Within target" in text
    assert "Target: 60.0 s" in text


def test_the_harness_never_uploads(client, users):
    """A test image written to the database would pollute the research dataset."""
    calls = []
    inner = rt.FlaskTransport(client)

    class Spy:
        token = None

        def request(self, method, path, body=None):
            calls.append((method, path))
            inner.token = self.token
            status, raw = inner.request(method, path, body)
            return status, raw

    spy = Spy()
    # keep the token in sync, since Spy owns the attribute the harness sets
    rt.run(spy, "t_tech", "correct-horse-battery", trials=1)
    writes = [c for c in calls if c[0] != "GET" and c[1] != "/auth/login"]
    assert writes == []
    assert not any(path.startswith("/images") and method == "POST" for method, path in calls)
