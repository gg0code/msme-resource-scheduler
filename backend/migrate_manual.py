"""
migrate_manual.py
-----------------
PostgreSQL migration — adds new columns to employees, machines, jobs tables.
Run from the backend/ directory:  python migrate_manual.py
Safe to run multiple times — skips columns that already exist.
"""

import os, sys

# ── Load DATABASE_URL from .env ───────────────────────
def load_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

# Try to find .env in backend/ or project root
env = {}
for candidate in [".env", "../.env", "app/.env"]:
    env = load_env(candidate)
    if env.get("DATABASE_URL"):
        break

DATABASE_URL = (
    env.get("DATABASE_URL") or
    os.environ.get("DATABASE_URL") or
    "postgresql://msme_user:msme_pass@localhost:5432/msme_scheduler"
)

print(f"Connecting to: {DATABASE_URL}")

# ── Connect via psycopg2 ──────────────────────────────
try:
    import psycopg2
except ImportError:
    print("Installing psycopg2...")
    os.system(f"{sys.executable} -m pip install psycopg2-binary")
    import psycopg2

# Parse URL  postgresql://user:pass@host:port/dbname
import re
m = re.match(r"postgresql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)", DATABASE_URL)
if not m:
    print("ERROR: Could not parse DATABASE_URL")
    sys.exit(1)

user, password, host, port, dbname = m.groups()
port = int(port or 5432)

conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
conn.autocommit = True
cur = conn.cursor()

def column_exists(table, column):
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
    """, (table, column))
    return cur.fetchone() is not None

def add_col(table, col, definition):
    if column_exists(table, col):
        print(f"  = {table}.{col} (already exists, skipping)")
    else:
        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {definition}')
        print(f"  + {table}.{col}")

print("\nMigrating employees...")
add_col("employees", "hourly_rate",   "FLOAT")
add_col("employees", "overtime_rate", "FLOAT")

print("\nMigrating machines...")
add_col("machines", "hourly_rate", "FLOAT")

print("\nMigrating jobs...")
add_col("jobs", "raw_materials",   "JSONB")
add_col("jobs", "timer_status",    "VARCHAR(20) NOT NULL DEFAULT 'idle'")
add_col("jobs", "actual_start_at", "TIMESTAMP")
add_col("jobs", "actual_end_at",   "TIMESTAMP")
add_col("jobs", "paused_seconds",  "INTEGER NOT NULL DEFAULT 0")
add_col("jobs", "timer_log",       "JSONB")

cur.close()
conn.close()
print("\nDone! All columns migrated successfully.")
