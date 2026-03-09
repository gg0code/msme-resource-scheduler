"""
scripts/seed_generic_roles.py
Idempotent script — inserts generic roles for a given tenant if they don't exist.

Usage:
    cd backend
    python scripts/seed_generic_roles.py --tenant-id 1
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.skill import Skill

GENERIC_ROLES = [
    "Helper",
    "Loader",
    "Unloader",
    "Cleaner",
    "Supervisor",
    "Quality Inspector",
    "Line Operator",
    "Packer",
    "Material Handler",
    "Forklift Operator",
    "Driver",
    "Despatch Clerk",
    "Safety Officer",
    "Shift Incharge",
]


def seed(tenant_id: int):
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for name in GENERIC_ROLES:
            exists = db.query(Skill).filter(
                Skill.tenant_id == tenant_id,
                Skill.name == name,
            ).first()
            if exists:
                skipped += 1
                continue
            db.add(Skill(
                tenant_id=tenant_id,
                name=name,
                category="generic",
                is_premium=False,
                is_generic_role=True,
                is_active=True,
            ))
            inserted += 1
        db.commit()
        print(f"Done — inserted: {inserted}, skipped (already exist): {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed generic roles for a tenant")
    parser.add_argument("--tenant-id", type=int, required=True, help="Tenant ID to seed roles for")
    args = parser.parse_args()
    seed(args.tenant_id)
