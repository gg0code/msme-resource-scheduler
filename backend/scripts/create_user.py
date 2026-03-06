"""
scripts/create_user.py
----------------------
Create a new user under an existing tenant.

Usage:
    python scripts/create_user.py --email user@company.com --password 12345678 --role scheduler
    python scripts/create_user.py --email viewer@company.com --password abcdefgh --role viewer

Roles: proprietor | scheduler | viewer
"""

import argparse
import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.auth import User, Tenant
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_ROLES = ["proprietor", "scheduler", "viewer"]

def create_user(email: str, password: str, role: str, tenant_id: int = None):
    db = SessionLocal()
    try:
        # Check role
        if role not in VALID_ROLES:
            print(f"❌ Invalid role '{role}'. Must be one of: {', '.join(VALID_ROLES)}")
            return

        # Check if user already exists
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"❌ User with email '{email}' already exists.")
            return

        # Get tenant
        if tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        else:
            tenant = db.query(Tenant).first()

        if not tenant:
            print("❌ No tenant found in database. Run seed script first.")
            return

        # Create user
        hashed = pwd_context.hash(password)
        user = User(
            email=email,
            hashed_password=hashed,
            role=role,
            tenant_id=tenant.id,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        print(f"✅ User created successfully!")
        print(f"   Email     : {email}")
        print(f"   Password  : {password}")
        print(f"   Role      : {role}")
        print(f"   Tenant    : {tenant.name} (id={tenant.id})")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()


def list_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("No users found.")
            return
        print(f"\n{'ID':<5} {'Email':<35} {'Role':<15} {'Tenant ID':<10} {'Active'}")
        print("-" * 75)
        for u in users:
            print(f"{u.id:<5} {u.email:<35} {u.role:<15} {u.tenant_id:<10} {u.is_active}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or list MSME users")
    parser.add_argument("--email",    help="User email address")
    parser.add_argument("--password", help="User password (min 6 chars)")
    parser.add_argument("--role",     help="Role: proprietor | scheduler | viewer")
    parser.add_argument("--tenant",   type=int, help="Tenant ID (optional, defaults to first tenant)")
    parser.add_argument("--list",     action="store_true", help="List all existing users")

    args = parser.parse_args()

    if args.list:
        list_users()
    elif args.email and args.password and args.role:
        create_user(args.email, args.password, args.role, args.tenant)
    else:
        print("Usage examples:")
        print("  python scripts/create_user.py --email owner@co.com --password 12345678 --role proprietor")
        print("  python scripts/create_user.py --email sched@co.com --password abcdefgh --role scheduler")
        print("  python scripts/create_user.py --email view@co.com  --password 12345678 --role viewer")
        print("  python scripts/create_user.py --list")
