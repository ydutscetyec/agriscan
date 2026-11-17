#!/bin/sh
# Run the test suite under a timezone other than UTC, so a bug that only appears
# at a UTC offset cannot hide behind a UTC test container. This is what the p38
# capture-session bug needed and did not have.
#
# Two clocks have to be offset for this to prove anything:
#   - the application's, via TZ
#   - the database server's, via AGRISCAN_TEST_DB_TZ (SET time_zone on connect)
# Pass extra pytest arguments through, e.g. ./run_tests_offset_tz.sh -k capture
set -e

# backend/, not backend/scripts/ — pytest collects nothing from scripts/ and
# exits 5, which reads like a clean run to anyone skimming the output.
cd "$(dirname "$0")/.."

TZ="${AGRISCAN_TEST_TZ:-Asia/Manila}" \
AGRISCAN_TEST_DB_TZ="${AGRISCAN_TEST_DB_TZ:-+08:00}" \
  python -m pytest "$@"
