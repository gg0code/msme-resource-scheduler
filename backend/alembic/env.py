"""
alembic/env.py
--------------
Alembic migration environment configuration for the MSME Resource Scheduler.
Imports all ORM models so Alembic can diff the full schema and auto-generate
migration scripts. Supports both offline (SQL script) and online (live DB) modes.
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys, os

# Ensure the backend root is on the path so `from app.xxx import` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import Base
from app.models import *   # noqa — import all models so Alembic sees their tables

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata used by --autogenerate to detect schema changes
target_metadata = Base.metadata


def run_migrations_offline():
    """
    Generate SQL migration scripts without a live DB connection.
    Output is written to stdout or a file, useful for review before applying.

    Input  : sqlalchemy.url from alembic.ini.
    Output : SQL DDL statements for the migration.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """
    Apply migrations directly to a live database connection.
    Used when running `alembic upgrade head` during local setup or CI/CD.

    Input  : sqlalchemy.url from alembic.ini (must point to a running PostgreSQL instance).
    Output : DDL statements executed against the connected database.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
