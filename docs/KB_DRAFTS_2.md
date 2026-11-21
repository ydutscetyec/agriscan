# Countermeasures for the remaining 16 modelA_v2 classes

Extract this zip at the repo root. It adds one file,
`backend/scripts/load_knowledge_drafts_2.py`, and this doc. Nothing existing is
modified or overwritten.

## What it fixes

`scripts/load_knowledge_drafts.py` drafts guidance for 9 of modelA_v2's 25 classes.
The other 16 stay at `content_status='PLACEHOLDER'`, so a correct detection on any of
them returns `"PLACEHOLDER — no reviewed agronomic content has been entered..."`.
That is two thirds of what the classifier can output.

This script drafts those 16. After it runs, every class the model can emit has
content, so the website identifies the damage **and** says something about it.

| | before | after |
|---|---|---|
| DRAFT | 17 | 33 |
| PLACEHOLDER | 16 | 0 |

## Run order

Steps 1–4 unblock identification; step 5 is this script. Run from `backend/`.

```bash
cd backend

# 1. Conditions (skip if already done — idempotent either way)
python -m scripts.import_conditions scripts/conditions_modelA_v2.csv

# 2. ultralytics, needed for register_model's class-name check
pip install -r requirements-ml.txt

# 3. Register and promote the trained weights
python -m scripts.register_model \
    --weights /path/to/best.pt \
    --name AGRISCAN-YOLO26n-cls-modelA-v2 \
    --architecture YOLO26n-cls \
    --dataset-version modelA_v2-2026-11-15 \
    --mode ground \
    --production

# 4. Placeholder rows for anything without one
python -m scripts.seed_knowledge

# 5. Real drafted content — placeholders first, then these 16.
#    Run these AFTER seed_knowledge so they overwrite the placeholders it creates.
python -m scripts.load_knowledge_drafts
python -m scripts.load_knowledge_drafts_2
```

Then in `backend/.env`:

```
AGRISCAN_DETECTOR_IMPL=yolo
```

and restart the worker:

```bash
python -m worker.run
```

The 24 queued photos drain on that restart. Until `DETECTOR_IMPL` is `yolo`,
`worker/run.py:stub_refused()` refuses to start on a production env by design — the
worker is not broken, it is declining to write synthetic diagnoses to real farmers.

### Preview without writing

```bash
python -m scripts.load_knowledge_drafts_2 --dry-run
```

Reports what would change, creates no sources, writes nothing. `--force` also
overwrites rows already at DRAFT; without it, existing DRAFT rows are left alone so
your team's edits survive a re-run. `REVIEWED` rows are never touched.

## For the technician review

All 16 land as `DRAFT`. Nothing here is reviewed agronomy and no farmer should act on
it yet. Three things to flag when you hand this to a technician:

**1. Five entries are sourced from outside the Philippines.** PhilRice is used wherever
PhilRice covers the condition — Sheath Blight, Tungro, Rice Black Bug, Rice Bug, Stem
Borer, Leaf Miner/Whorl Maggot, Vertebrate Damage, Weed Presence. It does not cover
Narrow Brown Spot, Sheath Rot or Thrips, and covers the two stunt viruses only in
passing. Those use Arkansas, Sri Lankan and Tamil Nadu sources, whose `locator` field
says so explicitly. Thresholds, varieties and planting dates in the originals are not
Philippine recommendations and need the closest review.

**2. No pesticide, fungicide or herbicide product is named anywhere**, even where a
source named one — several sources name actives that are restricted or banned here.
Every treatment decision routes to a technician holding the current DA/FPA registered
list. 30 fields carry an explicit `NEEDS LOCAL INPUT` marker.

**3. Three classes name a category, not a cause**, and say so in their own text:

- `Abiotic Stress` — covers water deficit, submergence, salinity, heat, cold, nutrient
  toxicity, chemical injury and wind damage. No photograph separates them.
- `Weed Presence` — records that weeds are there, not which species, and species
  determines the management.
- `Nutrient Deficiency` — already handled this way in the sibling script.

The UI must not present any of those as a diagnosis.

### The virus group needs special care

Tungro, Grassy Stunt and Ragged Stunt are three separate classes that cannot be
separated by eye. IRRI reported the first Philippine case of Rice Yellowing Syndrome
in 2025 after a field initially suspected to be tungro turned out to be a co-infection
of RGSV and RRSV; the co-infection shows tungro-like yellow-orange discolouration and
masks the narrow-leaf morphology that would otherwise identify RGSV. IRRI's own
recommendation is RT-PCR, not visual diagnosis.

All three entries carry that warning in `identification_cues`. This matters
operationally, not just academically: tungro is managed against green leafhopper and
the stunt viruses against brown planthopper, so a misidentification aims the whole
response at the wrong insect. Zinc deficiency is also documented as producing similar
symptoms.

If a panel asks about the model's weakest point, this is an honest answer: three
classes in the taxonomy are not visually separable, and the system is written to say
so rather than to guess.

## Sources

PhilRice (Major diseases of the rice plant in the Philippines; Harmful organisms in
Philippine rice fields; Field Guide: Harmful and useful organisms in Philippine rice
fields; Weeds in irrigated and rainfed lowland ricefields in the Philippines), IRRI
(Rice Yellowing Syndrome detection training, 2026), Pacific Pests, Pathogens and Weeds
(fact sheets 428 and 430), Philippine Journal of Science (Donayre et al. 2023),
Frontiers in Plant Science (Bigirimana et al. 2015), University of Arkansas Cooperative
Extension (FSA2213), Department of Agriculture Sri Lanka (RRDI), TNAU Agritech Portal.

Full citation details, including access dates and origin caveats, are in the
`SOURCES` dict at the top of the script and are written to `knowledge_sources` on
first run.
