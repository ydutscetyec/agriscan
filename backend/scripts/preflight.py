"""Check that this machine is ready to serve AGRISCAN publicly.

    python -m scripts.preflight

Exit code 0 when nothing failed. serve.py runs the same checks on start, and refuses to
start in production if any of them fail.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import get_config  # noqa: E402
from app.services import preflight  # noqa: E402


def main() -> int:
    cfg = get_config()
    print(f"AGRISCAN preflight ({cfg.ENV})\n")
    return 0 if preflight.print_report(preflight.run_all(cfg)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
