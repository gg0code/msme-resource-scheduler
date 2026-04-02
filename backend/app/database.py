"""
FILE PURPOSE
This file establishes the database foundation for the entire ZetaOps Copilot application by creating the SQLAlchemy engine, session factory, and declarative base class that all ORM models inherit from. It exists as the central database configuration point that was introduced in the initial v4 architecture and serves as the bridge between our Python application code and the PostgreSQL database. This file sits at the core of our data access layer, providing the dependency injection mechanism that ensures proper database session management across all FastAPI routes.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy's create_engine and sessionmaker from the ORM library
2. Imports DeclarativeBase to create our custom base class for all models
3. Imports application settings from app.config to get the DATABASE_URL
4. Creates a single, shared SQLAlchemy engine instance using the configured database URL with echo disabled
5. Creates a SessionLocal factory using sessionmaker with explicit transaction control (autocommit=False, autoflush=False)
6. Defines a Base class inheriting from DeclarativeBase that all our ORM models will inherit from
7. Defines get_db() as a FastAPI dependency that yields database sessions with guaranteed cleanup

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : engine
Type         : SQLAlchemy Engine instance
Purpose      : The single database engine shared across the entire application lifecycle. This engine manages the connection pool to our PostgreSQL database and is configured to not echo SQL statements to reduce log noise in production.
Parameters   : Created with settings.DATABASE_URL (the PostgreSQL connection string) and echo=False
Returns      : Not applicable (module-level variable)
Calls        : create_engine() from SQLAlchemy core
DB/API       : Establishes connection pool to PostgreSQL database specified in DATABASE_URL
Side effects : Creates database connection pool that persists for the application's lifetime

Name         : SessionLocal
Type         : SQLAlchemy sessionmaker factory
Purpose      : Factory function that produces new database sessions for each request. Configured with autocommit=False and autoflush=False to give our service and router code explicit control over when transactions are committed and when pending changes are flushed to the database.
Parameters   : autocommit=False (we control commits manually), autoflush=False (we control flushes manually), bind=engine (uses our shared engine)
Returns      : When called, returns a new SQLAlchemy Session instance
Calls        : sessionmaker() from SQLAlchemy ORM
DB/API       : Each session it creates can execute queries against the PostgreSQL database
Side effects : Each session created tracks changes and can modify database state when committed

Name         : Base
Type         : SQLAlchemy DeclarativeBase class
Purpose      : The declarative base class that all our ORM models (Job, Employee, Machine, Tenant, User, etc.) inherit from. This inheritance gives Alembic full visibility into our schema definition so it can automatically generate database migrations when we add or modify model fields.
Parameters   : None (inherits from DeclarativeBase)
Returns      : Not applicable (base class for inheritance)
Calls        : DeclarativeBase constructor from SQLAlchemy
DB/API       : Provides the metadata registry that Alembic uses for migration generation
Side effects : Registers model metadata when models inherit from it, enabling schema introspection

Name         : get_db
Type         : FastAPI dependency function
Purpose      : The dependency injection function used in every FastAPI route that needs database access. It creates a new session from SessionLocal, yields it to the route handler, and guarantees that session.close() is called after the request completes, even if an exception occurs during request processing.
Parameters   : None (called automatically by FastAPI's dependency injection system)
Returns      : Yields a SQLAlchemy Session instance that routes can use for database queries
Calls        : SessionLocal() to create a new session, then session.close() in the finally block
DB/API       : The yielded session can execute any SQL queries against our PostgreSQL database
Side effects : Creates and properly closes database sessions, ensuring no connection leaks

WHO CALLS THIS FILE
- backend/app/main.py imports this to access the engine for application startup
- backend/app/models/*.py files import Base to define ORM model classes
- backend/app/routers/*.py files import get_db as a FastAPI dependency
- backend/app/crud/*.py files receive sessions created by get_db through dependency injection
- backend/app/services/*.py files receive sessions through route handlers that inject get_db
- backend/alembic/env.py imports Base.metadata for migration generation
- Any test files that need to create database sessions for testing

IMPORTS EXPLAINED
- create_engine: SQLAlchemy function that creates the database engine managing our connection pool to PostgreSQL
- sessionmaker: SQLAlchemy factory that creates session factories with our desired configuration (no autocommit/autoflush)
- DeclarativeBase: Modern SQLAlchemy 2.x base class that our custom Base inherits from to provide declarative model definition
- app.config.settings: Our application configuration module containing DATABASE_URL and other environment-specific settings

INTERN NOTES
- Easiest thing to break without realising: Changing autocommit=True or autoflush=True will break our explicit transaction control and cause data consistency issues across the application
- Non-obvious design decision and why: We use autocommit=False and autoflush=False because our business logic in services/ needs to control exactly when database changes are committed, especially for multi-step operations like scheduling
- Most common mistake when editing: Forgetting to call db.close() or session.close() in custom database code outside of the get_db() dependency, which causes connection pool exhaustion
- Which design principle this file implements: Principle #2 (tenant scoping) is enforced by providing the session mechanism that all CRUD functions use to filter by tenant_id
- What to check if this file behaves unexpectedly: Verify DATABASE_URL in settings is correct, check PostgreSQL is running and accessible, monitor connection pool size if getting connection timeout errors
- If v5-whatsapp only: Not applicable - this file exists in both v4-dev and v5-whatsapp branches with identical functionality
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
