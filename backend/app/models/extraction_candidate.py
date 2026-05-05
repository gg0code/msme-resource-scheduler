# app/models/extraction_candidate.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# SQLAlchemy ORM mapping for the extraction_candidates staging table
# (migration 029, v6.3.13). v6.3.14 introduces this model and the
# entity-extractor service that writes rows into it from inbound
# WhatsApp messages. The table is a running tally of entity mentions:
# one row per (tenant_id, entity_type, normalized_value), with
# mention_count incremented on each re-mention via INSERT ... ON
# CONFLICT DO UPDATE.
#
# WHO CALLS THIS FILE
# - app/services/extraction/entity_extractor.py — writes rows via the
#   upsert helper. Imports the class so app/main.py picks the table
#   up in Base.metadata (the model registers itself on import).
# - backend/inspect_extractions.py — reads recent rows for a tenant.
# - backend/tests/services/test_entity_extractor.py — asserts on rows
#   the extractor inserted.
# - tests/conftest.py — imports app.main, which imports the
#   extractor service, which imports this module. That chain is what
#   gets the SQLite test DB to create the table.
#
# WHAT THIS FILE CALLS
# - app.database.Base — declarative base for ORM models.
# - sqlalchemy core types: Column, DateTime, Float, ForeignKey,
#   Integer, String, Text, text, UniqueConstraint, Index.
#
# DESIGN NOTES
# - Schema mirrors migration 029 exactly. If the migration ever
#   changes, update this file in the same commit. There is no shared
#   source of truth — alembic is the authority for Postgres DDL,
#   this class is the authority for the application's view of the
#   row shape.
# - entity_type is a free-form VARCHAR(50). The vocabulary
#   (employee, machine, customer, skill, material, job, issue) is
#   enforced at the application layer via the ENTITY_TYPES constant
#   in entity_extractor.py — not via a CHECK constraint, so future
#   versions can add types without a migration.
# - confidence is a Float [0.0, 1.0] LLM-reported. v6.3.15 promotion
#   threshold will be >= 0.7. No CHECK constraint — out-of-range
#   values are clamped at insert time.
# - The unique constraint on (tenant_id, entity_type, normalized_value)
#   backs the INSERT ... ON CONFLICT DO UPDATE upsert in v6.3.14.
# - server_default=text("now()") on created_at / updated_at is
#   Postgres-only. SQLite tests use the patch_now_defaults_for_sqlite
#   autouse fixture in tests/services/conftest.py to swap to
#   CURRENT_TIMESTAMP — this model's table is added to that fixture's
#   target list in v6.3.14.
#
# FORWARD-COMPAT
# - v6.3.15 — promotion job reads (tenant_id, mention_count, confidence)
#   to materialise candidates into employees/machines/customers/skills.
# - v6.3.16 — surface "we noticed X — should I add this?" prompts to
#   the user; reads same rows.

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ExtractionCandidate(Base):
    __tablename__ = "extraction_candidates"

    id = Column(Integer, primary_key=True, nullable=False)

    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    entity_type      = Column(String(50), nullable=False)
    raw_value        = Column(Text(),     nullable=False)
    normalized_value = Column(Text(),     nullable=False)
    confidence       = Column(Float(),    nullable=False)

    mention_count = Column(
        Integer,
        nullable=False,
        server_default="1",
    )

    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen  = Column(DateTime(timezone=True), nullable=False)

    source_type = Column(
        String(20),
        nullable=False,
        server_default="whatsapp",
    )
    source_message_id = Column(String(120), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    tenant = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "entity_type",
            "normalized_value",
            name="uq_extraction_candidates_tenant_type_value",
        ),
        Index(
            "idx_extraction_candidates_tenant_entity_type",
            "tenant_id",
            "entity_type",
        ),
        Index(
            "idx_extraction_candidates_tenant_normalized",
            "tenant_id",
            "normalized_value",
        ),
        Index(
            "idx_extraction_candidates_tenant_mentions",
            "tenant_id",
            "mention_count",
        ),
    )
