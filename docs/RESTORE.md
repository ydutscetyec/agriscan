# Restoring AGRISCAN from a backup

Written for the case where it matters: a dead laptop, a corrupted database, or a fresh
machine a week before defence. Follow it in order.

## What a backup contains

```
agriscan-YYYYMMDD-HHMMSS/
  database.sql      mysqldump, with triggers and routines
  images.tar.gz     the image store
  manifests.tar.gz  dataset manifests
  models.tar.gz     trained model weights and metadata
  env.backup        the .env that machine was running
  MANIFEST.txt      what was backed up, from where
```

## 1. Restore the database

```bash
mysql -u root -p -e "CREATE DATABASE agriscan CHARACTER SET utf8mb4;"
mysql -u root -p -e "CREATE USER 'agriscan'@'localhost' IDENTIFIED BY 'your-password';
                     GRANT ALL PRIVILEGES ON agriscan.* TO 'agriscan'@'localhost';
                     FLUSH PRIVILEGES;"
mysql -u agriscan -p agriscan < agriscan-YYYYMMDD-HHMMSS/database.sql
```

Then confirm the integrity triggers survived — a dump restored without them silently
loses the immutability guarantee:

```sql
SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = 'agriscan';
-- expect: trg_detections_immutable, trg_audit_log_no_update, trg_audit_log_no_delete
```

If they are missing, re-run migration 002:

```bash
python -m migrations.run_migrations
```

## 2. Restore the files

```bash
tar -xzf images.tar.gz    -C /path/to/agriscan/backend/data/
tar -xzf manifests.tar.gz -C /path/to/agriscan/backend/data/
tar -xzf models.tar.gz    -C /path/to/agriscan/backend/ml/
```

Image paths are stored in the database as relative paths under `AGRISCAN_IMAGE_ROOT`. If
you restore them somewhere else, set that variable to match rather than editing rows.

## 3. Restore configuration

```bash
cp env.backup /path/to/agriscan/backend/.env
```

Change `AGRISCAN_SECRET_KEY` if the backup drive has been out of your control. Changing
it signs everyone out; it does not affect stored data.

## 4. Verify before you trust it

```bash
python -m migrations.run_migrations --status   # all APPLIED
python -m pytest tests/ -q                     # full suite
python run.py                                  # then open the dashboard
```

Spot-check one detection end to end: open it on the map, confirm the image loads and the
model version is still named. An image that 404s means the file restore path is wrong.

## Backup schedule

Nightly, onto a drive that does not live in the same bag as the laptop. Test a restore
once, on a different machine, before you need it. An untested backup is a guess.
