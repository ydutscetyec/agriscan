"""Inference time test, after PROMISE's separate reporting of its AI function (p. 76).

PROMISE times every function over repeated trials and then reports the AI response
function on its own: it was the slowest, at a mean of 6.94 seconds, and the paper says
why. response_time_test.py deliberately leaves inference out, because uploading a test
image through the API would write into the research dataset. This times the same stage
functions the worker calls, directly, on image files you name. It touches no database
and writes no file unless you ask for --out.

    python -m scripts.inference_time_test --images ./timing_images --trials 3 \\
        --source phone --model-name yolo26n --out inference_times.md

Read this before quoting a number:

* With the stub detector (the default until weights exist) these are timings of a
  placeholder. The report says so at the top and marks itself not valid for reporting.
* The first prediction is timed separately as the COLD START. A detector that loads its
  weights lazily pays that cost once, and folding it into a mean would hide it. Report
  both: a farmer's first request after the server starts is a cold one.
* Time it on the machine that will run the worker in the field, with the same images a
  farmer would send. A laptop GPU figure describes the wrong computer.
* Images are timed the way production handles them. One that fails the quality gate stops
  there and is not timed through the later stages, so later-stage means cover only the
  images that reached them. The report shows how many that was.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
STAGES = ("quality gate", "palay gate", "detection", "uncertainty", "severity")


# ------------------------------------------------------------------------ timing


def time_once(fn, clock=time.perf_counter):
    """Run fn once. Returns (seconds, result)."""
    start = clock()
    result = fn()
    return clock() - start, result


def summarise(samples: list[float]) -> dict:
    """Mean, sample SD (n - 1), min, max. SD is None below two samples, not zero."""
    n = len(samples)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {
        "n": n,
        "mean": statistics.fmean(samples),
        "sd": statistics.stdev(samples) if n >= 2 else None,
        "min": min(samples),
        "max": max(samples),
    }


def collect_images(paths: list[str]) -> list[str]:
    """Expand files and directories into a sorted list of image files. Reads only."""
    found: list[str] = []
    for raw in paths:
        p = pathlib.Path(raw)
        if p.is_dir():
            found.extend(
                str(f) for f in sorted(p.iterdir()) if f.suffix.lower() in IMAGE_SUFFIXES
            )
        elif p.is_file():
            found.append(str(p))
        else:
            raise FileNotFoundError(raw)
    if not found:
        raise FileNotFoundError("no .jpg, .jpeg or .png files found")
    return found


def _dimensions(path: str) -> tuple[int, int]:
    from PIL import Image as PILImage

    with PILImage.open(path) as img:
        return img.size


def _hardware(cfg) -> dict:
    info = {
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "cuda": None,
    }
    if cfg.DETECTOR_IMPL == "yolo":
        try:  # only worth asking when a real model will run
            import torch

            info["cuda"] = bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001 - absence of torch is itself the answer
            info["cuda"] = None
    return info


# --------------------------------------------------------------------------- run


def run(images: list[str], source: str, trials: int, cfg, model_name: str | None,
        clock=time.perf_counter) -> dict:
    """Time the worker's own stage functions. Nothing here opens a database session."""
    from app.inference import apply_uncertainty, build_detector, build_palay_gate, compute_severity
    from app.services import quality

    gate = build_palay_gate(cfg)
    detector = build_detector(cfg, model_name)
    conf_threshold = cfg.CONF_THRESHOLD
    margin_threshold = cfg.MARGIN_THRESHOLD

    # Cold start: the first prediction, on the first image, before anything is warm.
    cold_seconds, _ = time_once(lambda: detector.predict(images[0], source), clock)

    samples: dict[str, list[float]] = {name: [] for name in STAGES}
    totals: list[float] = []
    stopped = {"quality gate": 0, "palay gate": 0, "completed": 0}

    for _ in range(trials):
        for path in images:
            total = 0.0

            t, verdict = time_once(lambda p=path: quality.assess(p, cfg), clock)
            samples["quality gate"].append(t)
            total += t
            if not verdict["passed"]:
                stopped["quality gate"] += 1
                totals.append(total)
                continue

            t, (is_palay, _conf) = time_once(lambda p=path: gate.is_palay(p), clock)
            samples["palay gate"].append(t)
            total += t
            if not is_palay:
                stopped["palay gate"] += 1
                totals.append(total)
                continue

            t, predictions = time_once(lambda p=path: detector.predict(p, source), clock)
            samples["detection"].append(t)
            total += t

            t, _ = time_once(
                lambda: apply_uncertainty(predictions, conf_threshold, margin_threshold), clock
            )
            samples["uncertainty"].append(t)
            total += t

            width, height = _dimensions(path)
            t, _ = time_once(lambda: compute_severity(predictions, width, height), clock)
            samples["severity"].append(t)
            total += t

            stopped["completed"] += 1
            totals.append(total)

    is_stub = cfg.DETECTOR_IMPL != "yolo"
    return {
        "detector_impl": cfg.DETECTOR_IMPL,
        "palay_gate_impl": cfg.PALAY_GATE_IMPL,
        "model_name": model_name,
        "is_stub": is_stub,
        "valid_for_reporting": not is_stub,
        "source": source,
        "images": len(images),
        "trials": trials,
        "cold_start_seconds": cold_seconds,
        "stages": {name: summarise(vals) for name, vals in samples.items()},
        "total": summarise(totals),
        "stopped": stopped,
        "hardware": _hardware(cfg),
    }


