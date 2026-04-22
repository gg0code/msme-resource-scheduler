"""
One-time backfill script for BUG-5.

Sets industry_type = "printing" on every tenant row where the column
is currently NULL. This affects tenants registered before BUG-4 fix
(commit 77fb429 on 2026-04-22) when industry_type was silently dropped
by the Pydantic schema.

"printing" is the documented default industry per SRS §1.2.

Idempotent: running a second time is a no-op. Safe.

Run against dev:
    cd backend
    python scripts/backfill_industry_type.py

Run against prod: same command, executed on the server after the v6.2.9
deploy is verified.
"""
from app.database import SessionLocal
from app.models.auth import Tenant


def backfill() -> int:
    db = SessionLocal()
    try:
        affected = (
            db.query(Tenant)
              .filter(Tenant.industry_type.is_(None))
              .update(
                  {Tenant.industry_type: "printing"},
                  synchronize_session=False,
              )
        )
        db.commit()
        return affected
    finally:
        db.close()


if __name__ == "__main__":
    count = backfill()
    if count == 0:
        print("No legacy tenants with NULL industry_type. Nothing to do.")
    else:
        print(f"Backfilled {count} tenant(s) with industry_type='printing'.")
