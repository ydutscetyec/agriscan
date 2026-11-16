"""Functional response-time test, after PROMISE's Phase 5 (pp. xviii, xxx).

PROMISE times each of its functions over three repeated trials and reports the mean and
SD. This does the same for the AGRISCAN functions a user waits on.

    python -m scripts.response_time_test --base-url http://127.0.0.1:5000 \\
        --user "DEMO Technician" --trials 3 --target-seconds 3.0 --out response_times.md

Read this before quoting a number:

* It times the server it is pointed at. Run it on the machine that will host AGRISCAN in
  the field, not on a development laptop, or the figures describe the wrong computer.
* Response time depends on how much data is stored, so the report prints the row counts
  it ran against. A figure measured on an empty demo database is not a field figure.
* The target is not defaulted. Fix it in Chapter 3 before testing; a target chosen after
  seeing the means is not a target.
* It does NOT time image upload or model inference. Uploading a test image would write
  into the research dataset, and inference time belongs with the model it measures.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import statistics
import sys
import time
import urllib.error
import urllib.request


# ------------------------------------------------------------------- transports


class UrllibTransport:
    """Talks to a running server over HTTP, standard library only."""

    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None

    def request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            return 0, str(exc).encode()


class FlaskTransport:
    """The same interface over a Flask test client, so the tests need no server."""

    def __init__(self, client):
        self.client = client
        self.token: str | None = None

    def request(self, method: str, path: str, body: dict | None = None):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        resp = self.client.open(path, method=method, json=body, headers=headers)
        return resp.status_code, resp.get_data()


# --------------------------------------------------------------------- measuring


def time_call(call, trials: int, clock=time.perf_counter) -> dict:
    """Run `call` `trials` times. `call` returns True when the response was a success."""
    seconds: list[float] = []
    failures = 0
    for _ in range(trials):
        start = clock()
        ok = call()
        elapsed = clock() - start
        if ok:
            seconds.append(elapsed)
        else:
            failures += 1
    return {
        "trials": seconds,
        "failures": failures,
        "mean": statistics.fmean(seconds) if seconds else None,
        "sd": statistics.stdev(seconds) if len(seconds) >= 2 else None,
        "max": max(seconds) if seconds else None,
    }


def _ok(status: int) -> bool:
    return 200 <= status < 300


def _json(raw: bytes):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def run(transport, user: str, password: str, trials: int = 3, clock=time.perf_counter) -> dict:
    """Time the read-only functions. Returns results plus the conditions they ran under."""
    results: list[dict] = []

    def login():
        status, raw = transport.request("POST", "/auth/login", {"name": user, "password": password})
        body = _json(raw) or {}
        if _ok(status) and body.get("token"):
            transport.token = body["token"]
            return True
        return False

    # Sign-in is timed, and it also provides the token everything else needs.
    results.append({"function": "Sign in", **time_call(login, trials, clock)})
    if not transport.token:
        return {"results": results, "conditions": {}, "aborted": "Sign-in failed."}

    def get(path):
        return lambda: _ok(transport.request("GET", path)[0])

    # Row counts first: they are part of the test conditions, and give us ids to open.
    _, raw = transport.request("GET", "/detections?include_demo=true&limit=1")
    listing = _json(raw) or {}
    total_detections = listing.get("total", listing.get("count"))
    first_detection = (listing.get("detections") or [{}])[0]
    detection_id = first_detection.get("id")
    image_id = first_detection.get("image_id")
    _, raw = transport.request("GET", "/fields")
    fields = _json(raw)

    plan = [
        ("Session check", get("/auth/me")),
        ("Field list", get("/fields")),
        ("Field boundaries summary", get("/fields-summary")),
        ("Detections, one page of 50", get("/detections?include_demo=true&limit=50")),
        ("Detections, dashboard load of 500", get("/detections?include_demo=true&limit=500")),
        ("Verification queue", get("/verification-queue")),
        ("Confusion matrix", get("/analysis/confusion-matrix?include_demo=true")),
        ("Model registry", get("/models")),
        ("Pending recommendations", get("/recommendations/pending")),
    ]
    if detection_id is not None:
        plan.append(("Detection detail", get(f"/detections/{detection_id}")))
    if image_id is not None:
        plan.append(("Image file", get(f"/images/{image_id}/file")))

    for name, call in plan:
        results.append({"function": name, **time_call(call, trials, clock)})

    skipped = []
    if detection_id is None:
        skipped.append("Detection detail and Image file (no detections stored)")

    return {
        "results": results,
        "skipped": skipped,
        "conditions": {
            "detections_stored": total_detections,
            "fields_stored": len(fields) if isinstance(fields, list) else None,
        },
        "aborted": None,
    }


# ---------------------------------------------------------------------- reporting


def _f(x, d=3):
    return "n/a" if x is None else f"{x:.{d}f}"


def render(report: dict, trials: int, target: float | None, base_url: str) -> str:
    lines: list[str] = []
    lines.append("Test conditions")
    lines.append("")
    lines.append(f"- Server: {base_url}")
    lines.append(f"- Run from: {platform.node()} ({platform.system()}, Python {platform.python_version()})")
    lines.append(f"- Date: {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- Trials per function: {trials}")
    cond = report.get("conditions") or {}
    lines.append(f"- Detections stored: {cond.get('detections_stored', 'unknown')}")
    lines.append(f"- Fields stored: {cond.get('fields_stored', 'unknown')}")
    lines.append(
        f"- Target: {target} s" if target is not None
        else "- Target: none given. State one in Chapter 3 before testing."
    )
    lines.append("")

    if report.get("aborted"):
        lines.append(f"Test stopped: {report['aborted']}")
        return "\n".join(lines)

    head = "| Function | Trial times (s) | Mean (s) | SD (s) |"
    rule = "| --- | --- | --- | --- |"
    if target is not None:
        head += " Within target |"
        rule += " --- |"
    lines += [head, rule]
    for r in report["results"]:
        times = ", ".join(f"{t:.3f}" for t in r["trials"]) or "none"
        if r["failures"]:
            times += f" ({r['failures']} failed)"
        row = f"| {r['function']} | {times} | {_f(r['mean'])} | {_f(r['sd'])} |"
        if target is not None:
            if r["mean"] is None or r["failures"]:
                row += " Not met (failed) |"
            else:
                row += f" {'Yes' if r['mean'] <= target else 'No'} |"
        lines.append(row)
    if report.get("skipped"):
        lines += ["", "Not measured: " + "; ".join(report["skipped"]) + "."]
    lines += [
        "",
        "Image upload and model inference are not timed here. See the notes at the top of "
        "scripts/response_time_test.py.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default=os.environ.get("AGRISCAN_TEST_PASSWORD"))
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--target-seconds", type=float, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    password = args.password or getpass.getpass(f"Password for {args.user}: ")
    report = run(UrllibTransport(args.base_url), args.user, password, args.trials)
    text = render(report, args.trials, args.target_seconds, args.base_url)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 1 if report.get("aborted") else 0


if __name__ == "__main__":
    raise SystemExit(main())