# ------------------------------------------------------------------------ report


def _fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def render(report: dict) -> str:
    lines: list[str] = []
    if report["is_stub"]:
        lines += [
            "> **STUB DETECTOR. These are not model timings.**",
            f"> The configured detector is `{report['detector_impl']}`, a placeholder. Only the "
            "quality-gate row times real work; every other row depends on the placeholder's "
            "output. Do not report this run. Run again once real weights are loaded.",
            "",
        ]
    lines += [
        "# Inference time test",
        "",
        f"Source: {report['source']} · Images: {report['images']} · "
        f"Trials per image: {report['trials']}",
        f"Detector: {report['detector_impl']}"
        + (f" ({report['model_name']})" if report["model_name"] else "")
        + f" · Palay gate: {report['palay_gate_impl']}",
        "",
        f"**Cold start** (first prediction, weights not yet loaded): "
        f"{_fmt(report['cold_start_seconds'])} s. Reported on its own and not included in "
        "the means below.",
        "",
        "| Stage | n | Mean (s) | SD (s) | Min (s) | Max (s) |",
        "|---|---|---|---|---|---|",
    ]
    for name in STAGES:
        s = report["stages"][name]
        lines.append(
            f"| {name} | {s['n']} | {_fmt(s['mean'])} | {_fmt(s['sd'])} | "
            f"{_fmt(s['min'])} | {_fmt(s['max'])} |"
        )
    t = report["total"]
    lines.append(
        f"| **total per image** | {t['n']} | {_fmt(t['mean'])} | {_fmt(t['sd'])} | "
        f"{_fmt(t['min'])} | {_fmt(t['max'])} |"
    )

    st = report["stopped"]
    lines += [
        "",
        f"Where images stopped, across all trials: {st['quality gate']} at the quality gate, "
        f"{st['palay gate']} at the palay gate, {st['completed']} ran every stage. A stage's "
        "mean covers only the images that reached it.",
        "",
    ]
    if any(s["n"] == 1 for s in report["stages"].values()):
        lines += ["SD is not shown where a stage has a single sample.", ""]
    hw = report["hardware"]
    lines += [
        f"Hardware: {hw['platform']} · {hw['processor']} · {hw['cpu_count']} CPUs · "
        f"Python {hw['python']}"
        + (f" · CUDA {'available' if hw['cuda'] else 'not available'}"
           if hw["cuda"] is not None else ""),
        "",
        "Run on the machine that will host the worker in the field, or these describe the "
        "wrong computer.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--images", nargs="+", required=True,
                        help="image files and/or directories of images")
    parser.add_argument("--source", choices=("phone", "drone"), default="phone")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--model-name", default=None,
                        help="required when AGRISCAN_DETECTOR_IMPL=yolo")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if args.trials < 1:
        print("--trials must be at least 1", file=sys.stderr)
        return 2
    try:
        images = collect_images(args.images)
    except FileNotFoundError as err:
        print(f"Not found: {err}", file=sys.stderr)
        return 2

    from app.config import get_config

    cfg = get_config()
    try:
        report = run(images, args.source, args.trials, cfg, args.model_name)
    except RuntimeError as err:  # e.g. MODEL_NOT_AVAILABLE: refuse, never invent a timing
        print(f"Cannot time inference: {err}", file=sys.stderr)
        return 2

    text = render(report)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
