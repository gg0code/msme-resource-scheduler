# backend/tests/test_alembic_migrations.py
# Tests for Alembic migration file integrity.
#
# WHY NO UPGRADE/DOWNGRADE TESTS AGAINST SQLITE:
# Our migrations use PostgreSQL-specific DDL:
#   - ALTER COLUMN ... SET NOT NULL  (migration 004)
#   - PG_ARRAY type                 (schedule_entries)
#   - IF NOT EXISTS clauses         (various)
# SQLite supports none of these. Running upgrade/downgrade in tests
# would either fail or require heavy mocking that hides real problems.
#
# INSTEAD: verify migration file integrity here (no DB needed), and
# run live DB tests manually before deploying:
#
#   cd backend
#   alembic upgrade head    # must succeed on real PostgreSQL
#   alembic downgrade base  # must succeed on real PostgreSQL
#   alembic upgrade head    # verify round-trip

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.fixture(scope="module")
def script_dir():
    """ScriptDirectory built from alembic.ini — no DB connection required."""
    cfg = Config("alembic.ini")
    return ScriptDirectory.from_config(cfg)


class TestMigrationFileIntegrity:
    def test_no_duplicate_revision_ids(self, script_dir):
        """No two migration files share the same revision ID."""
        revisions = list(script_dir.walk_revisions())
        ids = [r.revision for r in revisions]
        dupes = [r for r in ids if ids.count(r) > 1]
        assert not dupes, f"Duplicate revision IDs found: {dupes}"

    def test_migration_chain_no_gaps(self, script_dir):
        """Every down_revision (except base) points to an existing revision."""
        revisions = list(script_dir.walk_revisions())
        all_ids = {r.revision for r in revisions}
        for rev in revisions:
            if rev.down_revision is None:
                continue
            # down_revision can be a tuple for merge migrations
            parents = (
                rev.down_revision
                if isinstance(rev.down_revision, (list, tuple))
                else [rev.down_revision]
            )
            for parent in parents:
                assert parent in all_ids, (
                    f"Revision {rev.revision} references missing "
                    f"down_revision '{parent}'"
                )

    def test_single_head(self, script_dir):
        """Linear chain — exactly one head revision (no unmerged branches)."""
        heads = script_dir.get_heads()
        assert len(heads) == 1, (
            f"Expected 1 head, got {len(heads)}: {heads}. "
            f"A merge migration may be needed."
        )

    def test_head_is_030(self, script_dir):
        """Current head must be revision 030 (v6.3.15 revised confirmation
        state columns on extraction_candidates)."""
        heads = script_dir.get_heads()
        assert "030" in heads, (
            f"Expected head to be '030', got: {heads}"
        )

    def test_030_in_chain(self, script_dir):
        """Migration 030 (confirmation state columns) must be in the
        chain and chain off 029."""
        revisions = {r.revision: r for r in script_dir.walk_revisions()}
        assert "030" in revisions, (
            "Migration 030 (add_confirmation_state_columns) not found"
        )
        assert revisions["030"].down_revision == "029", (
            f"Migration 030 must chain off 029, got "
            f"{revisions['030'].down_revision}"
        )

    def test_021_in_chain(self, script_dir):
        """Migration 021 (add is_locked to jobs) must be in the chain."""
        ids = {r.revision for r in script_dir.walk_revisions()}
        assert "021" in ids, "Migration 021 (add_is_locked_to_jobs) not found"

    def test_029_in_chain(self, script_dir):
        """Migration 029 (extraction_candidates table) must be in the chain
        and chain off 028."""
        revisions = {r.revision: r for r in script_dir.walk_revisions()}
        assert "029" in revisions, (
            "Migration 029 (add_extraction_candidates_table) not found"
        )
        assert revisions["029"].down_revision == "028", (
            f"Expected 029 to chain off 028, got down_revision="
            f"{revisions['029'].down_revision!r}"
        )

    def test_all_migration_files_importable(self, script_dir):
        """All migration files can be parsed without import errors."""
        errors = []
        for rev in script_dir.walk_revisions():
            try:
                # walk_revisions() already loads each module — if we got here
                # without exception the file is importable
                assert rev.revision is not None
            except Exception as exc:
                errors.append(f"{rev.revision}: {exc}")
        assert not errors, f"Migration import errors:\n" + "\n".join(errors)


class TestLiveDatabaseSchema:
    """
    Skipped in unit test suite — requires live PostgreSQL.
    Run manually before every deploy:
        cd backend
        alembic upgrade head
        alembic downgrade base
        alembic upgrade head
    """

    @pytest.mark.skip(reason="Requires live PostgreSQL — run manually before deploy")
    def test_upgrade_head(self): pass

    @pytest.mark.skip(reason="Requires live PostgreSQL — run manually before deploy")
    def test_downgrade_base(self): pass

    @pytest.mark.skip(reason="Requires live PostgreSQL — run manually before deploy")
    def test_schema_columns(self): pass
