"""p9: the inference timing tool measures what it says, and writes nothing."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.config import get_config
from app.extensions import SessionLocal
from app.models import Detection, Image
from scripts import inference_time_test as it
from tests.factories import blurred_image, sharp_image


class StepClock:
    """Each reading advances by the next scripted step, so timings are exact."""

    def __init__(self, steps):
        self.steps = iter(steps)
        self.now = 0.0
        self.toggle = False

    def __call__(self):
        if self.toggle:
            self.now += next(self.steps)
        self.toggle = not self.toggle
        return self.now


@pytest.fixture
def sharp_files(tmp_path):
    paths = []
    for i in range(2):
        p = tmp_path / f"leaf_{i}.jpg"
        p.write_bytes(sharp_image(240, 100 + i))
        paths.append(str(p))
    return paths


# ------------------------------------------------------------------ the arithmetic


def test_time_once_returns_the_elapsed_time_and_the_result():
    clock = StepClock([0.25])
    seconds, result = it.time_once(lambda: "answer", clock)
    assert seconds == pytest.approx(0.25)
    assert result == "answer"


def test_summary_uses_the_sample_sd_not_the_population_sd():
    s = it.summarise([0.10, 0.20, 0.30])
    assert s["n"] == 3
    assert s["mean"] == pytest.approx(0.20)
    assert s["sd"] == pytest.approx(0.10)  # n - 1; the population SD would be 0.0816
    assert s["min"] == pytest.approx(0.10)
    assert s["max"] == pytest.approx(0.30)


def test_a_single_sample_has_no_sd_rather_than_a_zero_one():
    s = it.summarise([0.4])
    assert s["sd"] is None
    assert s["mean"] == pytest.approx(0.4)


def test_no_samples_is_reported_as_none_not_zero():
    s = it.summarise([])
    assert s["n"] == 0 and s["mean"] is None


# ------------------------------------------------------------------- finding images


def test_a_directory_is_expanded_to_its_images_only(tmp_path):
    (tmp_path / "a.jpg").write_bytes(sharp_image(240, 1))
    (tmp_path / "b.PNG").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("not an image")
    found = it.collect_images([str(tmp_path)])
    assert [p.rsplit("/", 1)[-1] for p in found] == ["a.jpg", "b.PNG"]


def test_a_missing_path_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        it.collect_images([str(tmp_path / "nope.jpg")])


def test_an_empty_directory_is_refused_not_timed_as_nothing(tmp_path):
    with pytest.raises(FileNotFoundError):
        it.collect_images([str(tmp_path)])


# ------------------------------------------------------------------- the run itself


def test_sample_counts_are_images_times_trials(sharp_files):
    report = it.run(sharp_files, "phone", 3, get_config(), None)
    assert report["images"] == 2 and report["trials"] == 3
    for name in ("quality gate", "palay gate", "detection", "uncertainty", "severity"):
        assert report["stages"][name]["n"] == 6
    assert report["total"]["n"] == 6
    assert report["stopped"]["completed"] == 6


def test_cold_start_is_reported_apart_and_not_averaged_in(sharp_files):
    report = it.run(sharp_files, "phone", 3, get_config(), None)
    assert report["cold_start_seconds"] > 0
    # six warm detection samples, none of which is the cold call
    assert report["stages"]["detection"]["n"] == 2 * 3


def test_total_is_the_sum_of_the_stages_that_ran(sharp_files):
    report = it.run(sharp_files, "phone", 1, get_config(), None)
    stage_means = sum(report["stages"][n]["mean"] for n in it.STAGES)
    assert report["total"]["mean"] == pytest.approx(stage_means, rel=1e-6)


def test_an_image_that_fails_quality_stops_there(tmp_path):
    blurry = tmp_path / "blur.jpg"
    blurry.write_bytes(blurred_image(240, 7))
    report = it.run([str(blurry)], "phone", 3, get_config(), None)
    assert report["stopped"]["quality gate"] == 3
    assert report["stopped"]["completed"] == 0
    assert report["stages"]["detection"]["n"] == 0
    assert report["stages"]["detection"]["mean"] is None


def test_the_stub_detector_marks_itself_unfit_to_report(sharp_files):
    report = it.run(sharp_files, "phone", 1, get_config(), None)
    assert report["is_stub"] is True
    assert report["valid_for_reporting"] is False
    text = it.render(report)
    assert text.startswith("> **STUB DETECTOR. These are not model timings.**")
    assert "Do not report this run" in text


def test_the_report_names_the_hardware_it_ran_on(sharp_files):
    text = it.render(it.run(sharp_files, "phone", 1, get_config(), None))
    assert "Hardware:" in text and "CPUs" in text
    assert "wrong computer" in text


# ---------------------------------------------------------------------- the command


def test_it_writes_nothing_to_the_database_or_the_image_folder(client, users, sharp_files, tmp_path):
    session = SessionLocal()
    before = (
        session.scalar(select(func.count()).select_from(Image)),
        session.scalar(select(func.count()).select_from(Detection)),
    )
    folder = {p.name for p in tmp_path.iterdir()}

    assert it.main(["--images", *sharp_files, "--trials", "2"]) == 0

    after = (
        session.scalar(select(func.count()).select_from(Image)),
        session.scalar(select(func.count()).select_from(Detection)),
    )
    assert before == after
    assert {p.name for p in tmp_path.iterdir()} == folder  # no --out, so no new file


def test_out_writes_the_report_where_asked(sharp_files, tmp_path, capsys):
    out = tmp_path / "times.md"
    assert it.main(["--images", *sharp_files, "--trials", "1", "--out", str(out)]) == 0
    assert "Inference time test" in out.read_text(encoding="utf-8")
    assert "Inference time test" in capsys.readouterr().out


def test_zero_trials_is_refused(sharp_files, capsys):
    assert it.main(["--images", *sharp_files, "--trials", "0"]) == 2
    assert "at least 1" in capsys.readouterr().err


def test_a_missing_image_exits_with_an_error_not_a_traceback(tmp_path, capsys):
    assert it.main(["--images", str(tmp_path / "gone.jpg")]) == 2
    assert "Not found" in capsys.readouterr().err
