# AGRISCAN 2.0 — Backend foundation (Prompt 1)

Flask + MariaDB backend: schema, migrations, authentication, RBAC, ownership checks,
and CRUD for users, farms, fields, missions and conditions.

**Stage 2 adds:** image ingestion with EXIF geotagging, quality gate S1, palay gate S2,
a polling inference worker, uncertainty handling S4 and experimental severity S5.

**Not in this stage:** a trained model, the dashboard, verification and recommendations.
Those are Prompts 3 and 4.

## Migration style

**Plain SQL, not Alembic.** The schema uses MariaDB-specific features (ENUM, JSON
columns, triggers with SIGNAL) that Alembic autogenerate handles poorly, and the team
must be able to read exactly what runs. Cost: downgrades are manual. Applied files are
tracked in `schema_migrations`.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env                            # then edit it
python -c "import secrets; print(secrets.token_urlsafe(48))"   # AGRISCAN_SECRET_KEY
```

Create the database user in XAMPP's MariaDB (do not use the default blank-password root):

```sql
CREATE USER 'agriscan'@'localhost' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON agriscan.* TO 'agriscan'@'localhost';
FLUSH PRIVILEGES;
```

Then:

```bash
python -m migrations.run_migrations            # apply
python -m migrations.run_migrations --status   # list applied/pending
python -m scripts.seed                         # Tier 1 taxonomy (reference data)
python -m scripts.seed --with-demo             # + synthetic rows, all is_demo=TRUE
python run.py                                  # http://127.0.0.1:5000
```

## Tests

```bash
python -m pytest tests/ -q
```

Tests run against a **real MariaDB** test database (`agriscan_test`), dropped and
re-migrated each session. They are not run on SQLite, because the immutability
guarantee is a MariaDB trigger and testing it elsewhere would prove nothing.

## What is enforced, and where

| Guarantee | Enforced by |
| --- | --- |
| Rule 1: detections immutable (condition, confidence, model, image) | DB trigger `trg_detections_immutable` |
| Detection `status` may still change | Same trigger, deliberately excluded |
| Audit log append-only | Triggers `trg_audit_log_no_update` / `no_delete` |
| Role cannot be escalated via token claim | `app/auth/decorators.py` re-reads the DB row |
| Farmer sees only own farm's rows | `app/services/ownership.py`, applied server-side |
| Passwords never stored or returned in plaintext | Argon2id; `to_dict()` omits the hash |

## Growth stage

Derived, never stored on the field. Rule `dat-v1`, thresholds configurable:
vegetative 0–55 DAT, reproductive 56–90, ripening 91–125, beyond that post_harvest.
Missing planting date returns `DATA_REQUIRED`, which is a legitimate state, not an error.
`GET /fields/<id>?observation_date=YYYY-MM-DD` returns the stage plus the evidence
(days after planting, method, rule version).

## Endpoints

```
POST   /auth/login            GET /auth/me         GET /health
GET    /users                 POST /users                      (admin)
GET    /farms                 POST /farms
GET    /fields                POST /fields
GET    /fields/<id>           PUT  /fields/<id>    DELETE /fields/<id>
GET    /missions              POST /missions       GET /missions/<id>
GET    /conditions            POST /conditions                 (admin, researcher)
```


## Ingestion and inference (Prompt 2)

Run the worker in a second terminal:

```bash
python -m worker.run
```

It refuses to start unless a `model_versions` row has `deployment_status='production'`
for the imaging mode it needs. That is deliberate: a detection whose model cannot be
named is unusable in Chapter 4.

### Pipeline

`POST /images` → validate → SHA-256 duplicate check → EXIF GPS (from the original bytes)
→ re-encode with Pillow → store at `<IMAGE_ROOT>/<year>/<month>/<uuid>.jpg` → enqueue →
**202**. The request never waits on inference.

The worker then runs: quality gate (S1) → palay gate (S2) → detector (S3) →
uncertainty (S4) → severity (S5).

### What is enforced here

| Guarantee | Enforced by |
| --- | --- |
| One record per unique file | `images.content_hash` UNIQUE + pre-insert check |
| Client filename never used | server UUID in `app/services/storage.py` |
| Uploaded bytes sanitised | Pillow decode/re-encode round trip |
| Missing GPS accepted, flagged | `gps_source='missing'`, `Position missing.` |
| Rejected images stored, not deleted | `images.quality_flag`, no detection written |
| Drone frames cannot carry lesion labels | `conditions.aerial_allowed` + worker filter |
| Low confidence becomes UNKNOWN | `apply_uncertainty()`, thresholds from config/model |
| Severity is marked experimental | every response carries `severity_status` |
| No model, no detection | worker exits 2 with `MODEL_NOT_AVAILABLE` |

### Severity is a proxy, not a measurement

`bbox_area_fraction` is the union of detection boxes over whole-image area. A bounding
box contains healthy tissue and there is no canopy mask, so this over-counts. It is
`EXPERIMENTAL` and `NOT_VALIDATED` until compared against technician severity scoring
(experiment E5). Do not put it in a results table yet.

### Swapping in a real model

1. Put weights at `ml/models/<model_name>/weights.pt`.
2. Insert a `model_versions` row whose `name` matches `<model_name>`.
3. Set `AGRISCAN_DETECTOR_IMPL=yolo` and mark that row `deployment_status='production'`.

No API contract changes. `StubDetector` output is DEMO_DATA and must never be reported.

### New endpoints

```
POST /images                    multipart: file, field_id, source[, mission_id]
GET  /images/<id>               record, quality flag, job status + result, detections
GET  /detections                ?field_id= &source= &status= &condition=
                                &min_confidence= &date_from= &date_to=
                                &include_demo= &limit= &offset=
