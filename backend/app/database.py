"""
database.py
-----------
Creates the SQLAlchemy engine and session factory that power all DB access in the app.
Defines the shared `Base` class that every ORM model inherits from.
Also exposes `get_db()`, a FastAPI dependency used in every router to obtain a session.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

# Single engine instance shared across the whole application lifecycle.
engine = create_engine(settings.DATABASE_URL, echo=False)

# Factory that produces new sessions; autocommit/autoflush off so
# we control transactions explicitly in service and router code.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    Declarative base class inherited by all SQLAlchemy ORM models.
    Gives Alembic visibility of the full schema for migration generation.
    """
    pass


def get_db():
    """
    FastAPI dependency injected into every route that needs database access.

    Input  : None — called automatically by FastAPI's dependency injection.
    Output : Yields an active SQLAlchemy Session; guarantees session.close()
             is called after the request finishes, even if an exception occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
