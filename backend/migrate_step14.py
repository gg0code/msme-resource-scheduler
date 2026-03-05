"""
migrate_step14.py — adds order_value and misc_cost to jobs table.
Run from backend/:  python migrate_step14.py
"""
import os, sys, re

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

env = {}
for candidate in [".env", "../.env"]:
    env = load_env(candidate)
    if env.get("DATABASE_URL"): break

DATABASE_URL = env.get("DATABASE_URL") or os.environ.get("DATABASE_URL") or \
    "postgresql://msme_user:msme_pass@localhost:5432/msme_scheduler"

try:
    import psycopg2
except ImportError:
    os.system(f"{sys.executable} -m pip install psycopg2-binary")
    import psycopg2

m = re.match(r"postgresql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)", DATABASE_URL)
user, password, host, port, dbname = m.groups()
conn = psycopg2.connect(host=host, port=int(port or 5432), user=user, password=password, dbname=dbname)
conn.autocommit = True
cur = conn.cursor()

def col_exists(table, col):
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s", (table, col))
    return cur.fetchone() is not None

def add_col(table, col, defn):
    if col_exists(table, col):
        print(f"  = {table}.{col} (already exists)")
    else:
        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {defn}')
        print(f"  + {table}.{col}")

print("\nMigrating jobs...")
add_col("jobs", "order_value", "FLOAT")
add_col("jobs", "misc_cost",   "FLOAT")

cur.close()
conn.close()
print("\nDone!")
