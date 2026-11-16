"""Dataset manifest checks: field-level split validation and the minimum-sample rule.

Two failures this guards against, both of which quietly inflate results:

  1. Field leakage. Splitting at image level puts near-duplicate frames of the same
     plant into train and test. Accuracy then measures memorisation.
  2. A class trained on too little data, reported as if it were a finding.

Usage:
    python -m scripts.validate_split path/to/manifest.json
    python -m scripts.validate_split path/to/manifest.json --strict-samples

Exit code 0 means the manifest is usable. Anything else means it is not, and the reason
is printed. The script is deliberately loud: a silent pass here is how a bad number gets
into a defended paper.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

MIN_SAMPLES_PER_CLASS = 150
MIN_FIELDS_PER_CLASS = 3
MIN_VISIT_DATES_PER_CLASS = 2

SPLITS = ("train", "validation", "test")
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
TRAINABLE = "TRAINABLE"


def load_manifest(path: str | pathlib.Path) -> dict:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if "images" not in data:
        raise ValueError("Manifest has no 'images' list.")
    return data


def check_field_leakage(manifest: dict) -> dict:
    """No field may appear in more than one split. This is the important one."""
    fields_by_split = {split: set() for split in SPLITS}
    unknown_splits = set()

    for entry in manifest["images"]:
        split = entry.get("split")
        field_id = entry.get("field_id")
        if split not in fields_by_split:
            unknown_splits.add(split)
            continue
        if field_id is None:
            raise ValueError(f"Image {entry.get('image_id')} has no field_id.")
        fields_by_split[split].add(field_id)

    leaks = []
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            shared = fields_by_split[a] & fields_by_split[b]
            for field_id in sorted(shared):
                leaks.append({"field_id": field_id, "splits": [a, b]})

    return {
        "ok": not leaks and not unknown_splits,
        "leaks": leaks,
        "unknown_splits": sorted(s for s in unknown_splits if s is not None),
        "fields_per_split": {k: sorted(v) for k, v in fields_by_split.items()},
    }


def check_minimum_samples(manifest: dict) -> dict:
    """A class is trainable only with enough samples, fields and visit dates."""
    per_class = collections.defaultdict(
        lambda: {"count": 0, "fields": set(), "dates": set(), "verified": 0}
    )

    for entry in manifest["images"]:
        label = entry.get("condition")
        if not label:
            continue
        bucket = per_class[label]
        bucket["count"] += 1
        bucket["fields"].add(entry.get("field_id"))
        if entry.get("captured_on"):
            bucket["dates"].add(str(entry["captured_on"])[:10])
        if entry.get("verified"):
            bucket["verified"] += 1

    classes = {}
    for label, bucket in sorted(per_class.items()):
        reasons = []
        if bucket["verified"] < MIN_SAMPLES_PER_CLASS:
            reasons.append(
                f"{bucket['verified']} verified samples, need {MIN_SAMPLES_PER_CLASS}"
            )
        if len(bucket["fields"]) < MIN_FIELDS_PER_CLASS:
            reasons.append(f"{len(bucket['fields'])} fields, need {MIN_FIELDS_PER_CLASS}")
        if len(bucket["dates"]) < MIN_VISIT_DATES_PER_CLASS:
            reasons.append(
                f"{len(bucket['dates'])} visit dates, need {MIN_VISIT_DATES_PER_CLASS}"
            )
        classes[label] = {
            "total": bucket["count"],
            "verified": bucket["verified"],
            "fields": len(bucket["fields"]),
            "visit_dates": len(bucket["dates"]),
            "status": INSUFFICIENT_DATA if reasons else TRAINABLE,
            "reasons": reasons,
        }

    trainable = [k for k, v in classes.items() if v["status"] == TRAINABLE]
    return {"classes": classes, "trainable": sorted(trainable), "ok": bool(trainable)}


def validate(manifest: dict) -> dict:
    leakage = check_field_leakage(manifest)
    samples = check_minimum_samples(manifest)
    return {"leakage": leakage, "samples": samples, "ok": leakage["ok"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument(
        "--strict-samples",
        action="store_true",
        help="also fail when no class meets the minimum-sample rule",
    )
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: could not read manifest: {exc}", file=sys.stderr)
        return 2

    report = validate(manifest)
    leakage = report["leakage"]
    samples = report["samples"]

    print(f"Manifest: {args.manifest}")
    print(f"Images:   {len(manifest['images'])}")
    for split, fields in leakage["fields_per_split"].items():
        print(f"  {split:<11} {len(fields)} field(s): {fields}")

    print("\nClass sample check:")
    for label, info in samples["classes"].items():
        mark = "OK " if info["status"] == TRAINABLE else "NO "
        print(
            f"  {mark}{label:<26} verified={info['verified']:<5} "
            f"fields={info['fields']:<3} dates={info['visit_dates']:<3} "
            f"{'; '.join(info['reasons'])}"
        )

    if not leakage["ok"]:
        print("\nFAIL: field-level split violated.", file=sys.stderr)
        for leak in leakage["leaks"]:
            print(
                f"  field {leak['field_id']} appears in {' and '.join(leak['splits'])}",
                file=sys.stderr,
            )
        for split in leakage["unknown_splits"]:
            print(f"  unknown split label: {split}", file=sys.stderr)
        print(
            "\nA field in two splits makes every reported metric an overestimate. "
            "Reassign whole fields and re-run.",
            file=sys.stderr,
        )
        return 1

    if args.strict_samples and not samples["ok"]:
        print(
            "\nFAIL: no class meets the minimum-sample rule "
            f"({MIN_SAMPLES_PER_CLASS} verified samples, {MIN_FIELDS_PER_CLASS} fields, "
            f"{MIN_VISIT_DATES_PER_CLASS} visit dates).",
            file=sys.stderr,
        )
        return 1

    print(f"\nPASS: no field leakage. Trainable classes: {samples['trainable'] or 'none yet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
