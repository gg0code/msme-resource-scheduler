# tests/test_material_estimate.py
# SRS §6.10 Material Estimate (v3.9.8) — pure function unit tests

from app.services.material_estimate import _estimate_materials, _confidence, _confidence_note


class FakeJob:
    def __init__(self, quantity, materials):
        self.quantity = quantity
        self.raw_materials = materials


class TestConfidence:

    def test_zero_jobs_is_none(self):
        assert _confidence(0) == "none"

    def test_one_job_is_low(self):
        assert _confidence(1) == "low"

    def test_two_jobs_is_medium(self):
        assert _confidence(2) == "medium"

    def test_three_or_more_is_high(self):
        assert _confidence(3) == "high"
        assert _confidence(10) == "high"


class TestConfidenceNote:

    def test_zero_note_mentions_cannot_estimate(self):
        note = _confidence_note(0, "brochure")
        assert "Cannot estimate" in note or "No completed" in note

    def test_one_note_warns_not_representative(self):
        note = _confidence_note(1, "brochure")
        assert "1" in note

    def test_two_note_mentions_count(self):
        note = _confidence_note(2, "brochure")
        assert "2" in note

    def test_three_note_mentions_high(self):
        note = _confidence_note(3, "brochure")
        assert "3" in note


class TestEstimateMaterials:

    def test_empty_jobs_returns_empty_list(self):
        result = _estimate_materials([], 100.0)
        assert result == []

    def test_single_job_single_material(self):
        job = FakeJob(quantity=500.0, materials=[
            {"name": "Paper", "quantity": 10.0, "unit": "ream"}
        ])
        result = _estimate_materials([job], 1000.0)
        assert len(result) == 1
        assert result[0]["material"] == "Paper"
        assert result[0]["estimated_qty"] == pytest.approx(20.0)
        assert result[0]["unit"] == "ream"

    def test_job_with_zero_quantity_skipped(self):
        job = FakeJob(quantity=0, materials=[
            {"name": "Ink", "quantity": 5.0, "unit": "litre"}
        ])
        result = _estimate_materials([job], 500.0)
        assert result == []

    def test_job_with_no_materials_returns_empty(self):
        job = FakeJob(quantity=100.0, materials=[])
        result = _estimate_materials([job], 200.0)
        assert result == []

    def test_multiple_jobs_averages_rate(self):
        job1 = FakeJob(quantity=100.0, materials=[{"name": "Paper", "quantity": 2.0, "unit": "ream"}])
        job2 = FakeJob(quantity=200.0, materials=[{"name": "Paper", "quantity": 6.0, "unit": "ream"}])
        result = _estimate_materials([job1, job2], 100.0)
        assert len(result) == 1
        assert result[0]["material"] == "Paper"
        # rate for job1: 2/100 = 0.02, rate for job2: 6/200 = 0.03 -> avg 0.025
        assert result[0]["estimated_qty"] == pytest.approx(2.5)

    def test_multiple_materials_in_one_job(self):
        job = FakeJob(quantity=100.0, materials=[
            {"name": "Paper", "quantity": 5.0, "unit": "ream"},
            {"name": "Ink", "quantity": 2.0, "unit": "litre"},
        ])
        result = _estimate_materials([job], 200.0)
        names = [r["material"] for r in result]
        assert "Paper" in names
        assert "Ink" in names


import pytest
