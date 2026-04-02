"""
```python
"""
FILE PURPOSE
This is a standalone database seeding script that creates generic workforce roles for manufacturing
tenants in the ZetaOps Copilot system. It was introduced in v4-dev as part of the skills/roles
system and sits outside the main application architecture as a utility script. The script ensures
that new tenants get a standard set of 14 common manufacturing roles (like Helper, Supervisor,
Quality Inspector) without duplicating existing roles, making it safe to run multiple times.

WHAT THIS FILE DOES — step by step
1. Sets up command line argument parsing to accept a required --tenant-id parameter
2. Adds the parent directory to Python path so it can import app modules from backend/
3. Defines a hardcoded list of 14 generic manufacturing role names (GENERIC_ROLES constant)
4. Opens a database session using the main application's SessionLocal factory
5. For each role name, queries the Skill table to check if it already exists for the given tenant
6. If the role doesn't exist, creates a new Skill record with generic role properties
7. If the role exists, skips it and increments the skip counter
8. Commits all new Skill records to the database in a single transaction
9. Prints a summary of how many roles were inserted vs skipped
10. Properly closes the database session in a try/finally block

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : seed
Type         : function
Purpose      : Core seeding logic that inserts generic roles for a specific tenant. Performs
               idempotent insertion by checking for existing roles first, then creates Skill
               records with standardized generic role properties. Safe to run multiple times.
Parameters   : tenant_id (int) - The database ID of the tenant to seed roles for
Returns      : None (void function, only prints status and modifies database)
Calls        : SessionLocal() from app.database, db.query() and db.add() methods
DB/API       : Queries Skill table filtered by tenant_id and name, inserts new Skill records
Side effects : Creates Skill records in database, prints insertion summary to stdout

Name         : GENERIC_ROLES
Type         : module constant
Purpose      : Hardcoded list of 14 standard manufacturing role names that every tenant should
               have available. Covers common positions from entry-level (Helper, Cleaner) to
               management (Supervisor, Shift Incharge) to specialized roles (Forklift Operator).
Parameters   : N/A (constant list)
Returns      : N/A (constant list)
Calls        : None
DB/API       : None
Side effects : None

WHO CALLS THIS FILE
This is a standalone script executed directly from command line. No other files import or call it.
Typical usage: `cd backend && python scripts/seed_generic_roles.py --tenant-id 1`

IMPORTS EXPLAINED
- argparse: Python standard library for parsing command line arguments (--tenant-id parameter)
- sys: Python standard library for system-specific parameters and functions, used for path manipulation
- os: Python standard library for operating system interface, used to build file paths
- sys.path.insert: Modifies Python module search path to allow importing from parent directory
- SessionLocal from app.database: Database session factory from main application
- Skill from app.models.skill: SQLAlchemy ORM model representing workforce skills/roles

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id filter in the existence check query - this would cause cross-tenant role conflicts and violate design principle #2
- Non-obvious design: Uses Skill model with is_generic_role=True rather than a separate Role table because skills and roles are unified in this system's data model
- Most common mistake: Running without proper database connection or wrong tenant ID, or modifying GENERIC_ROLES list without considering existing tenant data
- Design principle: Implements principle #2 (tenant scoping) by filtering all queries with tenant_id to ensure data isolation
- Check if unexpected behavior: Verify database connection, check if tenant_id exists in Tenant table, ensure Skill table has proper indexes on tenant_id
- v4-dev specific: This is production-stable code, any changes should be thoroughly tested before merging to master branch
"""
```
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
