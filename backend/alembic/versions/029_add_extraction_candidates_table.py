# alembic/versions/029_add_extraction_candidates_table.py
#
# FILE PURPOSE
# Migration 029 (v6.3.13) - extraction_candidates staging table. Holds
# entity candidates that future versions extract from inbound WhatsApp
# messages. v6.3.13 ships ONLY the schema. No SQLAlchemy model, no
# router, no service - those land in v6.3.14. No code reads or writes
# this table yet; it sits empty after the upgrade.
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.create_table / drop_table
#   alembic.op.create_index / drop_index
#   alembic.op.create_unique_constraint / drop_constraint
#   sqlalchemy column types: Integer, String, Text, Float, DateTime
#
# SCHEMA OVERVIEW
#   id                  PK
#   tenant_id           FK tenants.id ON DELETE CASCADE
#   entity_type         VARCHAR(50) - see ENTITY_TYPE_VOCAB below
#   raw_value           TEXT  - extractor output verbatim
#   normalized_value    TEXT  - canonical form used for de-duplication
#   confidence          FLOAT - LLM self-reported [0.0, 1.0]
#   mention_count       INT   - upsert-incremented on each re-mention
#   first_seen          TIMESTAMPTZ - when this candidate was first extracted
#   last_seen           TIMESTAMPTZ - most recent mention
#   source_type         VARCHAR(20) - 'whatsapp' today; future: 'slack', 'sms'
#   source_message_id   VARCHAR(120) - provenance pointer (nullable)
#   created_at          TIMESTAMPTZ DEFAULT now()
#   updated_at          TIMESTAMPTZ DEFAULT now()
#
# INDEXES
#   idx_extraction_candidates_tenant_entity_type
#       (tenant_id, entity_type) - "all candidates of type X for tenant Y"
#   idx_extraction_candidates_tenant_normalized
#       (tenant_id, normalized_value) - de-dup lookup before upsert
#   idx_extraction_candidates_tenant_mentions
#       (tenant_id, mention_count) - v6.3.15 promotion job's threshold scan
#
# CONSTRAINTS
#   uq_extraction_candidates_tenant_type_value
#       UNIQUE (tenant_id, entity_type, normalized_value)
#       Enforces the upsert invariant: one row per distinct entity per
#       tenant. Lets v6.3.14 use INSERT ... ON CONFLICT DO UPDATE.
#
# DESIGN NOTES
#   - entity_type is VARCHAR(50) with NO CHECK constraint. Vocabulary
#     lives in this docstring (ENTITY_TYPE_VOCAB) and will be repeated
#     in the v6.3.14 model file. Application-level discipline keeps
#     the migration simple and lets v6.3.14+ add new types without a
#     follow-up schema change.
#   - confidence has NO CHECK constraint. Range is documented as
#     [0.0, 1.0] LLM self-reported; v6.3.15 promotion threshold is
#     >= 0.7. Allowing experimental out-of-range values (e.g. -1 for
#     "unknown") keeps the door open without a migration.
#   - mention_count uses upsert-on-conflict semantics (one row per
#     distinct entity, mutated on re-mention). The events table from
#     migration 028 already provides the immutable audit trail; this
#     table is the materialised running count, not the audit log.
#   - source_type defaults to 'whatsapp' so v6.3.14 can omit it on
#     insert. When a non-WhatsApp source lands later it sets the
#     column explicitly. Two-column source provenance (source_type +
#     source_message_id) keeps "all candidates from this message"
#     queryable while staying source-agnostic.
#   - All TIMESTAMPTZ columns mirror the events table (migration 028).
#     Tests that use these columns will need patch_now_defaults_for_sqlite
#     (per backend/tests/services/conftest.py) to swap now() to
#     CURRENT_TIMESTAMP for SQLite. Not relevant for v6.3.13 since no
#     unit test inserts into this table yet.
#
# ENTITY_TYPE_VOCAB (documented; not enforced in DB)
#   'employee'   - worker names mentioned in attendance / task contexts
#   'machine'    - machine references
#   'customer'   - customer names from job mentions
#   'skill'      - skill mentions
#   'material'   - material mentions
#   'job'        - job description / project mentions
#   'issue'      - problems / blockers mentioned
#
# FUTURE CONSUMERS
#   v6.3.14 - app/models/extraction_candidate.py + extractor service
#             that writes rows from inbound WhatsApp messages.
#   v6.3.15 - promotion job that reads candidates with mention_count
#             above threshold and confidence >= 0.7, then materialises
#             them into the canonical employee/machine/customer/skill
#             tables.

from alembic import op
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "029"
down_revision = "028"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Create the extraction_candidates table, its three indexes, and the
    upsert uniqueness constraint.

    Called by:    alembic upgrade head
    Calls into:   op.create_table(), op.create_index(),
                  op.create_unique_constraint()
    Side effects: CREATE TABLE extraction_candidates;
                  CREATE INDEX x3; ADD CONSTRAINT UNIQUE x1.
    """
    op.create_table(
        "extraction_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type",      sa.String(50), nullable=False),
        sa.Column("raw_value",        sa.Text(),     nullable=False),
        sa.Column("normalized_value", sa.Text(),     nullable=False),
        sa.Column("confidence",       sa.Float(),    nullable=False),
        sa.Column(
            "mention_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.String(20),
            nullable=False,
            server_default="whatsapp",
        ),
        sa.Column("source_message_id", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # (tenant_id, entity_type) - "all candidates of type X for tenant Y".
    op.create_index(
        "idx_extraction_candidates_tenant_entity_type",
        "extraction_candidates",
        ["tenant_id", "entity_type"],
    )
    # (tenant_id, normalized_value) - de-dup lookup before upsert.
    op.create_index(
        "idx_extraction_candidates_tenant_normalized",
        "extraction_candidates",
        ["tenant_id", "normalized_value"],
    )
    # (tenant_id, mention_count) - v6.3.15 promotion job threshold scan.
    op.create_index(
        "idx_extraction_candidates_tenant_mentions",
        "extraction_candidates",
        ["tenant_id", "mention_count"],
    )

    # Upsert invariant: one row per distinct entity per tenant. Backs
    # INSERT ... ON CONFLICT DO UPDATE in v6.3.14.
    op.create_unique_constraint(
        "uq_extraction_candidates_tenant_type_value",
        "extraction_candidates",
        ["tenant_id", "entity_type", "normalized_value"],
    )


def downgrade() -> None:
    """
    Drop the extraction_candidates table, its indexes, and the unique
    constraint, in reverse order of creation.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_constraint(), op.drop_index(), op.drop_table()
    Side effects: DROP TABLE extraction_candidates; all candidate rows
                  permanently lost. Safe at v6.3.13 because the table
                  is empty - no application code writes to it yet.
    """
    op.drop_constraint(
        "uq_extraction_candidates_tenant_type_value",
        "extraction_candidates",
        type_="unique",
    )
    op.drop_index(
        "idx_extraction_candidates_tenant_mentions",
        table_name="extraction_candidates",
    )
    op.drop_index(
        "idx_extraction_candidates_tenant_normalized",
        table_name="extraction_candidates",
    )
    op.drop_index(
        "idx_extraction_candidates_tenant_entity_type",
        table_name="extraction_candidates",
    )
    op.drop_table("extraction_candidates")
