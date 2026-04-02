"""
utils/csv_import.py — V1.1
Added: tenant_id parameter to all three import functions.
Every model insert and skill lookup is now tenant-scoped.
"""

import csv
import io
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine, MachineSkillRequirement
from app.models.skill import Skill


def _read_csv(content: bytes) -> List[Dict[str, str]]:
    text = content.decode("utf-8-sig")   # strip BOM if present
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader]


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

def import_employees(db: Session, content: bytes, tenant_id: int) -> Dict[str, Any]:  # ← tenant_id added
    rows = _read_csv(content)
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

def import_machines(db: Session, content: bytes, tenant_id: int) -> Dict[str, Any]:  # ← tenant_id added
    rows = _read_csv(content)
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

EMPLOYEE_TEMPLATE = """full_name,department,employment_type,base_availability_pct,status,contact_number,join_date,hourly_rate,overtime_rate,skills
Ramesh Sharma,Production,Full-time,100,Active,9812345678,2023-01-15,150,225,CNC Ops:Premium|Welding:Generic
Priya Mehta,Quality,Full-time,100,Active,9898765432,2022-06-01,120,180,Quality Check:Intermediate
"""

MACHINE_TEMPLATE = """name,machine_type,location_bay,base_availability_pct,status,hourly_rate,skill_requirements
CNC Lathe #1,CNC Lathe,Bay A,100,Operational,80,CNC Ops:Premium:1|Helper:Generic:1
VMC Mill #2,VMC,Bay B,100,Operational,120,CNC Ops:Intermediate:2
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
