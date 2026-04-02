"""
```python
"""
FILE PURPOSE
This is a command-line utility script for creating new users in the ZetaOps Copilot system.
It exists to allow system administrators to manually add users to existing tenants without
going through the web interface. This script was part of the original v4.0 architecture
and sits in the backend/scripts/ folder as a database administration tool.

WHAT THIS FILE DOES — step by step
1. Sets up command-line argument parsing for email, password, role, tenant ID, and list options
2. Adds the backend app directory to Python's module search path for imports
3. Imports database models, session management, and password hashing utilities
4. Defines valid user roles as a constant list
5. Provides create_user() function that validates inputs and creates a new user record
6. Provides list_users() function that displays all existing users in a formatted table
7. Executes the appropriate function based on command-line arguments provided
8. Handles database transactions with proper rollback on errors

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : create_user
Type         : function
Purpose      : Creates a new user record in the database under an existing tenant. Validates
               the role, checks for email duplicates, hashes the password using bcrypt, and
               associates the user with either a specified tenant or the first available tenant.
Parameters   : email (str) - user's login email address
               password (str) - plaintext password to be hashed and stored
               role (str) - must be one of "proprietor", "scheduler", or "viewer"
               tenant_id (int, optional) - specific tenant ID, defaults to first tenant if None
Returns      : None (prints success/error messages to console)
Calls        : SQLAlchemy query methods, passlib password hashing, database session methods
DB/API       : Queries User table to check for duplicates, queries Tenant table to find target
               tenant, inserts new User record with hashed password and tenant association
Side effects : Creates new database record, prints status messages, commits or rolls back transaction

Name         : list_users
Type         : function  
Purpose      : Displays all users in the database in a formatted table showing ID, email, role,
               tenant ID, and active status. Used for administrative overview of system users.
Parameters   : None
Returns      : None (prints user table to console)
Calls        : SQLAlchemy query methods to fetch all User records
DB/API       : Queries all records from User table
Side effects : Prints formatted user information to console

WHO CALLS THIS FILE
This script is executed directly from the command line by system administrators. It is not
imported or called by any other Python files in the codebase. It's run manually using
commands like "python scripts/create_user.py --email user@company.com --password 12345678 --role scheduler"

IMPORTS EXPLAINED
- argparse: Python's built-in command-line argument parsing library for handling --email, --password, etc.
- sys: Provides access to Python interpreter variables, used here to modify the module search path
- os: Operating system interface functions, used for path manipulation to find the backend directory
- app.database.SessionLocal: Database session factory from our SQLAlchemy setup for creating DB connections
- app.models.auth.User: SQLAlchemy ORM model representing user records in the database
- app.models.auth.Tenant: SQLAlchemy ORM model representing tenant records that users belong to  
- passlib.context.CryptContext: Password hashing library using bcrypt for secure password storage

INTERN NOTES
- Easiest thing to break: Forgetting to run this from the backend/ directory will cause import errors due to the path manipulation
- Non-obvious design decision: Uses the first available tenant as default because early deployments often had single tenants
- Most common mistake: Not checking if a tenant exists before creating users, which will cause foreign key constraint errors
- Design principle #2: This script properly implements tenant scoping by requiring every user to have a tenant_id
- What to check if behaving unexpectedly: Verify database connection settings and ensure at least one tenant exists in the system
- This is v4-dev stable code that doesn't interact with WhatsApp features, so merging to v5-whatsapp should be straightforward
"""
```
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
