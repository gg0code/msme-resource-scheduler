"""
```python
"""
backend/scripts/seed_v2.py — Database Seeding Script for MSME Resource Scheduler
=================================================================================

FILE PURPOSE
This is a standalone Python script that populates the PostgreSQL database with realistic 
Indian manufacturing test data for development and demo purposes. Introduced in v4-dev to 
replace earlier seeding scripts with more comprehensive data including skills, employees, 
machines, and fully-loaded jobs with assignments and raw materials. It sits outside the 
main application architecture as a utility script run from the command line.

WHAT THIS FILE DOES — step by step
1. Sets up command-line argument parsing for --wipe and --tenant-id options
2. Configures Python path to import from the main app directory
3. Imports all necessary SQLAlchemy models and database session
4. Defines seed data arrays for skills, employees, machines, and jobs with realistic Indian manufacturing scenarios
5. Opens database session and finds target tenant (first tenant or specified --tenant-id)
6. Optionally wipes existing data if --wipe flag is provided
7. Seeds skills table with 20 manufacturing skills across machining, fabrication, quality, etc.
8. Seeds employees table with 10 workers including hourly rates, overtime rates, and skill associations
9. Seeds machines table with 10 pieces of equipment including CNC lathes, welders, presses, etc.
10. Seeds jobs table with 8 realistic manufacturing jobs including customer info, assignments, skill requirements, and raw materials
11. Commits all changes and closes database session

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : seed_skills
Type         : function
Purpose      : Creates Skill records from SKILLS_DATA array, skipping existing skills by name to maintain idempotency. Associates each skill with the target tenant.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant to associate skills with
Returns      : dict mapping skill names to Skill model instances for later reference
Calls        : SQLAlchemy Session.query(), Session.add(), Session.flush()
DB/API       : Queries skills table filtered by tenant_id and name, inserts new Skill records
Side effects : Creates new rows in skills table, prints progress messages to console

Name         : seed_employees  
Type         : function
Purpose      : Creates Employee records from EMPLOYEES_DATA array with associated EmployeeSkill junction records. Skips existing employees by name to maintain idempotency.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant to associate employees with, skills_map (dict) - mapping of skill names to Skill instances
Returns      : dict mapping employee names to Employee model instances for later job assignments
Calls        : SQLAlchemy Session.query(), Session.add(), Session.flush()
DB/API       : Queries employees table filtered by tenant_id and name, inserts Employee and EmployeeSkill records
Side effects : Creates new rows in employees and employee_skills tables, prints progress messages

Name         : seed_machines
Type         : function  
Purpose      : Creates Machine records from MACHINES_DATA array with associated MachineSkillRequirement records. Each machine specifies required skills, proficiency levels, and operator counts.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant to associate machines with, skills_map (dict) - mapping of skill names to Skill instances
Returns      : dict mapping machine names to Machine model instances for later job assignments
Calls        : SQLAlchemy Session.query(), Session.add(), Session.flush()
DB/API       : Queries machines table filtered by tenant_id and name, inserts Machine and MachineSkillRequirement records
Side effects : Creates new rows in machines and machine_skill_requirements tables, prints progress messages

Name         : seed_jobs
Type         : function
Purpose      : Creates Job records from JOBS_DATA array with full job assignments, skill requirements, and raw materials. Each job includes customer info, timeline, costs, and resource allocations representing realistic Indian manufacturing scenarios.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant to associate jobs with, employees_map (dict) - employee name to instance mapping, machines_map (dict) - machine name to instance mapping, skills_map (dict) - skill name to instance mapping
Returns      : None
Calls        : SQLAlchemy Session.query(), Session.add(), Session.flush()
DB/API       : Queries jobs table filtered by tenant_id and name, inserts Job, JobAssignment, and JobSkillRequirement records
Side effects : Creates new rows in jobs, job_assignments, and job_skill_requirements tables with raw_materials JSON data

Name         : wipe_tenant_data
Type         : function
Purpose      : Deletes all seeded data for a specific tenant in reverse dependency order to avoid foreign key constraint violations. Used when --wipe flag is provided.
Parameters   : db (Session) - SQLAlchemy database session, tenant_id (int) - tenant whose data should be deleted
Returns      : None  
Calls        : SQLAlchemy Session.query(), Session.delete()
DB/API       : Deletes from job_assignments, job_skill_requirements, jobs, machine_skill_requirements, machines, employee_skills, employees, skills tables filtered by tenant_id
Side effects : Permanently removes all seeded data for the specified tenant, prints deletion counts

