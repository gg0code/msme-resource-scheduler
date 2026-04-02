"""
```python
"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This file provides tenant-scoped bulk import functionality for employees, machines, and skills from CSV/XLSX files. 
It was introduced in v1.0 and enhanced to v1.1 with mandatory tenant_id parameters on all import functions to ensure 
data isolation between tenants. This utility sits in the backend/app/utils/ layer and serves as a bridge between 
raw file data and our SQLAlchemy ORM models, handling both CSV and Excel formats with proper error reporting.

WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Reads uploaded file content (bytes) and determines format by filename extension (.xlsx vs .csv)
2. Parses file content into list of dictionaries with column headers as keys
3. Iterates through each row, validates required fields, and creates SQLAlchemy model instances
4. For employees: handles pipe-separated skills (SkillName:Level) and optional leave periods
5. For machines: handles pipe-separated skill requirements (SkillName:Level:Count) and optional downtime periods
6. For skills: creates new tenant-scoped skills with categories and descriptions
7. Auto-creates missing skills during employee/machine imports within the tenant scope
8. Commits all changes in batches and returns detailed success/failure statistics with error messages
9. Provides CSV template generation functions for download by users

KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name         : _read_csv
Type         : function
Purpose      : Parses CSV file content from bytes into a list of dictionaries. Handles UTF-8 BOM stripping 
               to prevent encoding issues with Excel-exported CSV files.
Parameters   : content (bytes) - raw file content from upload
Returns      : List[Dict[str, str]] - each row as dictionary with column headers as keys
Calls        : csv.DictReader from Python standard library
DB/API       : None
Side effects : None

Name         : _read_xlsx
Type         : function
Purpose      : Parses Excel (.xlsx) file content from bytes into same format as CSV. Handles empty rows and 
               None values gracefully. Only reads the active worksheet.
Parameters   : content (bytes) - raw Excel file content from upload
Returns      : List[Dict[str, str]] - each row as dictionary, matching CSV format
Calls        : openpyxl.load_workbook for Excel parsing
DB/API       : None
Side effects : None

Name         : _read_file
Type         : function
Purpose      : Router function that delegates to appropriate parser based on file extension. Provides unified 
               interface for both CSV and Excel file handling.
Parameters   : content (bytes) - raw file content, filename (str) - original filename with extension
Returns      : List[Dict[str, str]] - parsed rows regardless of source format
Calls        : _read_csv or _read_xlsx based on filename
DB/API       : None
Side effects : None

Name         : _parse_date
Type         : function
Purpose      : Safely converts YYYY-MM-DD string to Python date object. Returns None for empty/invalid dates 
               instead of crashing, allowing optional date fields in imports.
Parameters   : val (str) - date string in ISO format
Returns      : Optional[date] - Python date object or None if invalid/empty
Calls        : date.fromisoformat from Python standard library
DB/API       : None
Side effects : None

Name         : _get_or_create_skill
Type         : function
Purpose      : Finds existing skill by name within tenant scope, or creates new one if missing. Ensures all 
               skills referenced in employee/machine imports exist before creating relationships.
Parameters   : db (Session) - SQLAlchemy session, name (str) - skill name, tenant_id (int) - tenant scope
Returns      : Skill - existing or newly created skill model instance
Calls        : SQLAlchemy query operations
DB/API       : SELECT query for existing skill, INSERT if not found, both filtered by tenant_id
Side effects : May create new Skill record in database, calls db.flush() to get ID

Name         : import_employees
Type         : function
Purpose      : Bulk imports employee records from CSV/Excel with skills, availability, and optional leave periods. 
               Creates EmployeeSkill relationships and EmployeeLeave records. Each employee is strictly tenant-scoped.
Parameters   : db (Session) - database session, content (bytes) - file content, tenant_id (int) - tenant scope, 
               filename (str) - for format detection (default "file.csv")
Returns      : Dict[str, Any] - {"rows_imported": int, "rows_failed": int, "errors": List[str]}
Calls        : _read_file, _get_or_create_skill, _parse_date
DB/API       : INSERT Employee, EmployeeSkill, EmployeeLeave records, all with tenant_id filter
Side effects : Creates database records, commits transaction, may rollback on individual row errors

Name         : import_machines
Type         : function
Purpose      : Bulk imports machine records with skill requirements and optional downtime periods. Creates 
               MachineSkillRequirement relationships with employee count per skill. All records tenant-scoped.
Parameters   : db (Session) - database session, content (bytes) - file content, tenant_id (int) - tenant scope,
               filename (str) - for format detection (default "file.csv")
Returns      : Dict[str, Any] - {"rows_imported": int, "rows_failed": int, "errors": List[str]}
Calls        : _read_file, _get_or_create_skill, _parse_date
DB/API       : INSERT Machine, MachineSkillRequirement, MachineDowntime records with tenant_id
Side effects : Creates database records, commits transaction, may rollback on individual row errors

Name         : import_skills
Type         : function
Purpose      : Bulk imports skill catalog with categories and descriptions. Prevents duplicate skills within 
               same tenant. Used for pre-populating skill master data before employee/machine imports.
Parameters   : db (Session) - database session, content (bytes) -
"""

