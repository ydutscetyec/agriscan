# AGRISCAN

Drone-based palay (*Oryza sativa*) monitoring and crop-damage detection system.

A smartphone mounted on a drone captures frames over a rice field. The frames are
uploaded, classified by a YOLO model, and surfaced in a web dashboard where an
agricultural technician verifies or corrects each detection. The technician's
verdict — not the model's confidence — is the system's ground truth.

Research 1 project, Libertad National High School, Surallah, South Cotabato.

## Status

Work in progress. This repository is the code; it is not a deployed instance.

## Layout

```
backend/     Flask + SQLAlchemy API, MariaDB
  app/       routes, models, services
  worker/    detection worker (polls the job queue)
  scripts/   seed, migration runner, model registration
  migrations/
web/         React + Vite single-page frontend
```

## Running it locally

Requires Python 3.12, Node 18+, and MariaDB (XAMPP works).

```bash
# backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # PowerShell;  source .venv/bin/activate on Linux
pip install -r requirements.txt
cp .env.example .env                 # then fill in the real values
python -m scripts.run_migrations
python -m scripts.seed
python serve.py --check              # preflight; fix anything it reports
python serve.py

# frontend
cd web
npm ci
cp .env.example .env
npm run dev
```

The detection worker runs separately:

```bash
cd backend
python -m worker.run
```

## Configuration

Both `backend/` and `web/` read a `.env` that is **not** in this repository.
Copy the matching `.env.example` and fill it in. `backend/.env` holds the database
URL and `AGRISCAN_SECRET_KEY`; generate a fresh secret rather than reusing one.

`AGRISCAN_DETECTOR_IMPL` selects the detector. It defaults to a stub that refuses
to produce detections; set it to `yolo` once real weights are registered.

## Models

Two models, trained separately:

- **Model A** — close-range classifier for smartphone photos taken at the plant.
- **Model B** — wide-area classifier for drone imagery. Different dataset, image
  size and class list.

Weights are not committed. Train in Colab, then register the resulting `best.pt`:

```bash
python -m scripts.register_model --weights ml/best.pt --mode ground --production
```

Registration refuses to promote weights whose class names do not match the codes
in the `conditions` table. That check is deliberate — a promoted model with
misaligned labels files every detection under the wrong condition, silently.

## Before exposing this publicly

`scripts/seed.py` creates demo accounts with a published password. Deactivate
them before the instance is reachable from the internet:

```sql
UPDATE users SET active = 0 WHERE is_demo = 1;
```