Name         : main
Type         : function
Purpose      : Entry point that orchestrates the entire seeding process. Handles command-line arguments, database session management, and calls all seeding functions in correct order.
Parameters   : None (uses global args from argparse)
Returns      : None
Calls        : SessionLocal(), seed_skills(), seed_employees(), seed_machines(), seed_jobs(), wipe_tenant_data()
DB/API       : Opens and commits database transaction, queries tenants table to find target tenant
Side effects : Modifies database with test data, prints success/error messages, exits with status code

WHO CALLS THIS FILE
This script is executed directly from the command line and is not imported by other files in the codebase. Developers and deployment scripts run it manually using:
- backend/scripts/seed_v2.py (normal seeding)
- backend/scripts/seed_v2.py --wipe (wipe and re-seed)
- backend/scripts/seed_v2.py --tenant-id 2 (seed specific tenant)

IMPORTS EXPLAINED
sys, os - Standard library modules for path manipulation to import from parent app directory
argparse - Standard library for parsing --wipe and --tenant-id command-line flags  
datetime.date, timedelta - Standard library for generating realistic job start/end dates relative to today
app.database.SessionLocal - Database session factory for connecting to PostgreSQL
app.models.auth.User, Tenant - SQLAlchemy models for user authentication and tenant isolation
app.models.skill.Skill - SQLAlchemy model for manufacturing skills catalog
app.models.employee.Employee, EmployeeSkill - SQLAlchemy models for worker records and their skill associations
app.models.machine.Machine, MachineSkillRequirement - SQLAlchemy models for equipment and required operator skills
app.models.job.Job, JobSkillRequirement, JobAssignment - SQLAlchemy models for manufacturing jobs and their resource allocations