import csv
import io
import openpyxl
from datetime import date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine, MachineSkillRequirement
from app.models.skill import Skill


def _read_csv(content: bytes) -> List[Dict[str, str]]:
    text = content.decode("utf-8-sig")   # strip BOM if present
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader]


def _read_xlsx(content: bytes) -> List[Dict[str, str]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    result = []
    for row in rows[1:]:
        if all(v is None for v in row):
            continue  # skip empty rows
        result.append({
            headers[i]: (str(v).strip() if v is not None else "")
            for i, v in enumerate(row)
            if i < len(headers)
        })
    return result


def _read_file(content: bytes, filename: str) -> List[Dict[str, str]]:
    if filename.endswith(".xlsx"):
        return _read_xlsx(content)
    return _read_csv(content)


def _parse_date(val: str) -> Optional[date]:
    """Parse YYYY-MM-DD date string, return None if empty or invalid."""
    val = (val or "").strip()
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None


def _get_or_create_skill(db: Session, name: str, tenant_id: int) -> Skill:
    """Find skill by name within tenant, or create it if missing."""
    skill = db.query(Skill).filter(
        Skill.name == name,
        Skill.tenant_id == tenant_id,       # ← tenant scoped
    ).first()
    if not skill:
        skill = Skill(name=name, category="Generic", tenant_id=tenant_id)  # ← tenant_id
        db.add(skill)
        db.flush()
    return skill


# ── Employee CSV ───────────────────────────────────────────────────────────
# Expected columns:
#   full_name*, department, employment_type, base_availability_pct,
#   status, contact_number, join_date, hourly_rate, overtime_rate,
#   skills  (pipe-separated "SkillName:Level" e.g. "CNC:Premium|Welding:Generic")

def import_employees(db: Session, content: bytes, tenant_id: int, filename: str = "file.csv") -> Dict[str, Any]:
    rows = _read_file(content, filename)
    ok, failed, errors = 0, 0, []

    for i, row in enumerate(rows, start=2):
        name = (row.get("full_name") or "").strip()
        if not name:
            errors.append(f"Row {i}: full_name is required — skipped")
            failed += 1
            continue

        try:
            emp = Employee(
                tenant_id=tenant_id,                                        # ← tenant_id
                full_name=name,
                department=(row.get("department") or "").strip() or None,
                employment_type=(row.get("employment_type") or "Full-time").strip(),
                base_availability_pct=float(row.get("base_availability_pct") or 100),
                status=(row.get("status") or "Active").strip(),
                contact_number=(row.get("contact_number") or "").strip() or None,
                join_date=(row.get("join_date") or "").strip() or None,
                hourly_rate=float(row["hourly_rate"]) if (row.get("hourly_rate") or "").strip() else None,
                overtime_rate=float(row["overtime_rate"]) if (row.get("overtime_rate") or "").strip() else None,
            )
            db.add(emp)
            db.flush()

            skills_raw = (row.get("skills") or "").strip()
            if skills_raw:
                for part in skills_raw.split("|"):
                    part = part.strip()
                    if not part:
                        continue
                    if ":" in part:
                        sname, slevel = part.rsplit(":", 1)
                    else:
                        sname, slevel = part, "Generic"
                    sname  = sname.strip()
                    slevel = slevel.strip()
                    skill  = _get_or_create_skill(db, sname, tenant_id)    # ← tenant scoped
                    db.add(EmployeeSkill(
                        employee_id=emp.id,
                        skill_id=skill.id,
                        skill_level=slevel,
                        tenant_id=tenant_id,                                # ← tenant_id
                    ))

            # ── Import leave period if provided ─────────────────────────
            leave_start = _parse_date(row.get("leave_start") or "")
            leave_end   = _parse_date(row.get("leave_end") or "")
            if leave_start and leave_end:
                if leave_end >= leave_start:
                    from app.models.unavailability import EmployeeLeave
                    db.add(EmployeeLeave(
                        tenant_id   = tenant_id,
                        employee_id = emp.id,
                        start_date  = leave_start,
                        end_date    = leave_end,
                        reason      = (row.get("leave_reason") or "").strip() or None,
                    ))
                else:
                    errors.append(f"Row {i} ({name}): leave_end before leave_start — leave skipped")

            ok += 1
        except Exception as e:
            errors.append(f"Row {i} ({name}): {e}")
            failed += 1
            db.rollback()

    db.commit()
    return {"rows_imported": ok, "rows_failed": failed, "errors": errors}


# ── Machine CSV ────────────────────────────────────────────────────────────
# Expected columns:
#   name*, machine_type, location_bay, base_availability_pct,
#   status, hourly_rate,
#   skill_requirements  (pipe-separated "SkillName:Level:Count" e.g. "CNC:Premium:1|Helper:Generic:2")

def import_machines(db: Session, content: bytes, tenant_id: int, filename: str = "file.csv") -> Dict[str, Any]:
    rows = _read_file(content, filename)
    ok, failed, errors = 0, 0, []

    for i, row in enumerate(rows, start=2):
        name = (row.get("name") or "").strip()
        if not name:
            errors.append(f"Row {i}: name is required — skipped")
            failed += 1
            continue

        try:
            machine = Machine(
                tenant_id=tenant_id,                                        # ← tenant_id
                name=name,
                machine_type=(row.get("machine_type") or "").strip() or None,
                location_bay=(row.get("location_bay") or "").strip() or None,
                base_availability_pct=float(row.get("base_availability_pct") or 100),
                status=(row.get("status") or "Operational").strip(),
                hourly_rate=float(row["hourly_rate"]) if (row.get("hourly_rate") or "").strip() else None,
            )
            db.add(machine)
            db.flush()

            reqs_raw = (row.get("skill_requirements") or "").strip()
            if reqs_raw:
                for part in reqs_raw.split("|"):
                    part = part.strip()
                    if not part:
                        continue
                    pieces = [p.strip() for p in part.split(":")]
                    sname  = pieces[0]
                    slevel = pieces[1] if len(pieces) > 1 else "Generic"
                    scount = int(pieces[2]) if len(pieces) > 2 else 1
                    skill  = _get_or_create_skill(db, sname, tenant_id)    # ← tenant scoped
                    db.add(MachineSkillRequirement(
                        machine_id=machine.id,
                        skill_id=skill.id,
                        min_skill_level=slevel,
                        employees_required=scount,
                        tenant_id=tenant_id,                                # ← tenant_id
                    ))

            # ── Import downtime period if provided ──────────────────────
            dt_start = _parse_date(row.get("downtime_start") or "")
            dt_end   = _parse_date(row.get("downtime_end") or "")
            if dt_start and dt_end:
                if dt_end >= dt_start:
                    from app.models.unavailability import MachineDowntime
                    db.add(MachineDowntime(
                        tenant_id  = tenant_id,
                        machine_id = machine.id,
                        start_date = dt_start,
                        end_date   = dt_end,
                        reason     = (row.get("downtime_reason") or "").strip() or None,
                    ))
                else:
                    errors.append(f"Row {i} ({name}): downtime_end before downtime_start — downtime skipped")

            ok += 1
        except Exception as e:
            errors.append(f"Row {i} ({name}): {e}")
            failed += 1
            db.rollback()

    db.commit()
    return {"rows_imported": ok, "rows_failed": failed, "errors": errors}


# ── Skill CSV ──────────────────────────────────────────────────────────────
# Expected columns: name*, category (Generic/Premium), description

def import_skills(db: Session, content: bytes, tenant_id: int) -> Dict[str, Any]:  # ← tenant_id added
    rows = _read_csv(content)
    ok, failed, errors = 0, 0, []

    for i, row in enumerate(rows, start=2):
        name = (row.get("name") or "").strip()
        if not name:
            errors.append(f"Row {i}: name is required — skipped")
            failed += 1
            continue

        existing = db.query(Skill).filter(
            Skill.name == name,
            Skill.tenant_id == tenant_id,                                   # ← tenant scoped
        ).first()
        if existing:
            errors.append(f"Row {i}: Skill '{name}' already exists — skipped")
            failed += 1
            continue

        try:
            db.add(Skill(
                tenant_id=tenant_id,                                        # ← tenant_id
                name=name,
                category=(row.get("category") or "Generic").strip(),
                description=(row.get("description") or "").strip() or None,
            ))
            ok += 1
        except Exception as e:
            errors.append(f"Row {i} ({name}): {e}")
            failed += 1

    db.commit()
    return {"rows_imported": ok, "rows_failed": failed, "errors": errors}


# ── CSV Template generators ────────────────────────────────────────────────

EMPLOYEE_TEMPLATE = """full_name,department,employment_type,base_availability_pct,status,contact_number,join_date,hourly_rate,overtime_rate,skills,leave_start,leave_end,leave_reason
Ramesh Sharma,Production,Full-time,100,Active,9812345678,2023-01-15,150,225,CNC Ops:Premium|Welding:Generic,,,
Priya Mehta,Quality,Full-time,100,Active,9898765432,2022-06-01,120,180,Quality Check:Intermediate,2026-04-01,2026-04-05,Annual Leave
"""

MACHINE_TEMPLATE = """name,machine_type,location_bay,base_availability_pct,status,hourly_rate,skill_requirements,downtime_start,downtime_end,downtime_reason
CNC Lathe #1,CNC Lathe,Bay A,100,Operational,80,CNC Ops:Premium:1|Helper:Generic:1,,,
VMC Mill #2,VMC,Bay B,100,Operational,120,CNC Ops:Intermediate:2,2026-04-10,2026-04-12,Scheduled Maintenance
"""

SKILL_TEMPLATE = """name,category,description
CNC Ops,Premium,Operating CNC lathes and mills
Welding,Generic,MIG/TIG welding operations
Quality Check,Intermediate,Dimensional inspection and QC
"""

TEMPLATES = {
    "employees": ("employees_template.csv", EMPLOYEE_TEMPLATE),
    "machines":  ("machines_template.csv",  MACHINE_TEMPLATE),
    "skills":    ("skills_template.csv",    SKILL_TEMPLATE),
}


# ── XLSX Template generators ───────────────────────────────────────────────

def _make_xlsx(headers: list, sample_rows: list) -> bytes:
    """Build an xlsx file with headers and sample rows, return as bytes."""
    wb = openpyxl.Workbook()
    ws = wb.active

    # Style header row
    from openpyxl.styles import Font, PatternFill, Alignment
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="2563EB")  # blue-600

    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = max(len(header) + 4, 16)

    # Sample rows
    for row_idx, row_data in enumerate(sample_rows, start=2):
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_EMP_HEADERS = [
    "full_name", "department", "employment_type", "base_availability_pct",
    "status", "contact_number", "join_date", "hourly_rate", "overtime_rate",
    "skills", "leave_start", "leave_end", "leave_reason",
]
_EMP_SAMPLES = [
    ["Ramesh Sharma", "Production", "Full-time", 100, "Active", "9812345678",
     "2023-01-15", 150, 225, "CNC Ops:Premium|Welding:Generic", "", "", ""],
    ["Priya Mehta", "Quality", "Full-time", 100, "Active", "9898765432",
     "2022-06-01", 120, 180, "Quality Check:Intermediate", "2026-04-01", "2026-04-05", "Annual Leave"],
]

_MACH_HEADERS = [
    "name", "machine_type", "location_bay", "base_availability_pct",
    "status", "hourly_rate", "skill_requirements",
    "downtime_start", "downtime_end", "downtime_reason",
]
_MACH_SAMPLES = [
    ["CNC Lathe #1", "CNC Lathe", "Bay A", 100, "Operational", 80,
     "CNC Ops:Premium:1|Helper:Generic:1", "", "", ""],
    ["VMC Mill #2", "VMC", "Bay B", 100, "Operational", 120,
     "CNC Ops:Intermediate:2", "2026-04-10", "2026-04-12", "Scheduled Maintenance"],
]

XLSX_TEMPLATES = {
    "employees": ("employees_template.xlsx", _make_xlsx(_EMP_HEADERS, _EMP_SAMPLES)),
    "machines":  ("machines_template.xlsx",  _make_xlsx(_MACH_HEADERS, _MACH_SAMPLES)),
}
