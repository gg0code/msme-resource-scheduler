# tests/test_rag_pipeline.py
# SRS §6.22 RAG Pipeline — flat file MVP (v6.1)
# Pure filesystem tests — no DB, no HTTP.

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.services.rag_service import (
    seed_rag_from_template,
    load_rag_context,
    VALID_INDUSTRIES,
    RAG_DATA_ROOT,
    TEMPLATES_DIR,
)


class TestRagValidIndustries:

    def test_printing_is_valid(self):
        assert "printing" in VALID_INDUSTRIES

    def test_manufacturing_is_valid(self):
        assert "manufacturing" in VALID_INDUSTRIES

    def test_fabrication_is_valid(self):
        assert "fabrication" in VALID_INDUSTRIES

    def test_field_service_is_valid(self):
        assert "field_service" in VALID_INDUSTRIES

    def test_chemical_is_not_valid(self):
        assert "chemical" not in VALID_INDUSTRIES

    def test_exactly_four_valid_industries(self):
        assert len(VALID_INDUSTRIES) == 4


class TestSeedRagFromTemplate:

    def _patch(self, tmp_path):
        """Patch both RAG_DATA_ROOT and TEMPLATES_DIR to use tmp_path."""
        from unittest.mock import patch as mk
        p1 = mk("app.services.rag_service.RAG_DATA_ROOT", tmp_path)
        p2 = mk("app.services.rag_service.TEMPLATES_DIR", tmp_path / "_templates")
        return p1, p2

    def test_seed_creates_tenant_folder(self, tmp_path):
        p1, p2 = self._patch(tmp_path)
        with p1, p2:
            template_dir = tmp_path / "_templates" / "printing"
            template_dir.mkdir(parents=True)
            (template_dir / "test.txt").write_text("test content")
            result = seed_rag_from_template(999, "printing")
        assert result is True
        assert (tmp_path / "999").is_dir()

    def test_seed_copies_txt_files(self, tmp_path):
        p1, p2 = self._patch(tmp_path)
        with p1, p2:
            template_dir = tmp_path / "_templates" / "printing"
            template_dir.mkdir(parents=True)
            (template_dir / "knowledge.txt").write_text("paper rates")
            seed_rag_from_template(42, "printing")
        assert (tmp_path / "42" / "knowledge.txt").exists()

    def test_seed_invalid_industry_returns_false(self, tmp_path):
        p1, p2 = self._patch(tmp_path)
        with p1, p2:
            result = seed_rag_from_template(1, "chemical")
        assert result is False

    def test_seed_unknown_industry_returns_false(self, tmp_path):
        p1, p2 = self._patch(tmp_path)
        with p1, p2:
            result = seed_rag_from_template(1, "nonexistent_industry")
        assert result is False

    def test_seed_does_not_overwrite_existing_files(self, tmp_path):
        p1, p2 = self._patch(tmp_path)
        with p1, p2:
            template_dir = tmp_path / "_templates" / "printing"
            template_dir.mkdir(parents=True)
            (template_dir / "rates.txt").write_text("template content")
            tenant_dir = tmp_path / "77"
            tenant_dir.mkdir(parents=True)
            (tenant_dir / "rates.txt").write_text("custom content")
            seed_rag_from_template(77, "printing")
        assert (tmp_path / "77" / "rates.txt").read_text() == "custom content"

    def test_seed_with_real_templates(self):
        template_dir = RAG_DATA_ROOT / "_templates" / "printing"
        assert template_dir.exists(), "Printing template directory must exist in repo"
        txt_files = list(template_dir.glob("*.txt"))
        assert len(txt_files) > 0, "Printing template must have at least one .txt file"


class TestLoadRagContext:

    def test_load_returns_string(self, tmp_path):
        tenant_dir = tmp_path / "55"
        tenant_dir.mkdir()
        (tenant_dir / "info.txt").write_text("some content")
        with patch("app.services.rag_service.RAG_DATA_ROOT", tmp_path):
            result = load_rag_context(55)
        assert isinstance(result, str)
        assert "some content" in result

    def test_load_returns_empty_string_when_no_folder(self, tmp_path):
        with patch("app.services.rag_service.RAG_DATA_ROOT", tmp_path):
            result = load_rag_context(99999)
        assert result == ""

    def test_load_concatenates_multiple_files(self, tmp_path):
        tenant_dir = tmp_path / "56"
        tenant_dir.mkdir()
        (tenant_dir / "a.txt").write_text("content A")
        (tenant_dir / "b.txt").write_text("content B")
        with patch("app.services.rag_service.RAG_DATA_ROOT", tmp_path):
            result = load_rag_context(56)
        assert "content A" in result
        assert "content B" in result

    def test_load_ignores_non_txt_files(self, tmp_path):
        tenant_dir = tmp_path / "57"
        tenant_dir.mkdir()
        (tenant_dir / "data.txt").write_text("valid")
        (tenant_dir / "data.csv").write_text("should be ignored")
        with patch("app.services.rag_service.RAG_DATA_ROOT", tmp_path):
            result = load_rag_context(57)
        assert "valid" in result
        assert "should be ignored" not in result

    def test_tenant_isolation_different_folders(self, tmp_path):
        (tmp_path / "100").mkdir()
        (tmp_path / "101").mkdir()
        (tmp_path / "100" / "a.txt").write_text("tenant 100 only")
        (tmp_path / "101" / "b.txt").write_text("tenant 101 only")
        with patch("app.services.rag_service.RAG_DATA_ROOT", tmp_path):
            ctx_100 = load_rag_context(100)
            ctx_101 = load_rag_context(101)
        assert "tenant 100 only" in ctx_100
        assert "tenant 100 only" not in ctx_101
        assert "tenant 101 only" in ctx_101
        assert "tenant 101 only" not in ctx_100
