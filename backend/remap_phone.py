import sys
from app.database import SessionLocal
from sqlalchemy import text

PHONE = '+919845539868'

db = SessionLocal()

print(f'=== Current mapping for {PHONE} ===')
row = db.execute(text(
    "SELECT phone_number, tenant_id, industry_type, consent_given, is_active "
    f"FROM phone_tenant_map WHERE phone_number='{PHONE}'"
)).first()
print(row)

if len(sys.argv) > 1:
    target = int(sys.argv[1])

    # Bug 2 fix: PhoneTenantMap.industry_type is a denormalized snapshot of the
    # tenant's industry at link time (BUG-6 design in whatsapp_identity.py).
    # Re-pointing tenant_id alone leaves the snapshot stale, so the AI loads
    # the wrong RAG vertical until this row is re-synced. Always refresh both.
    target_industry_row = db.execute(text(
        f"SELECT industry_type FROM tenants WHERE id={target}"
    )).first()
    if target_industry_row is None:
        print(f'ERROR: tenant_id={target} not found in tenants table.')
        db.close()
        sys.exit(1)
    target_industry = target_industry_row[0]

    print()
    print(f'Updating tenant_id to {target}, industry_type to {target_industry!r}...')
    db.execute(text(
        f"UPDATE phone_tenant_map "
        f"SET tenant_id={target}, industry_type='{target_industry}' "
        f"WHERE phone_number='{PHONE}'"
    ))
    db.commit()

    print()
    print('=== After update ===')
    row = db.execute(text(
        "SELECT phone_number, tenant_id, industry_type, consent_given, is_active "
        f"FROM phone_tenant_map WHERE phone_number='{PHONE}'"
    )).first()
    print(row)
else:
    print()
    print('No tenant_id argument - read-only.')
    print('To remap to tenant 12:  python remap_phone.py 12')
    print('To revert to tenant 11: python remap_phone.py 11')

db.close()
