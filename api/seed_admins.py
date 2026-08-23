"""
seed_admins.py

Run this ONCE after your database is set up, to create the first
admin accounts. After running, you'll have login credentials for
the admin panel.

How to run (from inside the running api container):
    docker compose exec api python seed_admins.py

This script is interactive — it will ask you for each admin's
username, password, and role, so no passwords are hard-coded here.
"""

import sys
sys.path.insert(0, "/app")  # so `from app...` imports work inside the container

from app.core.database import SessionLocal
from app.core.admin_auth import hash_password
from app.models.models import Admin


ROLE_DESCRIPTIONS = {
    "1": ("super_admin", "Full access — sees and can do everything"),
    "2": ("finance", "Approve/reject deposits and withdrawals"),
    "3": ("support", "View users, suspend/reactivate, view matches"),
}


def prompt_admin(default_username: str, default_role_key: str):
    print(f"\n--- Creating admin account ---")
    username = input(f"Username [{default_username}]: ").strip() or default_username
    password = input("Password: ").strip()
    while len(password) < 8:
        print("Password must be at least 8 characters.")
        password = input("Password: ").strip()

    print("Roles: 1) super_admin  2) finance  3) support")
    role_key = input(f"Role number [{default_role_key}]: ").strip() or default_role_key
    role, _ = ROLE_DESCRIPTIONS.get(role_key, ROLE_DESCRIPTIONS[default_role_key])

    return username, password, role


def main():
    db = SessionLocal()
    try:
        print("=" * 50)
        print("TicTacToe Bet — Admin Account Setup")
        print("=" * 50)
        print("You are setting up 3 accounts, as planned:")
        print("  1. You       -> suggested role: super_admin (bug fixing / full access)")
        print("  2. Yafet     -> suggested role: finance (deposits/withdrawals)")
        print("  3. Nahom     -> suggested role: support (users/moderation)")

        accounts = [
            ("your_username", "1"),
            ("yafet", "2"),
            ("nahom", "3"),
        ]

        for default_username, default_role_key in accounts:
            username, password, role = prompt_admin(default_username, default_role_key)

            existing = db.query(Admin).filter(Admin.username == username).first()
            if existing:
                print(f"⚠️  Username '{username}' already exists — skipping.")
                continue

            admin = Admin(
                username=username,
                password_hash=hash_password(password),
                role=role,
            )
            db.add(admin)
            db.commit()
            print(f"✅ Created '{username}' with role '{role}'.")

        print("\nDone! You can now log in at http://your-server:8000/admin-panel/")
    finally:
        db.close()


if __name__ == "__main__":
    main()