```

## Verification and recommendations (Prompt 4)

```bash
python -m scripts.seed_knowledge   # placeholder knowledge base, all PLACEHOLDER
```

### Endpoints

```
POST /detections/<id>/feedback     farmer: {agrees, comment}
POST /detections/<id>/verify       technician: {decision, corrected_condition,
                                                severity_score, notes}
GET  /verification-queue           ?limit= &sample_rate=
GET  /analysis/confusion-matrix    ?model_version= &date_from= &date_to= &include_demo=
GET  /analysis/agreement           ?include_demo=
GET  /recommendations/<detection_id>
POST /recommendations/<detection_id>/generate
POST /recommendations/<id>/approve | /reject
GET  /recommendations/pending
```

### What is enforced

| Guarantee | Enforced by |
| --- | --- |
| Farmer feedback never changes a diagnosis | feedback writes only `farmer_feedback`; status may reach `farmer_confirmed` and no further |
| A correction never edits the detection | correction writes `verifications.corrected_condition_id`; DB trigger blocks the alternative |
| Confusion matrix is a query | built by JOIN on every request; nothing cached |
| Ungrounded dosages never reach a farmer | `validate_output()` rejects output containing rates or product names absent from the retrieved records |
| No advice without sign-off | `approved_by IS NULL` → farmer response carries `Pending technician review.` and no text |
| Repeat cases need no model call | approved text cached by condition + severity band + growth stage |

### Two mechanisms, not one

The LLM system prompt forbids naming a pesticide, rate or interval not present in the
retrieved records. That is a request. `validate_output()` then checks what was actually
produced and replaces it with `Consult an agricultural technician.` if it names anything
ungrounded. Only the second is enforcement.

The default phraser is `TemplatePhraser`, which assembles knowledge base text
deterministically — no model call, no internet, nothing to invent. `LLMPhraser` is a
wired interface requiring `AGRISCAN_LLM_API_KEY`; its output must pass the same validator.

### Queue priority

Low confidence → high severity → farmer-rejected → a random sample of high-confidence
predictions (`AGRISCAN_QUEUE_SAMPLE_RATE`, default 10%, above
`AGRISCAN_QUEUE_CONFIDENT_MIN`, default 0.80). Each item shows why it is in the queue.
The fourth stream is the one that finds confident errors; without it the verified set is
biased toward cases the model already found hard.

### Keyboard

`c` correct · `x` corrected · `u` cannot determine · `0`–`3` severity · `n` notes ·
`j`/`k` move between cases.

## Deployment (p21)

See `DEPLOY.md` in the project root. In short:

```bash
python serve.py --check     # preflight: config, database, migrations, build, accounts
python serve.py             # web app + API on http://127.0.0.1:8080, API under /api
python -m worker.run        # beside it
```

`run.py` is still the development server behind `npm run dev`.

### New endpoints

```
POST /auth/password              any role: {current_password, new_password} -> new token
PUT  /users/<id>                 admin: {role, active, barangay, name}
POST /users/<id>/password        admin: {password}; ends that account's sessions
GET  /health                     database, queue depth, oldest waiting, production models
```

### Scripts

```
python -m scripts.create_admin           first real admin, or reset one
python -m scripts.preflight              the same checks serve.py runs
python -m scripts.register_model ...     register trained weights (see DEPLOY.md)
python -m scripts.import_conditions f.csv
scripts\backup.ps1                       Windows backup (backup.sh on Linux)
```

### What is enforced, added in p21

| Guarantee | Enforced by |
| --- | --- |
| Password change or reset ends old sessions | token `pwv` claim vs `users.password_changed_at` |
| Sign-in guessing is bounded | `login_failed` rows in `audit_log`, per name and per address |
| Production never runs the stub detector | `worker/run.py stub_refused()` |
| Production never starts with demo passwords | `app/services/preflight.py` |
| Paths do not depend on the working directory | `app/config.py resolve_path()` |


## Running the tests

```bash
python -m pytest tests/            # the suite
TZ=Asia/Manila python -m pytest tests/   # and again at a UTC offset
```

Run it both ways. Every stored timestamp is naive UTC, and a comparison that accidentally
uses local time is invisible on a UTC machine and eight hours wrong in Surallah. That
exact bug expired every capture session seconds after it started while the whole suite
passed. `tests/test_p38_clock.py` covers it, but only the offset run proves it.

All times go through `app/utils/clock.utc_now()`. Nothing should call
`datetime.now()` without a timezone.
