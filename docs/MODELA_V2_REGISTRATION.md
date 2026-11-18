# Registering modelA_v2 (ground-track YOLO26n-cls)

Written because this registration needed a decision, not just a command: the trained
weights' 25 classes did not match the 9-code demo taxonomy in `scripts.seed`. Run this
once, in order, on a machine with MariaDB running and `requirements-ml.txt` installed —
neither was available in the environment that prepared this.

## What this is

`modelA_v2` (architecture `YOLO26n-cls`, `task: classify`, trained from
`/content/dataset`, `imgsz 224`, 60 epochs before early stopping on patience 20,
final `metrics/accuracy_top1 = 0.889`, `accuracy_top5 = 0.969` — see
`results.csv`/`args.yaml` in the Google Drive run folder `AGRISCAN_runs/modelA_v2`)
outputs 25 class names read directly off the checkpoint:

```
Abiotic Stress, Bacterial Leaf Blight-Streak, Brown Spot, False Smut, Flooding,
Grassy Stunt Virus, Healthy Rice plant, Hopper, Leaf Blast, Leaf Miner-Whorl Maggot,
Lodging-Physical Damage, Narrow Brown Spot, Neck-Panicle Blast, Nutrient Deficiency,
Ragged Stunt Virus, Rice Black Bug, Rice Bug, Sheath Blight, Sheath Rot, Stem Borer,
Stem Rot, Thrips, Tungro, Vertebrate Damage, Weed Presence
```

None of these are in the taxonomy `scripts.seed` creates (`healthy`,
`bacterial_leaf_blight`, `rice_blast`, `brown_spot`, `hopperburn`,
`nitrogen_deficiency`, `lodging`, `flooding`, `unknown` — a pre-model demo set).
`scripts.register_model` requires an exact string match between a model's class name
and a `conditions.code`; registering against the demo taxonomy would either refuse to
promote, or (with `--allow-unmatched`) promote while the worker silently drops every
prediction, because none of the 25 classes would resolve to a condition.

Decision taken: add all 25 as new conditions (not collapsed onto the old 9), so no
class the model can output is ever dropped. `scripts/conditions_modelA_v2.csv` carries
them, categorized against the existing `CONDITION_CATEGORIES` enum (`fungal`,
`bacterial`, `viral`, `pest`, `nutritional`, `abiotic`, `physical`, `weed`, `healthy`).

Two blast classes (`Leaf Blast`, `Neck-Panicle Blast`) stay as separate condition codes
even though `scripts/seed.py` documents blast as "ONE disease ... never four separate
classes" — that principle is about not fragmenting the *taxonomy*; here it's the
*classifier* that already outputs two distinct labels, and collapsing them at the
condition level would mean one of the two is silently dropped by the worker. Both rows
share `scientific_name=Pyricularia oryzae` and differ only in `plant_part` (`leaf` vs
`neck_panicle`), which keeps them connected without losing either signal. Revisit this
if a future model version merges them back into one class.

## Steps

```bash
cd backend

# 1. Add the 25 new conditions (idempotent; skips codes that already exist)
python -m scripts.import_conditions scripts/conditions_modelA_v2.csv

# 2. Placeholder knowledge-base text for every condition that doesn't have a row yet,
#    including the 25 new ones (seed_knowledge.py's CONDITIONS list was extended to
#    cover them). These are content_status=PLACEHOLDER, not agronomy -- the UI must
#    label them as unusable until someone replaces the text with DA/PhilRice/BPI/IRRI
#    guidance and sets content_status=REVIEWED.
python -m scripts.seed_knowledge

# 3. ultralytics is required for register_model's class-name check. Without it the
#    check is skipped entirely (register_model.py logs this and proceeds), which is
#    *not* safe to combine with --production on a model whose classes you haven't
#    independently verified -- install it first.
pip install -r requirements-ml.txt

# 4. Register and promote. Point --weights at best.pt from the Google Drive run
#    (AGRISCAN_runs/modelA_v2/weights/best.pt), or wherever you copied it locally.
python -m scripts.register_model \
    --weights /path/to/best.pt \
    --name AGRISCAN-YOLO26n-cls-modelA-v2 \
    --architecture YOLO26n-cls \
    --dataset-version modelA_v2-2026-11-15 \
    --mode ground \
    --production

# 5. Point the worker at it and restart.
```

In `backend/.env`, set:

```
AGRISCAN_DETECTOR_IMPL=yolo
```

then restart the worker:

```bash
python -m worker.run
```

## After registering

- `model_versions.capability_status` starts at `NOT_VALIDATED` (set by
  `register_model.py` itself) regardless of the training-run accuracy figures above --
  that status only changes once technician-verified detections exist to measure
  against. Don't report the Colab validation accuracy as the deployed model's
  real-world capability; they're not the same claim.
- Every recommendation for these 25 conditions will read the generic
  `"PLACEHOLDER — no reviewed agronomic content has been entered..."` text (or the
  `TemplatePhraser` fallback) until real knowledge-base content is entered per
  condition. The pipeline runs end-to-end now; the agronomy still needs writing.
- `conditions.tier` was left `NULL` for the 25 new rows (`scripts.import_conditions`
  has no column for it). `scripts/seed.py`'s original 9 use `tier=1`. If you want these
  tracked as a distinct training cycle for Chapter 4, set `tier=2` on them, e.g.:
  ```sql
  UPDATE conditions SET tier = 2
  WHERE code IN (
    'Healthy Rice plant','Bacterial Leaf Blight-Streak','Brown Spot',
    'Narrow Brown Spot','Leaf Blast','Neck-Panicle Blast','Sheath Blight',
    'Sheath Rot','Stem Rot','False Smut','Tungro','Grassy Stunt Virus',
    'Ragged Stunt Virus','Hopper','Rice Black Bug','Rice Bug','Stem Borer',
    'Thrips','Leaf Miner-Whorl Maggot','Nutrient Deficiency','Abiotic Stress',
    'Flooding','Lodging-Physical Damage','Vertebrate Damage','Weed Presence'
  );
  ```
