"""Create the first real administrator, or reset an administrator's password.

    python -m scripts.create_admin                 # asks for the name and password
    python -m scripts.create_admin --name "Rol"    # asks only for the password

The password is typed, never passed on the command line, so it does not end up in the
shell history. A server without a real admin cannot be managed from the Users page, and
the demo admin's password is published in scripts/seed.py.
"""

from __future__ import annotations

import argparse
import getpass
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth.security import PasswordPolicyError, hash_password, utc_now  # noqa: E402
from app.config import get_config  # noqa: E402
from app.extensions import SessionLocal, init_engine  # noqa: E402
from app.models import User  # noqa: E402
from app.services import audit  # noqa: E402


def ask_password(min_length: int) -> str:
    while True:
        first = getpass.getpass(f"Password (at least {min_length} characters): ")
        if len(first) < min_length:
            print(f"  Too short. At least {min_length} characters.")
            continue
        if getpass.getpass("Type it again: ") != first:
            print("  The two did not match.")
            continue
        return first


def upsert_admin(session, name: str, password: str, min_length: int,
                 barangay: str | None = None) -> tuple[User, bool]:
    """Create the admin, or reset and reactivate it. Returns (user, created)."""
    pw_hash = hash_password(password, min_length)
    user = session.execute(select(User).where(User.name == name)).scalar_one_or_none()
    created = user is None
    if created:
        user = User(name=name, role="admin", barangay=barangay, password_hash=pw_hash,
                    is_demo=False)
        session.add(user)
    else:
        if user.role != "admin":
            raise SystemExit(
                f"'{name}' exists with role '{user.role}'. Change it on the Users page, "
                "or choose another name."
            )
        user.password_hash = pw_hash
        user.password_changed_at = utc_now()
        user.active = True
    session.commit()
    return user, created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name")
    parser.add_argument("--barangay")
    args = parser.parse_args()

    cfg = get_config()
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()

    name = (args.name or input("Administrator name (used to sign in): ")).strip()
    if not name:
        print("A name is required.")
        return 1
    try:
        user, created = upsert_admin(session, name, ask_password(cfg.PASSWORD_MIN_LENGTH),
                                     cfg.PASSWORD_MIN_LENGTH, args.barangay)
    except PasswordPolicyError as exc:
        print(exc)
        return 1
    audit.record(None, "create_admin_cli" if created else "reset_admin_cli", "user", user.id)
    print(("Created" if created else "Reset password for") + f" administrator '{user.name}'.")
    SessionLocal.remove()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
