"""
One-time backfill script for BUG-6.

Fixes PhoneTenantMap rows where industry_type does not match the
tenant's current industry_type. This affects every row created before
BUG-6 fix, because link_phone() always stored "printing" regardless
of tenant industry.

Idempotent: running a second time is a no-op. Safe.

Run against dev:
    cd backend
    python -m scripts.backfill_phone_industry_type

Run against prod: same command, after the v6.3.0 deploy is verified.
"""
from app.database import SessionLocal
from app.models.auth import Tenant
from app.models.whatsapp import PhoneTenantMap


def backfill() -> dict:
    db = SessionLocal()
    try:
        fixed = 0
        skipped = 0
        for row in db.query(PhoneTenantMap).all():
            tenant = db.query(Tenant).filter(Tenant.id == row.tenant_id).first()
            if tenant is None:
                skipped += 1
                continue
            expected = tenant.industry_type or "printing"
            if row.industry_type != expected:
                row.industry_type = expected
                fixed += 1
        db.commit()
        return {"fixed": fixed, "skipped": skipped, "total": fixed + skipped}
    finally:
        db.close()


if __name__ == "__main__":
    result = backfill()
    if result["fixed"] == 0:
        print(
            f"No PhoneTenantMap rows needed updating. "
            f"(Checked {result['total']}, skipped {result['skipped']} orphaned.)"
        )
    else:
        print(
            f"Backfilled {result['fixed']} PhoneTenantMap row(s) to match "
            f"tenant.industry_type. (Skipped {result['skipped']} orphaned.)"
        )
