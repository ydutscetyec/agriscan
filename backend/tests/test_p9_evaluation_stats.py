"""p9: evaluation statistics, checked against known values and against scipy."""

from __future__ import annotations

import math
import statistics

import pytest

from app.services import evaluation_stats as ev
from scripts import evaluation_stats as cli


# -------------------------------------------------------- the t distribution itself
# Published critical values, so the check does not depend on any library.


@pytest.mark.parametrize(
    "df, t_crit",
    [(2, 2.920), (5, 2.015), (10, 1.812), (14, 1.761), (30, 1.697)],
)
def test_one_tailed_critical_values_match_the_published_table(df, t_crit):
    assert ev.t_upper_p(t_crit, df) == pytest.approx(0.05, abs=0.0006)
    assert ev.t_critical_upper(df, 0.05) == pytest.approx(t_crit, abs=0.002)


def test_two_sided_p_at_the_textbook_value():
    assert ev.t_two_sided_p(2.228, 10) == pytest.approx(0.05, abs=0.0006)


def test_upper_p_is_symmetric_and_half_at_zero():
    assert ev.t_upper_p(0.0, 7) == pytest.approx(0.5)
    for t in (0.4, 1.3, 2.9):
        assert ev.t_upper_p(-t, 9) == pytest.approx(1 - ev.t_upper_p(t, 9), abs=1e-12)


def test_agrees_with_scipy_across_a_grid():
    scipy_stats = pytest.importorskip("scipy.stats")
    for df in (1, 2, 3, 5, 9, 14, 29, 120):
        for t in (-3.1, -0.7, 0.0, 0.35, 1.2, 2.4, 5.95, 12.85):
            assert ev.t_upper_p(t, df) == pytest.approx(scipy_stats.t.sf(t, df), abs=1e-9)


def test_one_sample_test_agrees_with_scipy():
    scipy_stats = pytest.importorskip("scipy.stats")
    values = [4.2, 3.8, 4.6, 4.0, 3.5, 4.4, 4.1, 3.9]
    mine = ev.one_sample_t_greater(values, 3.41)
    theirs = scipy_stats.ttest_1samp(values, 3.41, alternative="greater")
    assert mine.t == pytest.approx(theirs.statistic, rel=1e-9)
    assert mine.p == pytest.approx(theirs.pvalue, rel=1e-6, abs=1e-12)
    assert mine.df == len(values) - 1


# ---------------------------------------------------------- interpretation scale


def test_five_point_bands_match_promise_page_25():
    bands = [(lo, hi) for lo, hi, _ in ev.interpretation_bands(5)]
    assert bands == [(1.00, 1.80), (1.81, 2.60), (2.61, 3.40), (3.41, 4.20), (4.21, 5.00)]


@pytest.mark.parametrize(
    "mean, expected",
    [(5.00, "Excellent"), (4.21, "Excellent"), (4.20, "Very Good"), (3.41, "Very Good"),
     (3.40, "Good"), (2.61, "Good"), (2.60, "Fair"), (1.81, "Fair"), (1.80, "Poor"), (1.0, "Poor")],
)
def test_five_point_interpretation_boundaries(mean, expected):
    assert ev.interpret(mean, 5).startswith(expected)


def test_four_point_bands_are_equal_width():
    bands = [(lo, hi) for lo, hi, _ in ev.interpretation_bands(4)]
    assert bands == [(1.00, 1.75), (1.76, 2.50), (2.51, 3.25), (3.26, 4.00)]
    assert ev.interpret(3.26, 4) == "Strongly Agree"
    assert ev.interpret(3.25, 4) == "Agree"


def test_wrong_number_of_labels_is_refused():
    with pytest.raises(ValueError):
        ev.interpret(3.0, 4, labels=["a", "b"])


# --------------------------------------------------------------- mean and spread


def test_summary_uses_promise_convention_and_respondent_means():
    cols = {"FS_1": [4, 3, 4], "FS_2": [2, 3, 4]}
    s = ev.summarise_characteristic("FS", cols)
    assert s.mean == pytest.approx((statistics.fmean([4, 3, 4]) + statistics.fmean([2, 3, 4])) / 2)
    assert s.sd_of_indicator_sds == pytest.approx(
        (statistics.stdev([4, 3, 4]) + statistics.stdev([2, 3, 4])) / 2
    )
    assert s.respondent_means == [3.0, 3.0, 4.0]
    assert s.respondent_sd == pytest.approx(statistics.stdev([3.0, 3.0, 4.0]))


def test_no_variance_is_reported_not_divided_by_zero():
    r = ev.one_sample_t_greater([4.0, 4.0, 4.0], 3.41)
    assert r.t is None and r.reject_null is None and r.note


def test_one_respondent_cannot_be_tested():
    r = ev.one_sample_t_greater([4.0], 3.41)
    assert r.t is None and r.note


def test_p_formatting():
    assert ev.format_p(0.0000001) == "<0.001"
    assert ev.format_p(0.0421) == "0.042"
    assert ev.format_p(None) == "n/a"


# ------------------------------------------------------------------- the script


def _write(tmp_path, rows):
    path = tmp_path / "responses.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


GOOD = [
    "respondent_id,group,FS_1,FS_2,US_1,US_2",
    "r1,it,4,4,3,4",
    "r2,it,3,4,4,4",
    "r3,it,4,3,3,3",
    "r4,farmer,4,4,4,4",
    "r5,farmer,3,3,3,4",
    "r6,farmer,4,4,4,3",
]


def test_script_prints_tables_and_a_decision(tmp_path, capsys):
    code = cli.main([_write(tmp_path, GOOD), "--scale", "4", "--benchmark", "2.51",
                     "--names", '{"FS":"Functional suitability","US":"Usability"}'])
    out = capsys.readouterr().out
    assert code == 0
    assert "Evaluation in terms of Functional suitability" in out
    assert "AVERAGE" in out and "OVERALL" in out
    assert "One-sample t-test against 2.51" in out
    assert "Reject H0" in out or "Fail to reject H0" in out


def test_no_benchmark_means_no_test_and_says_why(tmp_path, capsys):
    cli.main([_write(tmp_path, GOOD), "--scale", "4"])
    out = capsys.readouterr().out
    assert "No benchmark given" in out
    assert "t-test against" not in out


def test_small_samples_get_a_plain_warning(tmp_path, capsys):
    cli.main([_write(tmp_path, GOOD), "--scale", "4", "--benchmark", "2.51"])
    assert "very little power" in capsys.readouterr().out


def test_group_filter_selects_respondents(tmp_path, capsys):
    cli.main([_write(tmp_path, GOOD), "--scale", "4", "--group", "farmer"])
    assert "Respondents: 3" in capsys.readouterr().out


def test_out_of_range_rating_is_refused_not_clipped(tmp_path, capsys):
    bad = GOOD[:2] + ["r2,it,5,4,3,4"] + GOOD[3:]
    assert cli.main([_write(tmp_path, bad), "--scale", "4"]) == 2
    assert "not a whole rating from 1 to 4" in capsys.readouterr().err


def test_blank_rating_is_refused_not_imputed(tmp_path, capsys):
    bad = GOOD[:2] + ["r2,it,,4,3,4"] + GOOD[3:]
    assert cli.main([_write(tmp_path, bad), "--scale", "4"]) == 2
    assert "is blank" in capsys.readouterr().err


def test_missing_respondent_column_is_refused(tmp_path, capsys):
    assert cli.main([_write(tmp_path, ["group,FS_1", "it,4"]), "--scale", "4"]) == 2
    assert "respondent_id" in capsys.readouterr().err
