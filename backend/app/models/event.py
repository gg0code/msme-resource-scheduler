# app/models/event.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Generic audit-event row. Introduced in v6.3.3 to log role changes from
# the team-management endpoints; v6.3.4 will reuse the same table to log
# briefing dispatches, and later iterations will fan out further.
# Layer: model
#
# WHAT THIS FILE DOES
# Defines a single Event ORM mapping to table 'events'.
#   - tenant_id    : multi-tenancy boundary, CASCADE on tenant delete.
#   - event_type   : dotted string ('user.role_changed', 'briefing.sent').
#   - entity_type  : the kind of object the event is about ('user', 'job').
#   - entity_id    : optional pointer to the affected row (no FK — entities
#                    span tables, and we want the event to outlive the row).
#   - actor_user_id: who triggered it. SET NULL on user delete so audit
#                    history survives a user purge (audit is the point).
#   - source       : 'web' | 'whatsapp' | 'system'.
#   - payload      : free-form JSONB for event-specific details.
#                    Patched to JSON for SQLite by tests/conftest.py.
#   - created_at   : DDL default now(); patched in tests via the autouse
#                    patch_now_defaults_for_sqlite fixture from
#                    tests/test_signup_v6_4.py.
#
# WHO CALLS THIS FILE
# - app/routers/team_management.py  - inserts user.role_changed rows.
# - tests/test_team_management.py   - asserts audit rows.
# - app/main.py                     - imports it indirectly via team_management
#                                     so Base.metadata picks the table up.
# - tests/conftest.py               - imports it so SQLite test DB sees it.
# Future callers (v6.3.4+) will write briefing.* and other event types.
#
# WHAT THIS FILE CALLS
# - app.database.Base                  - declarative base for ORM models.
# - sqlalchemy.dialects.postgresql.JSONB - payload column type. Patched to
#                                          JSON for SQLite by conftest.
# - sqlalchemy core types: Column, DateTime, ForeignKey, Integer, String, text.
#
# DESIGN NOTES
# - No FK on entity_id. Events reference many entity types ('user', 'job',
#   'machine', 'briefing'); a polymorphic FK is more brittle than a plain
#   integer plus the entity_type discriminator. Lookup callers join on
#   (entity_type, entity_id).
# - source uses String(20) not an enum so v6.3.4+ can add new sources
#   ('cron', 'erp_sync') without a migration. Validation lives at the
#   service layer if needed; the column is permissive on purpose.
# - No updated_at column. Events are append-only; never edit a logged row.
#   If a fact changes, write a new event referencing the prior one in payload.

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)

    # Tenant scope. Indexed because every list-events query starts here.
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Dotted event type ('user.role_changed', 'briefing.sent'). String(50)
    # is generous; current vocabulary is short. Indexed because filtering
    # by event_type is the second-most-common query after tenant scope.
    event_type = Column(String(50), nullable=False, index=True)

    # What the event is about. 'user' / 'job' / 'machine' / 'briefing'.
    entity_type = Column(String(50), nullable=False)

    # Pointer to the affected row of entity_type. Not a FK — see header.
    # Nullable because some event types (e.g. 'tenant.created') describe
    # the tenant itself rather than a child row.
    entity_id = Column(Integer, nullable=True)

    # Who triggered the event. SET NULL on user delete so audit history
    # outlives the user. Nullable because system-generated events
    # ('system' source) have no actor.
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Channel that produced the event. 'web' | 'whatsapp' | 'system'.
    # Validation lives at the service layer; the column is open by design.
    source = Column(String(20), nullable=False)

    # Free-form event payload. JSONB on Postgres, patched to JSON on
    # SQLite by tests/conftest.py:_patch_pg_types_to_json. Nullable
    # because some event types are fully described by their type alone.
    payload = Column(JSONB, nullable=True)

    # Insertion timestamp. server_default=text("now()") is Postgres-only;
    # tests/test_team_management.py uses the patch_now_defaults_for_sqlite
    # autouse fixture from test_signup_v6_4.py to swap to CURRENT_TIMESTAMP.
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    tenant = relationship("Tenant")
    actor  = relationship("User", foreign_keys=[actor_user_id])
