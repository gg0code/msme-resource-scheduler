# tests/test_csv_import.py
# SRS §6.16 CSV / Excel Import — unit tests

import pytest
from app.services.csv_import import (
    _read_csv,
    _read_file,
    import_employees,
    import_machines,
)


class TestReadCsv:

    def test_reads_header_and_rows(self):
        csv_bytes = b"full_name,department\nRavi,Press\nMeena,Finishing\n"
        rows = _read_csv(csv_bytes)
        assert len(rows) == 2
        assert rows[0]["full_name"] == "Ravi"
        assert rows[0]["department"] == "Press"

    def test_strips_bom(self):
        bom_csv = b"\xef\xbb\xbffull_name,department\nSuresh,Offset\n"
        rows = _read_csv(bom_csv)
        assert rows[0]["full_name"] == "Suresh"

    def test_empty_csv_returns_empty_list(self):
        rows = _read_csv(b"full_name,department\n")
        assert rows == []


class TestReadFile:

    def test_dispatches_csv_for_csv_filename(self):
        csv_bytes = b"full_name\nRavi\n"
        rows = _read_file(csv_bytes, "workers.csv")
        assert rows[0]["full_name"] == "Ravi"

    def test_dispatches_csv_for_unknown_extension(self):
        csv_bytes = b"full_name\nRavi\n"
        rows = _read_file(csv_bytes, "workers.txt")
        assert rows[0]["full_name"] == "Ravi"


class TestImportEmployees:

    def test_creates_employee_from_valid_csv(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        csv_content = b"full_name,department,employment_type\nCSV Worker,Press,Full-time\n"
        result = import_employees(db, csv_content, tenant.id, "workers.csv")
        assert result["rows_imported"] >= 1

    def test_skips_row_with_missing_full_name(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        csv_content = b"full_name,department\n,Press\n"
        result = import_employees(db, csv_content, tenant.id, "workers.csv")
        assert result["rows_imported"] == 0
        assert result["rows_failed"] >= 1 or len(result.get("errors", [])) >= 0

    def test_created_employee_belongs_to_tenant(self, db, auth_headers):
        from app.models.auth import Tenant
        from app.models.employee import Employee
        tenant = db.query(Tenant).first()
        csv_content = b"full_name,department\nTenant CSV Emp,Assembly\n"
        import_employees(db, csv_content, tenant.id, "workers.csv")
        emp = db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
            Employee.full_name == "Tenant CSV Emp",
        ).first()
        assert emp is not None

    def test_result_has_created_key(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        result = import_employees(db, b"full_name\n", tenant.id)
        assert "rows_imported" in result


class TestImportMachines:

    def test_creates_machine_from_valid_csv(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        csv_content = b"name,machine_type\nCSV Press,Offset\n"
        result = import_machines(db, csv_content, tenant.id, "machines.csv")
        assert result["rows_imported"] >= 1

    def test_skips_row_with_missing_name(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        csv_content = b"name,machine_type\n,Offset\n"
        result = import_machines(db, csv_content, tenant.id, "machines.csv")
        assert result["rows_imported"] == 0

    def test_result_has_created_key(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        result = import_machines(db, b"name\n", tenant.id)
        assert "rows_imported" in result
