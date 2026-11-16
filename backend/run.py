"""Development entrypoint: python run.py

Checks the database before serving. A schema that is behind the code used to surface as
"Internal server error" at sign-in, with the real reason (an unknown column) only in the
terminal — which is exactly how an afternoon gets lost. Now it refuses to start and says
what to run.

For the public server use serve.py, which serves the built web app as well.
"""

import sys

from app import create_app
from app.config import get_config
from app.services import preflight

app = create_app()

if __name__ == "__main__":
    cfg = get_config()
    results = preflight.check_database(cfg)
    blocking = [m for level, m in results if level == preflight.FAIL]
    for level, message in results:
        if level != preflight.OK:
            print(f"[{level}] {message}")
    if blocking:
        print("\nNot starting. Fix the above first.")
        sys.exit(1)
    app.run(host="127.0.0.1", port=5000, debug=False)
