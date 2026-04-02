"""
```python
"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from app.database import SessionLocal
from app.models.skill import Skill
from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine, MachineSkillRequirement
from app.models.job import Job, JobSkillRequirement
from app.models.auth import Tenant

db = SessionLocal()

print("\n========================================")
print("  MSME Resource Scheduler — Seed Data")
print("========================================\n")

# ===========================================================================
# 0. FIND TENANT
# ===========================================================================
TENANT_SLUG = "acme-mfg"   # ← change if your slug is different

tenant = db.query(Tenant).filter(Tenant.slug == TENANT_SLUG).first()
if not tenant:
    # List available tenants to help user pick the right slug
    all_tenants = db.query(Tenant).all()
    print(f"  ERROR: No tenant found with slug '{TENANT_SLUG}'")
    print(f"  Available tenants: {[(t.slug, t.name) for t in all_tenants]}")
    print(f"  Edit TENANT_SLUG at the top of this script and re-run.")
    db.close()
    sys.exit(1)

TID = tenant.id
print(f"  Seeding for tenant: '{tenant.name}' (id={TID}, slug={tenant.slug})\n")


# ===========================================================================
# 1. SKILLS
# ===========================================================================
print("Seeding skills...")

skills_data = [
    {"name": "CNC Operation", "category": "premium",  "is_premium": True,  "description": "Operating CNC lathes and milling machines"},
    {"name": "Welding",       "category": "premium",  "is_premium": True,  "description": "MIG, TIG and arc welding techniques"},
    {"name": "Grinding",      "category": "generic",  "is_premium": False, "description": "Surface and cylindrical grinding operations"},
    {"name": "Assembly",      "category": "generic",  "is_premium": False, "description": "Mechanical assembly and fitting of components"},
    {"name": "Quality Check", "category": "generic",  "is_premium": False, "description": "Inspection, measurement and quality assurance"},
    {"name": "Assistant1",    "category": "generic",  "is_premium": False, "description": "General shop floor assistance and support tasks"},
    {"name": "Helper",        "category": "generic",  "is_premium": False, "description": "Material handling, cleaning and basic support work"},
]

skill_map = {}
for s in skills_data:
    existing = db.query(Skill).filter(Skill.name == s["name"], Skill.tenant_id == TID).first()
    if existing:
        skill_map[s["name"]] = existing
        print(f"  [skip] {s['name']} already exists")
    else:
        obj = Skill(**s, tenant_id=TID)
        db.add(obj)
        db.flush()
        skill_map[s["name"]] = obj
        print(f"  [+] {s['name']}")

db.commit()
print(f"  Done — {len(skill_map)} skills ready.\n")


# ===========================================================================
# 2. EMPLOYEES
# ===========================================================================
print("Seeding employees...")

employees_data = [
    ("Ramesh Sharma",   "Production", "Full-time",  100, "Active", date(2018, 3, 1),   [("CNC Operation", "Premium"), ("Grinding", "Intermediate")]),
    ("Suresh Patil",    "Production", "Full-time",  100, "Active", date(2019, 7, 15),  [("CNC Operation", "Intermediate"), ("Assembly", "Generic")]),
    ("Mahesh Yadav",    "Production", "Full-time",  100, "Active", date(2020, 1, 10),  [("Welding", "Premium"), ("Assembly", "Intermediate")]),
    ("Dinesh Kumar",    "Production", "Full-time",  100, "Active", date(2017, 5, 20),  [("Welding", "Intermediate"), ("Grinding", "Generic")]),
    ("Prakash Nair",    "Production", "Full-time",  100, "Active", date(2021, 2, 1),   [("Grinding", "Premium"), ("Quality Check", "Intermediate")]),
    ("Rajesh Verma",    "Quality",    "Full-time",  100, "Active", date(2019, 9, 5),   [("Quality Check", "Premium"), ("Assembly", "Generic")]),
    ("Vikram Singh",    "Production", "Full-time",  100, "Active", date(2022, 6, 1),   [("Assembly", "Intermediate"), ("Helper", "Generic")]),
    ("Anil Desai",      "Production", "Part-time",   60, "Active", date(2021, 11, 1),  [("CNC Operation", "Generic"), ("Assistant1", "Generic")]),
    ("Santosh More",    "Production", "Full-time",  100, "Active", date(2020, 8, 15),  [("Welding", "Generic"), ("Assembly", "Generic")]),
    ("Ganesh Raut",     "Production", "Full-time",  100, "Active", date(2023, 1, 10),  [("Grinding", "Generic"), ("Helper", "Generic")]),
    ("Priya Joshi",     "Quality",    "Full-time",  100, "Active", date(2022, 3, 20),  [("Quality Check", "Intermediate"), ("Assistant1", "Generic")]),
    ("Kavita Shinde",   "Production", "Part-time",   50, "Active", date(2023, 6, 1),   [("Assembly", "Generic"), ("Helper", "Generic")]),
    ("Rahul Kulkarni",  "Production", "Contract",    80, "Active", date(2024, 1, 5),   [("Assistant1", "Generic"), ("Helper", "Generic")]),
    ("Sanjay Bhosale",  "Production", "Full-time",  100, "Active", date(2016, 4, 12),  [("CNC Operation", "Premium"), ("Welding", "Intermediate"), ("Quality Check", "Generic")]),
]

emp_map = {}
for (name, dept, emp_type, avail, status, join_date, skills) in employees_data:
    existing = db.query(Employee).filter(Employee.full_name == name, Employee.tenant_id == TID).first()
    if existing:
        emp_map[name] = existing
        print(f"  [skip] {name} already exists")
        continue

    emp = Employee(
        tenant_id=TID,
        full_name=name, department=dept, employment_type=emp_type,
        base_availability_pct=avail, status=status, join_date=join_date,
    )
    db.add(emp)
    db.flush()

    for skill_name, level in skills:
        skill_obj = skill_map.get(skill_name)
        if skill_obj:
            db.add(EmployeeSkill(tenant_id=TID, employee_id=emp.id, skill_id=skill_obj.id, skill_level=level))

    emp_map[name] = emp
    print(f"  [+] {name} ({dept}, {emp_type})")

db.commit()
print(f"  Done — {len(emp_map)} employees ready.\n")


# ===========================================================================
# 3. MACHINES
# ===========================================================================
print("Seeding machines...")

machines_data = [
    {
        "name": "CNC Lathe #1", "machine_type": "CNC Lathe",
        "base_availability_pct": 100.0, "location_bay": "Bay A", "status": "Operational",
        "skill_requirements": [{"skill": "CNC Operation", "min_level": "Intermediate", "headcount": 1}],
    },
    {
        "name": "MIG Welder #1", "machine_type": "Welding Station",
        "base_availability_pct": 100.0, "location_bay": "Bay B", "status": "Operational",
        "skill_requirements": [{"skill": "Welding", "min_level": "Generic", "headcount": 1}],
    },
    {
        "name": "Surface Grinder #1", "machine_type": "Grinder",
        "base_availability_pct": 100.0, "location_bay": "Bay C", "status": "Operational",
        "skill_requirements": [
            {"skill": "Grinding",      "min_level": "Generic", "headcount": 1},
            {"skill": "Quality Check", "min_level": "Generic", "headcount": 1},
        ],
    },
]

machine_map = {}
for m in machines_data:
    existing = db.query(Machine).filter(Machine.name == m["name"], Machine.tenant_id == TID).first()
    if existing:
        machine_map[m["name"]] = existing
        print(f"  [skip] {m['name']} already exists")
        continue

    machine = Machine(
        tenant_id=TID,
        name=m["name"], machine_type=m["machine_type"],
        base_availability_pct=m["base_availability_pct"],
        location_bay=m["location_bay"], status=m["status"],
    )
    db.add(machine)
    db.flush()

    for req in m["skill_requirements"]:
        skill_obj = skill_map.get(req["skill"])
        if skill_obj:
            db.add(MachineSkillRequirement(
                tenant_id=TID, machine_id=machine.id, skill_id=skill_obj.id,
                min_skill_level=req["min_level"], employees_required=req["headcount"],
            ))

    machine_map[m["name"]] = machine
    print(f"  [+] {m['name']} ({m['location_bay']})")

db.commit()
print(f"  Done — {len(machine_map)} machines ready.\n")


# ===========================================================================
# 4. JOBS
# ===========================================================================
print("Seeding jobs...")

jobs_data = [
    {
        "name": "Batch CNC Shaft Machining", "customer": "Tata Motors",
        "description": "Machine 200 drive shafts to spec on CNC Lathe #1",
        "start_date": date(2026, 3, 10), "end_date": date(2026, 3, 20),
        "hours_per_day": 8.0, "profit": 85000.0, "priority": "High", "status": "Pending Assignment",
        "skill_requirements": [
            {"skill": "CNC Operation", "min_level": "Intermediate", "headcount": 2},
            {"skill": "Quality Check", "min_level": "Generic",      "headcount": 1},
        ],
    },
    {
        "name": "Structural Welding — Frame Assembly", "customer": "L&T Construction",
        "description": "Weld steel frames for prefab site structures",
        "start_date": date(2026, 3, 12), "end_date": date(2026, 3, 25),
        "hours_per_day": 8.0, "profit": 120000.0, "priority": "Critical", "status": "Pending Assignment",
        "skill_requirements": [
            {"skill": "Welding",  "min_level": "Intermediate", "headcount": 2},
            {"skill": "Assembly", "min_level": "Generic",      "headcount": 2},
            {"skill": "Helper",   "min_level": "Generic",      "headcount": 1},
        ],
    },
    {
        "name": "Precision Grinding — Bearing Housings", "customer": "SKF India",
        "description": "Grind bearing housings to tolerance Ra 0.8",
        "start_date": date(2026, 3, 18), "end_date": date(2026, 3, 28),
        "hours_per_day": 7.0, "profit": 65000.0, "priority": "Medium", "status": "Draft",
        "skill_requirements": [
            {"skill": "Grinding",      "min_level": "Intermediate", "headcount": 1},
            {"skill": "Quality Check", "min_level": "Intermediate", "headcount": 1},
        ],
    },
    {
        "name": "Assembly Line — Gearbox Units", "customer": "Mahindra & Mahindra",
        "description": "Assemble and inspect 50 gearbox units per day",
        "start_date": date(2026, 4, 1), "end_date": date(2026, 4, 15),
        "hours_per_day": 8.0, "profit": 200000.0, "priority": "Critical", "status": "Draft",
        "skill_requirements": [
            {"skill": "Assembly",      "min_level": "Intermediate", "headcount": 3},
            {"skill": "Quality Check", "min_level": "Generic",      "headcount": 1},
            {"skill": "Assistant1",    "min_level": "Generic",      "headcount": 1},
        ],
    },
    {
        "name": "Routine Maintenance Support", "customer": "Internal",
        "description": "Scheduled preventive maintenance on shop floor equipment",
        "start_date": date(2026, 4, 5), "end_date": date(2026, 4, 7),
        "hours_per_day": 4.0, "profit": 0.0, "priority": "Low", "status": "Scheduled",
        "skill_requirements": [
            {"skill": "Helper",     "min_level": "Generic", "headcount": 2},
            {"skill": "Assistant1", "min_level": "Generic", "headcount": 1},
        ],
    },
]

for j in jobs_data:
    existing = db.query(Job).filter(Job.name == j["name"], Job.tenant_id == TID).first()
    if existing:
        print(f"  [skip] {j['name']} already exists")
        continue

    job = Job(
        tenant_id=TID,
        name=j["name"], customer=j["customer"], description=j["description"],
        start_date=j["start_date"], end_date=j["end_date"],
        estimated_hours_per_day=j["hours_per_day"], tentative_profit=j["profit"],
        priority=j["priority"], status=j["status"],
        timer_status="idle", paused_seconds=0, timer_log=[],
    )
    db.add(job)
    db.flush()

    for req in j["skill_requirements"]:
        skill_obj = skill_map.get(req["skill"])
        if skill_obj:
            db.add(JobSkillRequirement(
                tenant_id=TID, job_id=job.id, skill_id=skill_obj.id,
                min_skill_level=req["min_level"], employees_required=req["headcount"],
            ))

    print(f"  [+] {j['name']} ({j['priority']}, ₹{j['profit']:,.0f})")

db.commit()
print(f"  Done — {len(jobs_data)} jobs ready.\n")


# ===========================================================================
# Summary
# ===========================================================================
print("========================================")
print("  Seed Complete!")
print("========================================")
print(f"  Skills    : {db.query(Skill).filter(Skill.tenant_id == TID).count()}")
print(f"  Employees : {db.query(Employee).filter(Employee.tenant_id == TID).count()}")
print(f"  Machines  : {db.query(Machine).filter(Machine.tenant_id == TID).count()}")
print(f"  Jobs      : {db.query(Job).filter(Job.tenant_id == TID).count()}")
print("========================================\n")

db.close()
