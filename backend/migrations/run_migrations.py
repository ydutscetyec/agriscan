"""Apply numbered SQL migrations in order.

Migration style decision: PLAIN SQL, not Alembic.
Reason: the schema is hand-designed, uses MariaDB-specific features (ENUM, JSON columns,
triggers with SIGNAL) that Alembic autogenerate handles poorly, and the team needs to be
able to read exactly what runs. The cost is that downgrades are manual.

Statements are separated by a line containing only `-- @@`, or by `;` when no such marker
is present. The marker exists because trigger bodies contain semicolons.

Usage:
    python -m migrations.run_migrations            # apply pending
    python -m migrations.run_migrations --status   # list applied/pending
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pymysql

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import get_config  # noqa: E402

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename   VARCHAR(255) NOT NULL PRIMARY KEY,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _strip_comments(sql: str) -> str:
    """Drop whole-line SQL comments.

    Done BEFORE splitting: a comment may legitimately contain a semicolon, and
    splitting first would cut the comment in half and leave prose in a statement.
    """
    return "\n".join(
        ln for ln in sql.splitlines() if not ln.strip().startswith("--")
    )


def split_statements(sql: str) -> list[str]:
    """Split a migration file into executable statements.

    Files containing the `-- @@` marker are split on it, because trigger bodies
    contain semicolons that are not statement terminators. Other files split on `;`.
    """
    if "-- @@" in sql:
        parts = sql.split("-- @@")
    else:
        parts = _strip_comments(sql).split(";")

    out = []
    for part in parts:
        stmt = _strip_comments(part).strip().rstrip(";").strip()
        if stmt:
            out.append(stmt)
    return out


def connect(cfg, database: str | None = None):
    return pymysql.connect(
        host=cfg.DB_HOST,
        port=cfg.DB_PORT,
        user=cfg.DB_USER,
        password=cfg.DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def ensure_database(cfg) -> None:
    conn = connect(cfg, database=None)
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{cfg.DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
        )
    conn.close()


def applied_set(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(LEDGER_DDL)
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def migration_files() -> list[pathlib.Path]:
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true", help="show state and exit")
    args = parser.parse_args()

    cfg = get_config()
    ensure_database(cfg)
    conn = connect(cfg, database=cfg.DB_NAME)
    done = applied_set(conn)

    if args.status:
        for path in migration_files():
            print(f"{'APPLIED ' if path.name in done else 'PENDING '} {path.name}")
        conn.close()
        return 0

    pending = [p for p in migration_files() if p.name not in done]
    if not pending:
        print("No pending migrations.")
        conn.close()
        return 0

    for path in pending:
        print(f"Applying {path.name} ...")
        statements = split_statements(path.read_text(encoding="utf-8"))
        with conn.cursor() as cur:
            for stmt in statements:
                try:
                    cur.execute(stmt)
                except Exception as exc:  # noqa: BLE001
                    print(f"  FAILED on statement:\n{stmt[:400]}\n  {exc}")
                    conn.close()
                    return 1
            cur.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
            )
        print(f"  ok ({len(statements)} statements)")

    conn.close()
    print("Migrations complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
