from app.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    conn.execute(text("DELETE FROM alembic_version WHERE version_num = '014'"))
    conn.commit()
    print('Removed stale 014 entry')