INTERN NOTES
• Easiest thing to break: Running without existing tenant records will crash - always ensure at least one tenant exists in database before seeding
• Non-obvious design decision: All seed data uses realistic Indian company names, INR pricing, and manufacturing scenarios to match the target market rather than generic placeholder data
• Most common mistake when editing: Adding new jobs without checking that referenced employee/machine names exist in EMPLOYEES_DATA and MACHINES_DATA arrays
• Design principle implemented
"""

import sys
import os
import argparse
from datetime import date, timedelta

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.auth import User, Tenant
from app.models.skill import Skill
from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine, MachineSkillRequirement
from app.models.job import Job, JobSkillRequirement, JobAssignment

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--wipe", action="store_true",
                    help="Delete all seeded data for the target tenant before re-seeding")
parser.add_argument("--tenant-id", type=int, default=None,
                    help="Tenant ID to seed (defaults to first tenant found)")
args = parser.parse_args()

# ── Seed data ─────────────────────────────────────────────────────────────────

# (name, category)
SKILLS_DATA = [
    ("CNC Operation",        "Machining"),
    ("Welding",              "Fabrication"),
    ("Lathe Operation",      "Machining"),
    ("Milling",              "Machining"),
    ("Quality Inspection",   "Quality"),
    ("Assembly",             "Assembly"),
    ("Hydraulics",           "Maintenance"),
    ("Electrical Wiring",    "Electrical"),
    ("PLC Programming",      "Electrical"),
    ("CAD/CAM",              "Engineering"),
    ("Forging",              "Fabrication"),
    ("Sheet Metal",          "Fabrication"),
    ("Painting & Finishing", "Finishing"),
    ("Heat Treatment",       "Fabrication"),
    ("Tool & Die Making",    "Machining"),
    ("Grinding",             "Machining"),
    ("Press Operation",      "Fabrication"),
    ("Casting",              "Fabrication"),
    ("Material Handling",    "General"),
    ("Maintenance",          "Maintenance"),
]

EMPLOYEES_DATA = [
    # (name, dept, employment_type, availability_pct, hourly_rate, overtime_rate, skills)
    ("Ravi Kumar",      "Machining",    "Full-time",  100, 180, 270, ["CNC Operation", "Lathe Operation", "Milling"]),
    ("Suresh Patil",    "Fabrication",  "Full-time",  100, 160, 240, ["Welding", "Sheet Metal", "Grinding"]),
    ("Anil Sharma",     "Quality",      "Full-time",  100, 150, 225, ["Quality Inspection", "Assembly"]),
    ("Dinesh Yadav",    "Maintenance",  "Full-time",   80, 140, 210, ["Hydraulics", "Maintenance", "Electrical Wiring"]),
    ("Priya Desai",     "Engineering",  "Full-time",  100, 200, 300, ["CAD/CAM", "PLC Programming", "CNC Operation"]),
    ("Mahesh Gaikwad",  "Fabrication",  "Full-time",  100, 155, 232, ["Forging", "Heat Treatment", "Welding"]),
    ("Sanjay More",     "Machining",    "Full-time",   90, 165, 248, ["Lathe Operation", "Grinding", "Tool & Die Making"]),
    ("Kavita Jadhav",   "Assembly",     "Part-time",   60, 120, 180, ["Assembly", "Painting & Finishing"]),
    ("Rajesh Nair",     "Production",   "Full-time",  100, 145, 218, ["Press Operation", "Sheet Metal", "Material Handling"]),
    ("Amit Tiwari",     "Engineering",  "Contract",    80, 175, 262, ["PLC Programming", "Electrical Wiring", "CAD/CAM"]),
]

MACHINES_DATA = [
    # (name, type, bay, availability_pct, hourly_rate, skill_requirements)
    # skill_requirements: list of (skill_name, level, operators_required)
    ("CNC Lathe #1",        "CNC Lathe",        "Bay A", 100, 350, [("CNC Operation",    "Intermediate", 1)]),
    ("CNC Milling Center",  "CNC Milling",      "Bay A", 100, 400, [("Milling",           "Intermediate", 1), ("CAD/CAM", "Generic", 1)]),
    ("MIG Welder #1",       "Welding",          "Bay B",  90, 150, [("Welding",           "Generic",      1)]),
    ("Hydraulic Press 80T", "Press",            "Bay C", 100, 280, [("Press Operation",   "Intermediate", 2)]),
    ("Surface Grinder",     "Grinding",         "Bay A",  80, 200, [("Grinding",          "Generic",      1)]),
    ("Heat Treatment Oven", "Heat Treatment",   "Bay D", 100, 450, [("Heat Treatment",    "Intermediate", 1)]),
    ("Sheet Metal Shear",   "Sheet Metal",      "Bay B", 100, 180, [("Sheet Metal",       "Generic",      1)]),
    ("Forging Hammer 2T",   "Forging",          "Bay D",  70, 500, [("Forging",           "Premium",      2)]),
    ("CMM Machine",         "Inspection",       "Bay E", 100, 300, [("Quality Inspection","Intermediate", 1)]),
    ("CNC Lathe #2",        "CNC Lathe",        "Bay A",  90, 350, [("CNC Operation",     "Generic",      1)]),
]

# 20 raw materials catalog: (name, unit, unit_cost_inr)
RAW_MATERIALS_CATALOG = [
    ("EN8 Steel Rod 40mm",      "kg",  85),
    ("MS Flat Bar 50x10",       "kg",  72),
    ("SS 304 Sheet 2mm",        "kg", 210),
    ("Aluminium Billet 6061",   "kg", 280),
    ("Cast Iron Blank",         "kg",  65),
    ("Mild Steel Plate 12mm",   "kg",  78),
    ("Brass Rod 25mm",          "kg", 520),
    ("Copper Tube 1 inch",      "mtr", 380),
    ("Nylon Block PA66",        "kg", 320),
    ("Carbide Insert TNMG",     "pcs", 450),
    ("Welding Wire ER70S-6",    "kg", 185),
    ("Cutting Fluid (5L)",      "ltr",  95),
    ("Grinding Wheel 200mm",    "pcs", 320),
    ("Drill Bit Set HSS",       "set", 850),
    ("O-Ring Kit Nitrile",      "set", 240),
    ("Epoxy Primer (1L)",       "ltr", 380),
    ("Hex Bolt M12x50 (100pc)", "box", 420),
    ("Bearing 6205 ZZ",         "pcs", 380),
    ("V-Belt A-42",             "pcs", 280),
    ("Paint RAL 7035 (4L)",     "ltr", 620),
]

# 8 jobs: realistic Indian auto/engineering component jobs
today = date.today()

JOBS_DATA = [
    {
        "name":           "Crankshaft Machining Batch",
        "customer":       "Tata Motors Vendor",
        "description":    "Precision machining of 50 crankshafts to drawing spec",
        "start_date":     today - timedelta(days=3),
        "end_date":       today + timedelta(days=7),
        "estimated_hours_per_day": 8.0,
        "order_value":    185000,
        "misc_cost":      4500,
        "priority":       "High",
        "status":         "In Progress",
        "employees":      ["Ravi Kumar", "Priya Desai"],
        "machines":       ["CNC Lathe #1", "CNC Milling Center"],
        "skills":         [("CNC Operation", "Intermediate", 2)],
        "raw_materials":  [
            ("EN8 Steel Rod 40mm", 120, 85),
            ("Carbide Insert TNMG", 20, 450),
            ("Cutting Fluid (5L)", 4, 95),
        ],
    },
    {
        "name":           "Hydraulic Cylinder Fabrication",
        "customer":       "Ace Hydraulics Pvt Ltd",
        "description":    "Fabricate 25 hydraulic cylinders — body welding & boring",
        "start_date":     today + timedelta(days=1),
        "end_date":       today + timedelta(days=12),
        "estimated_hours_per_day": 7.0,
        "order_value":    220000,
        "misc_cost":      6000,
        "priority":       "High",
        "status":         "Scheduled",
        "employees":      ["Suresh Patil", "Dinesh Yadav"],
        "machines":       ["MIG Welder #1", "Hydraulic Press 80T"],
        "skills":         [("Welding", "Generic", 1), ("Hydraulics", "Generic", 1)],
        "raw_materials":  [
            ("MS Flat Bar 50x10",    80,  72),
            ("Mild Steel Plate 12mm", 60, 78),
            ("Welding Wire ER70S-6", 15, 185),
            ("O-Ring Kit Nitrile",   25, 240),
        ],
    },
    {
        "name":           "Gear Housing Casting Finish",
        "customer":       "Kirloskar Electric",
        "description":    "Finishing & inspection of 40 gear housings post-casting",
        "start_date":     today + timedelta(days=5),
        "end_date":       today + timedelta(days=18),
        "estimated_hours_per_day": 8.0,
        "order_value":    160000,
        "misc_cost":      3200,
        "priority":       "Medium",
        "status":         "Scheduled",
        "employees":      ["Sanjay More", "Anil Sharma"],
        "machines":       ["Surface Grinder", "CMM Machine"],
        "skills":         [("Grinding", "Generic", 1), ("Quality Inspection", "Intermediate", 1)],
        "raw_materials":  [
            ("Cast Iron Blank",      40, 65),
            ("Grinding Wheel 200mm",  6, 320),
            ("Cutting Fluid (5L)",    2,  95),
            ("Epoxy Primer (1L)",     8, 380),
        ],
    },
    {
        "name":           "SS Panel Fabrication",
        "customer":       "Pharma Equipment Co",
        "description":    "SS 304 control panel enclosures — 15 units",
        "start_date":     today + timedelta(days=3),
        "end_date":       today + timedelta(days=14),
        "estimated_hours_per_day": 6.0,
        "order_value":    130000,
        "misc_cost":      2800,
        "priority":       "Medium",
        "status":         "Scheduled",
        "employees":      ["Rajesh Nair", "Kavita Jadhav"],
        "machines":       ["Sheet Metal Shear", "MIG Welder #1"],
        "skills":         [("Sheet Metal", "Generic", 1), ("Painting & Finishing", "Generic", 1)],
        "raw_materials":  [
            ("SS 304 Sheet 2mm",      45, 210),
            ("Hex Bolt M12x50 (100pc)", 3, 420),
            ("Paint RAL 7035 (4L)",    4, 620),
            ("Welding Wire ER70S-6",   5, 185),
        ],
    },
    {
        "name":           "Forged Flange Batch",
        "customer":       "Bharat Forge Subcontract",
        "description":    "Hot forging + heat treatment of 60 pipeline flanges",
        "start_date":     today + timedelta(days=8),
        "end_date":       today + timedelta(days=22),
        "estimated_hours_per_day": 8.0,
        "order_value":    275000,
        "misc_cost":      8500,
        "priority":       "Critical",
        "status":         "Draft",
        "employees":      ["Mahesh Gaikwad"],
        "machines":       ["Forging Hammer 2T", "Heat Treatment Oven"],
        "skills":         [("Forging", "Premium", 2), ("Heat Treatment", "Intermediate", 1)],
        "raw_materials":  [
            ("EN8 Steel Rod 40mm",  200, 85),
            ("Cutting Fluid (5L)",    3, 95),
            ("Grinding Wheel 200mm",  4, 320),
        ],
    },
    {
        "name":           "Aluminium Housing CNC",
        "customer":       "Bajaj Auto Components",
        "description":    "CNC milling of 30 aluminium gearbox housings",
        "start_date":     today + timedelta(days=10),
        "end_date":       today + timedelta(days=20),
        "estimated_hours_per_day": 8.0,
        "order_value":    198000,
        "misc_cost":      5000,
        "priority":       "High",
        "status":         "Draft",
        "employees":      ["Priya Desai", "Ravi Kumar"],
        "machines":       ["CNC Milling Center", "CNC Lathe #2"],
        "skills":         [("CNC Operation", "Intermediate", 1), ("CAD/CAM", "Generic", 1)],
        "raw_materials":  [
            ("Aluminium Billet 6061", 90, 280),
            ("Carbide Insert TNMG",   15, 450),
            ("Cutting Fluid (5L)",     3,  95),
            ("Drill Bit Set HSS",       2, 850),
        ],
    },
    {
        "name":           "Brass Valve Bodies",
        "customer":       "Nirmala Controls Pvt Ltd",
        "description":    "Turn & bore 80 brass valve bodies on lathe",
        "start_date":     today + timedelta(days=15),
        "end_date":       today + timedelta(days=25),
        "estimated_hours_per_day": 7.0,
        "order_value":    145000,
        "misc_cost":      3000,
        "priority":       "Low",
        "status":         "Draft",
        "employees":      ["Sanjay More"],
        "machines":       ["CNC Lathe #2"],
        "skills":         [("Lathe Operation", "Generic", 1)],
        "raw_materials":  [
            ("Brass Rod 25mm",    60, 520),
            ("Cutting Fluid (5L)", 2,  95),
            ("O-Ring Kit Nitrile", 80, 240),
            ("Bearing 6205 ZZ",   16, 380),
        ],
    },
    {
        "name":           "Electrical Panel Wiring",
        "customer":       "Siemens Sub-Vendor",
        "description":    "Wire & test 10 industrial electrical control panels",
        "start_date":     today + timedelta(days=12),
        "end_date":       today + timedelta(days=28),
        "estimated_hours_per_day": 6.0,
        "order_value":    320000,
        "misc_cost":      12000,
        "priority":       "Critical",
        "status":         "Draft",
        "employees":      ["Amit Tiwari", "Dinesh Yadav"],
        "machines":       [],   # bench work, no machine
        "skills":         [("Electrical Wiring", "Intermediate", 1), ("PLC Programming", "Intermediate", 1)],
        "raw_materials":  [
            ("Copper Tube 1 inch",      20, 380),
            ("Hex Bolt M12x50 (100pc)",  2, 420),
            ("O-Ring Kit Nitrile",       5, 240),
            ("Paint RAL 7035 (4L)",      2, 620),
            ("V-Belt A-42",             10, 280),
        ],
    },
]


# ─── Seeder ───────────────────────────────────────────────────────────────────

def wipe_tenant(db, tid: int):
    print(f"  🗑  Wiping existing data for tenant {tid}…")

    job_ids = [j.id for j in db.query(Job).filter(Job.tenant_id == tid).all()]
    if job_ids:
        db.query(JobAssignment).filter(JobAssignment.job_id.in_(job_ids)).delete(synchronize_session=False)
        db.query(JobSkillRequirement).filter(JobSkillRequirement.job_id.in_(job_ids)).delete(synchronize_session=False)
    db.query(Job).filter(Job.tenant_id == tid).delete(synchronize_session=False)

    mac_ids = [m.id for m in db.query(Machine).filter(Machine.tenant_id == tid).all()]
    if mac_ids:
        db.query(MachineSkillRequirement).filter(MachineSkillRequirement.machine_id.in_(mac_ids)).delete(synchronize_session=False)
    db.query(Machine).filter(Machine.tenant_id == tid).delete(synchronize_session=False)

    emp_ids = [e.id for e in db.query(Employee).filter(Employee.tenant_id == tid).all()]
    if emp_ids:
        db.query(EmployeeSkill).filter(EmployeeSkill.employee_id.in_(emp_ids)).delete(synchronize_session=False)
    db.query(Employee).filter(Employee.tenant_id == tid).delete(synchronize_session=False)

    db.query(Skill).filter(Skill.tenant_id == tid).delete(synchronize_session=False)
    db.commit()
    print("  ✅ Wipe complete")


def run():
    db = SessionLocal()
    try:
        # ── Find tenant ──────────────────────────────────────────────────────
        if args.tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == args.tenant_id).first()
        else:
            tenant = db.query(Tenant).first()
        if not tenant:
            print("❌ No tenant found. Register a user first, then re-run this script.")
            return
        tid = tenant.id
        print(f"\n🏭 Seeding tenant: {tenant.name!r} (id={tid})\n")

        if args.wipe:
            wipe_tenant(db, tid)

        # ── Skills ───────────────────────────────────────────────────────────
        print("📚 Skills…")
        skill_map: dict[str, int] = {}
        for (name, category) in SKILLS_DATA:
            existing = db.query(Skill).filter(Skill.tenant_id == tid, Skill.name == name).first()
            if existing:
                skill_map[name] = existing.id
            else:
                s = Skill(tenant_id=tid, name=name, category=category)
                db.add(s)
                db.flush()
                skill_map[name] = s.id
                print(f"   + {name}")
        db.commit()
        print(f"   ✅ {len(skill_map)} skills ready\n")

        # ── Employees ────────────────────────────────────────────────────────
        print("👷 Employees…")
        emp_map: dict[str, int] = {}
        for (name, dept, emp_type, avail, rate, ot_rate, skills) in EMPLOYEES_DATA:
            existing = db.query(Employee).filter(Employee.tenant_id == tid, Employee.full_name == name).first()
            if existing:
                emp_map[name] = existing.id
                print(f"   ~ {name} (already exists)")
                continue
            emp = Employee(
                tenant_id=tid, full_name=name, department=dept,
                employment_type=emp_type, base_availability_pct=avail,
                hourly_rate=rate, overtime_rate=ot_rate, status="Active",
            )
            db.add(emp)
            db.flush()
            for skill_name in skills:
                if skill_name in skill_map:
                    db.add(EmployeeSkill(
                        tenant_id=tid, employee_id=emp.id,
                        skill_id=skill_map[skill_name], skill_level="Intermediate",
                    ))
            emp_map[name] = emp.id
            print(f"   + {name} | ₹{rate}/hr | skills: {', '.join(skills)}")
        db.commit()
        print(f"   ✅ {len(emp_map)} employees ready\n")

        # ── Machines ─────────────────────────────────────────────────────────
        print("🏭 Machines…")
        mac_map: dict[str, int] = {}
        for (name, mtype, bay, avail, rate, skill_reqs) in MACHINES_DATA:
            existing = db.query(Machine).filter(Machine.tenant_id == tid, Machine.name == name).first()
            if existing:
                mac_map[name] = existing.id
                print(f"   ~ {name} (already exists)")
                continue
            mac = Machine(
                tenant_id=tid, name=name, machine_type=mtype,
                location_bay=bay, base_availability_pct=avail,
                hourly_rate=rate, status="Operational",
            )
            db.add(mac)
            db.flush()
            for (skill_name, level, ops_req) in skill_reqs:
                if skill_name in skill_map:
                    db.add(MachineSkillRequirement(
                        tenant_id=tid, machine_id=mac.id,
                        skill_id=skill_map[skill_name],
                        min_skill_level=level, employees_required=ops_req,
                    ))
            mac_map[name] = mac.id
            print(f"   + {name} | ₹{rate}/hr | bay: {bay}")
        db.commit()
        print(f"   ✅ {len(mac_map)} machines ready\n")

        # ── Jobs ─────────────────────────────────────────────────────────────
        print("📋 Jobs…")
        for jd in JOBS_DATA:
            existing = db.query(Job).filter(Job.tenant_id == tid, Job.name == jd["name"]).first()
            if existing:
                print(f"   ~ {jd['name']} (already exists)")
                continue

            # Build raw materials list with total cost
            raw_materials = []
            rm_total = 0.0
            for (rm_name, qty, unit_cost) in jd["raw_materials"]:
                total = qty * unit_cost
                rm_total += total
                raw_materials.append({
                    "name":       rm_name,
                    "quantity":   qty,
                    "unit_cost":  unit_cost,
                    "total_cost": total,
                })

            job = Job(
                tenant_id=tid,
                name=jd["name"],
                customer=jd["customer"],
                description=jd["description"],
                start_date=jd["start_date"],
                end_date=jd["end_date"],
                estimated_hours_per_day=jd["estimated_hours_per_day"],
                order_value=jd["order_value"],
                misc_cost=jd["misc_cost"],
                priority=jd["priority"],
                status=jd["status"],
                raw_materials=raw_materials,
                timer_status="idle",
                paused_seconds=0,
                timer_log=[],
            )
            db.add(job)
            db.flush()

            # Skill requirements
            for (skill_name, level, qty) in jd["skills"]:
                if skill_name in skill_map:
                    db.add(JobSkillRequirement(
                        tenant_id=tid, job_id=job.id, skill_id=skill_map[skill_name],
                        min_skill_level=level, employees_required=qty,
                    ))

            # Employee assignments
            for emp_name in jd["employees"]:
                if emp_name in emp_map:
                    db.add(JobAssignment(
                        tenant_id=tid, job_id=job.id,
                        employee_id=emp_map[emp_name], machine_id=None,
                    ))

            # Machine assignments
            for mac_name in jd["machines"]:
                if mac_name in mac_map:
                    db.add(JobAssignment(
                        tenant_id=tid, job_id=job.id,
                        employee_id=None, machine_id=mac_map[mac_name],
                    ))

            duration_days = (jd["end_date"] - jd["start_date"]).days + 1
            hours = duration_days * jd["estimated_hours_per_day"]
            emp_cost  = sum((EMPLOYEES_DATA[[e[0] for e in EMPLOYEES_DATA].index(n)][4] if n in [e[0] for e in EMPLOYEES_DATA] else 0) * hours
                            for n in jd["employees"])
            mac_cost  = sum((MACHINES_DATA[[m[0] for m in MACHINES_DATA].index(n)][4] if n in [m[0] for m in MACHINES_DATA] else 0) * hours
                            for n in jd["machines"])
            total_cost = emp_cost + mac_cost + rm_total + jd["misc_cost"]
            profit     = jd["order_value"] - total_cost

            print(f"   + {jd['name']}")
            print(f"     Customer: {jd['customer']} | Priority: {jd['priority']} | Status: {jd['status']}")
            print(f"     Dates: {jd['start_date']} → {jd['end_date']} ({duration_days}d × {jd['estimated_hours_per_day']}h)")
            print(f"     Raw materials: ₹{rm_total:,.0f} | Order: ₹{jd['order_value']:,.0f} | Est. Profit: ₹{profit:,.0f}")

        db.commit()
        print(f"\n   ✅ 8 jobs ready\n")

        # ── Summary ──────────────────────────────────────────────────────────
        total_order = sum(j["order_value"] for j in JOBS_DATA)
        print("═" * 55)
        print(f"  ✅ Seed complete for tenant: {tenant.name!r}")
        print(f"  Skills    : {len(SKILLS_DATA)}")
        print(f"  Employees : {len(EMPLOYEES_DATA)}")
        print(f"  Machines  : {len(MACHINES_DATA)}")
        print(f"  Jobs      : {len(JOBS_DATA)}")
        print(f"  Total order book : ₹{total_order:,.0f}")
        print("═" * 55)

    finally:
        db.close()


if __name__ == "__main__":
    run()
