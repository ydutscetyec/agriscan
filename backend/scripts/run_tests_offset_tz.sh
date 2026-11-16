#!/bin/sh
# Run the test suite under a timezone other than the machine's, so a bug that only
# appears at a UTC offset cannot hide behind a UTC test container.
cd "$(dirname "$0")"
TZ="${AGRISCAN_TEST_TZ:-Asia/Manila}" python -m pytest "$@"
