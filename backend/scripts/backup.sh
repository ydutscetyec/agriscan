#!/usr/bin/env bash
# AGRISCAN 2.0 backup.
#
# The most likely catastrophic failure on this project is not a breach or a crash. It is
# a dead laptop two weeks before defence. Run this nightly onto a second drive.
#
#   ./scripts/backup.sh /media/usb/agriscan-backups
#
# Restore instructions: docs/RESTORE.md

set -euo pipefail

DEST="${1:-./backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${DEST}/agriscan-${STAMP}"

DB_HOST="${AGRISCAN_DB_HOST:-127.0.0.1}"
DB_PORT="${AGRISCAN_DB_PORT:-3306}"
DB_USER="${AGRISCAN_DB_USER:-agriscan}"
DB_NAME="${AGRISCAN_DB_NAME:-agriscan}"
IMAGE_ROOT="${AGRISCAN_IMAGE_ROOT:-./data/images}"
MODEL_ROOT="${AGRISCAN_MODEL_ROOT:-./ml/models}"

mkdir -p "${OUT}"
echo "Backing up to ${OUT}"

echo "  1/5 database"
mysqldump --host="${DB_HOST}" --port="${DB_PORT}" --user="${DB_USER}" \
  ${AGRISCAN_DB_PASSWORD:+--password="${AGRISCAN_DB_PASSWORD}"} \
  --single-transaction --routines --triggers --events \
  "${DB_NAME}" > "${OUT}/database.sql"

echo "  2/5 images"
if [ -d "${IMAGE_ROOT}" ]; then
  tar -czf "${OUT}/images.tar.gz" -C "$(dirname "${IMAGE_ROOT}")" "$(basename "${IMAGE_ROOT}")"
else
  echo "     (no image directory at ${IMAGE_ROOT}, skipped)"
fi

echo "  3/5 dataset manifests"
if [ -d "./data/manifests" ]; then
  tar -czf "${OUT}/manifests.tar.gz" -C ./data manifests
else
  echo "     (no manifests yet, skipped)"
fi

echo "  4/5 models"
if [ -d "${MODEL_ROOT}" ]; then
  tar -czf "${OUT}/models.tar.gz" -C "$(dirname "${MODEL_ROOT}")" "$(basename "${MODEL_ROOT}")"
else
  echo "     (no models yet, skipped)"
fi

echo "  5/5 configuration"
# .env holds secrets. It is copied because a restore needs it; keep the backup drive
# somewhere you would keep the laptop itself.
[ -f .env ] && cp .env "${OUT}/env.backup" || echo "     (no .env, skipped)"
cp .env.example "${OUT}/env.example" 2>/dev/null || true

cat > "${OUT}/MANIFEST.txt" <<MANIFEST
AGRISCAN backup ${STAMP}
database:  ${DB_NAME} @ ${DB_HOST}:${DB_PORT}
images:    ${IMAGE_ROOT}
models:    ${MODEL_ROOT}
host:      $(hostname)
MANIFEST

echo "Done. $(du -sh "${OUT}" | cut -f1) in ${OUT}"
echo "Verify the dump is readable before trusting it: head -5 ${OUT}/database.sql"
