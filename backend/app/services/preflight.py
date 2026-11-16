"""Deployment checks. Each returns (level, message): 'fail' stops a production start,
'warn' is printed, 'ok' is confirmation.

Run on their own with `python -m scripts.preflight`, and automatically by serve.py.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.config import BACKEND_DIR, Config

OK, WARN, FAIL = "ok", "warn", "fail"

# The password scripts/seed.py --with-demo gives every demo account. It is printed on
# screen and written in the source, so on a public server it is a published password.
DEMO_PASSWORD = "demo-password-change-me"


def _engine(cfg: Config):
    return create_engine(cfg.sqlalchemy_uri, pool_pre_ping=True, future=True)


def check_config(cfg: Config) -> list[tuple[str, str]]:
    out = []
    if cfg.is_production:
        problems = cfg.production_problems()
        out += [(FAIL, p) for p in problems]
        if not problems:
            out.append((OK, "Production configuration: secret key and database password set."))
        if cfg.PROXY_HOPS == 0:
            out.append((WARN, "AGRISCAN_PROXY_HOPS is 0. Behind Caddy or Cloudflare Tunnel set it "
                              "to 1, or every client looks like 127.0.0.1 to the sign-in limit."))
    else:
        out.append((WARN, f"AGRISCAN_ENV is '{cfg.ENV}'. Set AGRISCAN_ENV=production on the "
                          "public server to turn on the production checks."))
    if cfg.DETECTOR_IMPL == "stub":
        if cfg.is_production:
            out.append((WARN, "Detector is the stub, so the worker will refuse to run. Uploads "
                              "work and photos stay queued until a trained model is registered "
                              "and AGRISCAN_DETECTOR_IMPL=yolo."))
        else:
            out.append((WARN, "Detector is the stub: every analysed photo gets the same "
                              "synthetic result. Fine for development, never for farmers."))
    return out


def check_paths(cfg: Config) -> list[tuple[str, str]]:
    out = []
    root = cfg.image_root_path
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        out.append((OK, f"Image store writable: {root}"))
    except OSError as exc:
        out.append((FAIL, f"Image store not writable at {root}: {exc}"))

    index = cfg.web_dist_path / "index.html"
    if index.is_file():
        out.append((OK, f"Web build found: {cfg.web_dist_path}"))
    else:
        out.append((FAIL, f"No web build at {cfg.web_dist_path}. Run: cd web && npm ci && npm run build"))
    return out


def check_database(cfg: Config) -> list[tuple[str, str]]:
    out = []
    try:
        engine = _engine(cfg)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            out.append((OK, f"Database reachable: {cfg.DB_NAME} on {cfg.DB_HOST}:{cfg.DB_PORT}"))

            applied = {r[0] for r in conn.execute(text("SELECT filename FROM schema_migrations"))}
            files = sorted(p.name for p in (BACKEND_DIR / "migrations").glob("*.sql"))
            pending = [f for f in files if f not in applied]
            if pending:
                out.append((FAIL, "Migrations not applied: " + ", ".join(pending)
                                  + ". Run: python -m migrations.run_migrations"))
            else:
                out.append((OK, f"Schema up to date ({len(files)} migrations)."))

            admins = conn.execute(text(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND active AND NOT is_demo"
            )).scalar_one()
            if admins:
                out.append((OK, f"{admins} real administrator account(s)."))
            else:
                out.append((FAIL if cfg.is_production else WARN,
                            "No real (non-demo) administrator. Run: python -m scripts.create_admin"))

            out += _check_demo_accounts(conn, cfg)

            conditions = conn.execute(text("SELECT COUNT(*) FROM conditions")).scalar_one()
            if not conditions:
                out.append((WARN, "Condition taxonomy is empty. Run: python -m scripts.seed"))

            models = conn.execute(text(
                "SELECT imaging_mode, name FROM model_versions WHERE deployment_status='production'"
            )).fetchall()
            if models:
                for mode, name in models:
                    out.append((OK, f"Production {mode} model: {name}"))
            else:
                out.append((WARN, "No model in production. The worker will not start; photos "
                                  "queue until one is registered (python -m scripts.register_model)."))
    except Exception as exc:  # noqa: BLE001
        msg = str(getattr(exc, "orig", exc))
        out.append((FAIL, f"Database not reachable ({msg}). Is MySQL running in XAMPP, and "
                          "are the AGRISCAN_DB_* values in backend/.env right?"))
    return out


def _check_demo_accounts(conn, cfg: Config) -> list[tuple[str, str]]:
    from app.auth.security import verify_password

    rows = conn.execute(text(
        "SELECT name, password_hash FROM users WHERE is_demo AND active"
    )).fetchall()
    if not rows:
        return [(OK, "No active demo accounts.")]
    published = [name for name, pw_hash in rows if verify_password(pw_hash, DEMO_PASSWORD)]
    if published:
        level = FAIL if cfg.is_production else WARN
        return [(level, "Demo accounts still use the published demo password: "
                        + ", ".join(published)
                        + ". Deactivate them on the Users page before going public.")]
    return [(WARN, f"{len(rows)} demo account(s) are active. Their data is excluded from "
                   "metrics, but they can still sign in.")]


def run_all(cfg: Config) -> list[tuple[str, str]]:
    return check_config(cfg) + check_paths(cfg) + check_database(cfg)


def print_report(results: list[tuple[str, str]]) -> bool:
    """Print and return True if nothing failed."""
    marks = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}
    for level, message in results:
        print(f"[{marks[level]}] {message}")
    failed = [m for lvl, m in results if lvl == FAIL]
    print()
    print("Preflight: " + ("passed." if not failed else f"{len(failed)} problem(s) must be fixed."))
    return not failed
