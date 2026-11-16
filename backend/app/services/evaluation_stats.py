"""Evaluation statistics for the system-quality instruments.

PROMISE (pp. 25, xxx, 82) summarises each quality characteristic as a weighted mean and
standard deviation with a verbal interpretation, then tests the mean against a fixed
benchmark with a one-sample t-test at the 0.05 level. This module does the same sums,
for AGRISCAN's own instrument and scale.

Nothing here decides the benchmark. The benchmark must be fixed in Chapter 3 before any
response is collected, and the caller has to supply it. The t-test is optional and the
paper has not adopted it; see the mapping document.

Pure standard library, so it runs on any Python the school machines have. The Student t
distribution is computed from the regularised incomplete beta function and checked
against scipy in the tests.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

DEFAULT_LABELS = {
    4: ["Strongly Disagree", "Disagree", "Agree", "Strongly Agree"],
    5: [
        "Poor / Strongly Disagree",
        "Fair / Disagree",
        "Good / Neutral",
        "Very Good / Agree",
        "Excellent / Strongly Agree",
    ],
}


# ------------------------------------------------------------ interpretation scale


def band_width(points: int) -> float:
    """Equal-width bands over 1..points. Five points gives 0.8, the scale PROMISE uses."""
    return (points - 1) / points


def interpretation_bands(points: int) -> list[tuple[float, float, int]]:
    """[(low, high, code)], reported to two decimals the way the paper prints them.

    Five points: 1.00-1.80, 1.81-2.60, 2.61-3.40, 3.41-4.20, 4.21-5.00 (PROMISE p. 25).
    """
    width = band_width(points)
    bands = []
    for k in range(points):
        low = 1.0 if k == 0 else round(1.0 + k * width, 2) + 0.01
        high = round(1.0 + (k + 1) * width, 2)
        bands.append((round(low, 2), high, k + 1))
    return bands


def interpret(mean: float, points: int, labels: list[str] | None = None) -> str:
    """Verbal interpretation of a mean, judged on the two-decimal value as printed."""
    labels = labels or DEFAULT_LABELS.get(points) or [str(i + 1) for i in range(points)]
    if len(labels) != points:
        raise ValueError(f"{points}-point scale needs {points} labels, got {len(labels)}.")
    shown = round(mean, 2)
    for low, high, code in interpretation_bands(points):
        if shown <= high:
            return labels[code - 1]
    return labels[-1]


# --------------------------------------------------------- weighted mean and spread


def weighted_mean(ratings: list[float]) -> float:
    """Sum of (rating x frequency) over N, which is the arithmetic mean of the ratings."""
    return statistics.fmean(ratings)


def sample_sd(ratings: list[float]) -> float | None:
    """Sample standard deviation (n - 1). None when there is only one response."""
    return statistics.stdev(ratings) if len(ratings) >= 2 else None


@dataclass
class IndicatorStat:
    code: str
    n: int
    mean: float
    sd: float | None


@dataclass
class CharacteristicSummary:
    code: str
    indicators: list[IndicatorStat]
    # PROMISE convention (Tables 9 to 14): the AVERAGE row is the mean of the indicator
    # means and the mean of the indicator SDs.
    mean: float
    sd_of_indicator_sds: float | None
    # One number per respondent. This is the right basis for a t-test, because
    # respondents are the independent units, not the items they answered.
    respondent_means: list[float] = field(default_factory=list)

    @property
    def respondent_sd(self) -> float | None:
        return sample_sd(self.respondent_means)


def summarise_characteristic(code: str, columns: dict[str, list[float]]) -> CharacteristicSummary:
    """`columns` maps an indicator name to one rating per respondent, in respondent order."""
    indicators = [
        IndicatorStat(name, len(vals), weighted_mean(vals), sample_sd(vals))
        for name, vals in columns.items()
    ]
    sds = [i.sd for i in indicators if i.sd is not None]
    n_resp = len(next(iter(columns.values())))
    respondent_means = [
        statistics.fmean([vals[r] for vals in columns.values()]) for r in range(n_resp)
    ]
    return CharacteristicSummary(
        code=code,
        indicators=indicators,
        mean=statistics.fmean([i.mean for i in indicators]),
        sd_of_indicator_sds=statistics.fmean(sds) if sds else None,
        respondent_means=respondent_means,
    )


# ------------------------------------------------------------- Student t, one-sample


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, df: int) -> float:
    return _betainc(df / 2.0, 0.5, df / (df + t * t))


def t_upper_p(t: float, df: int) -> float:
    """P(T >= t): the p-value for 'the mean significantly exceeds the benchmark'."""
    p2 = t_two_sided_p(t, df)
    return p2 / 2.0 if t >= 0 else 1.0 - p2 / 2.0


def t_critical_upper(df: int, alpha: float = 0.05) -> float:
    """The t that leaves `alpha` in the upper tail. Found by bisection."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_upper_p(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


@dataclass
class TTestResult:
    n: int
    df: int
    mean: float
    sd: float
    benchmark: float
    alpha: float
    t: float | None
    p: float | None
    t_critical: float | None
    reject_null: bool | None
    note: str | None


def one_sample_t_greater(values: list[float], benchmark: float, alpha: float = 0.05) -> TTestResult:
    """H0: mean <= benchmark.  H1: mean > benchmark.  One-tailed, as 'significantly exceeds'."""
    n = len(values)
    mean = statistics.fmean(values) if values else float("nan")
    if n < 2:
        return TTestResult(n, max(n - 1, 0), mean, float("nan"), benchmark, alpha,
                           None, None, None, None, "Needs at least two respondents.")
    sd = statistics.stdev(values)
    df = n - 1
    crit = t_critical_upper(df, alpha)
    if sd == 0:
        return TTestResult(n, df, mean, 0.0, benchmark, alpha, None, None, crit, None,
                           "Every respondent gave the same mean, so the test is undefined.")
    t = (mean - benchmark) / (sd / math.sqrt(n))
    p = t_upper_p(t, df)
    return TTestResult(n, df, mean, sd, benchmark, alpha, t, p, crit, p < alpha, None)


def format_p(p: float | None) -> str:
    if p is None:
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"
