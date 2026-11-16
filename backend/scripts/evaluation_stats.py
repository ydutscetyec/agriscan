"""Summarise the system-quality instrument the way PROMISE reports its own.

    python -m scripts.evaluation_stats responses.csv --scale 4 --benchmark 2.51

Input is a CSV with one row per respondent. A `respondent_id` column is required. Rating
columns are named `<CODE>_<n>`, where CODE is the quality characteristic (FS_1, FS_2,
US_1 ...). An optional `group` column lets you analyse one respondent group at a time with
`--group`. Blank or out-of-range ratings are refused, never filled in.

The benchmark is deliberately not defaulted. It has to be fixed in Chapter 3 before any
response is collected; choosing it after seeing the means is not a benchmark.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys

from app.services import evaluation_stats as ev

RATING_COLUMN = re.compile(r"^([A-Za-z]+)_(\d+)$")
# n at or below this gets a plain warning. The t-test is valid with any n >= 2 but has
# almost no power with a handful of respondents.
SMALL_N = 10


def read_responses(path: str, points: int, group: str | None = None):
    """Return {code: {indicator: [rating per respondent]}} and the respondent ids."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        if "respondent_id" not in header:
            raise ValueError("The CSV needs a 'respondent_id' column.")
        rating_cols = [c for c in header if RATING_COLUMN.match(c)]
        if not rating_cols:
            raise ValueError("No rating columns found. Name them like FS_1, FS_2, US_1.")
        rows = [r for r in reader if (group is None or (r.get("group") or "").strip() == group)]
    if not rows:
        raise ValueError(f"No respondents found{f' in group {group!r}' if group else ''}.")

    data: dict[str, dict[str, list[float]]] = {}
    ids = [r["respondent_id"] for r in rows]
    for col in rating_cols:
        code = RATING_COLUMN.match(col).group(1)
        values = []
        for row in rows:
            raw = (row.get(col) or "").strip()
            if raw == "":
                raise ValueError(f"Respondent {row['respondent_id']}: {col} is blank.")
            try:
                value = float(raw)
            except ValueError:
                raise ValueError(f"Respondent {row['respondent_id']}: {col} is not a number ({raw!r}).")
            if not (1 <= value <= points) or value != int(value):
                raise ValueError(
                    f"Respondent {row['respondent_id']}: {col} = {raw} is not a whole "
                    f"rating from 1 to {points}."
                )
            values.append(value)
        data.setdefault(code, {})[col] = values
    return data, ids


def _fmt(x, digits=2):
    return "n/a" if x is None else f"{x:.{digits}f}"


def build_report(data, ids, points, labels, names, benchmark, alpha) -> str:
    out: list[str] = []
    summaries = {code: ev.summarise_characteristic(code, cols) for code, cols in data.items()}

    out.append(f"Respondents: {len(ids)}   Scale: 1 to {points}")
    out.append("")
    out.append("Interpretation scale")
    out.append("")
    out.append("| Code | Mean range | Interpretation |")
    out.append("| --- | --- | --- |")
    for low, high, code in reversed(ev.interpretation_bands(points)):
        out.append(f"| {code} | {low:.2f} to {high:.2f} | {labels[code - 1]} |")
    out.append("")

    for code, summary in summaries.items():
        title = names.get(code, code)
        out.append(f"Evaluation in terms of {title}")
        out.append("")
        out.append("| Indicator | WM | SD | Interpretation |")
        out.append("| --- | --- | --- | --- |")
        for ind in summary.indicators:
            out.append(
                f"| {ind.code} | {_fmt(ind.mean)} | {_fmt(ind.sd)} | "
                f"{ev.interpret(ind.mean, points, labels)} |"
            )
        out.append(
            f"| AVERAGE | {_fmt(summary.mean)} | {_fmt(summary.sd_of_indicator_sds)} | "
            f"{ev.interpret(summary.mean, points, labels)} |"
        )
        out.append("")

    overall_mean = sum(s.mean for s in summaries.values()) / len(summaries)
    out.append("Overall system requirements")
    out.append("")
    out.append("| Characteristic | WM | SD | Interpretation |")
    out.append("| --- | --- | --- | --- |")
    for code, s in summaries.items():
        out.append(
            f"| {names.get(code, code)} | {_fmt(s.mean)} | {_fmt(s.sd_of_indicator_sds)} | "
            f"{ev.interpret(s.mean, points, labels)} |"
        )
    out.append(f"| OVERALL | {_fmt(overall_mean)} | | {ev.interpret(overall_mean, points, labels)} |")
    out.append("")

    if benchmark is None:
        out.append(
            "No benchmark given, so no hypothesis test was run. If the paper will test "
            "the means against a criterion, state it in Chapter 3 before collecting data, "
            "then pass it with --benchmark."
        )
        return "\n".join(out)

    out.append(f"One-sample t-test against {benchmark} (one-tailed, alpha {alpha})")
    out.append("")
    out.append("| Characteristic | n | Mean | SD | t | df | p | Decision |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    small = False
    for code, s in summaries.items():
        r = ev.one_sample_t_greater(s.respondent_means, benchmark, alpha)
        small = small or r.n <= SMALL_N
        decision = "Not tested" if r.reject_null is None else (
            "Reject H0" if r.reject_null else "Fail to reject H0"
        )
        out.append(
            f"| {names.get(code, code)} | {r.n} | {_fmt(r.mean)} | {_fmt(r.sd)} | "
            f"{_fmt(r.t)} | {r.df} | {ev.format_p(r.p)} | {decision} |"
        )
    out.append("")
    out.append(
        "The t-test uses one mean per respondent, taken across that characteristic's "
        "indicators. The SD shown in the first tables is the mean of the indicator SDs, "
        "which is how PROMISE reports it; the SD in this table is the SD of respondent "
        "means, which is what the test needs. The two are different numbers."
    )
    if small:
        out.append("")
        out.append(
            f"Caution: with {SMALL_N} or fewer respondents the test has very little power. "
            f"With 3 respondents there are 2 degrees of freedom and the mean must exceed "
            f"the benchmark by {ev.t_critical_upper(2, alpha):.2f} standard errors to be "
            f"called significant. Report these as descriptive results unless the "
            f"respondent group is larger."
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("csv_path")
    parser.add_argument("--scale", type=int, required=True, help="Number of points, e.g. 4 or 5")
    parser.add_argument("--benchmark", type=float, default=None)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--group", default=None, help="Analyse only this value of the group column")
    parser.add_argument("--labels", default=None, help="Comma-separated, lowest to highest")
    parser.add_argument("--names", default=None,
                        help='JSON, e.g. \'{"FS":"Functional suitability","US":"Usability"}\'')
    parser.add_argument("--out", default=None, help="Also write the report to this file")
    args = parser.parse_args(argv)

    labels = [s.strip() for s in args.labels.split(",")] if args.labels else None
    labels = labels or ev.DEFAULT_LABELS.get(args.scale) or [str(i + 1) for i in range(args.scale)]
    names = json.loads(args.names) if args.names else {}

    try:
        data, ids = read_responses(args.csv_path, args.scale, args.group)
        report = build_report(data, ids, args.scale, labels, names, args.benchmark, args.alpha)
    except ValueError as exc:
        print(f"Cannot analyse: {exc}", file=sys.stderr)
        return 2

    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
