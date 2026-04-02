"""
```python
"""
FILE PURPOSE
This is an interactive database seeding script specifically designed for the printing industry vertical of ZetaOps Copilot. It provides a safe way to reset tenant data and populate it with realistic printing business scenarios including flexo printing, offset printing, die cutting, and finishing operations. The script was introduced in v4-dev to help developers and testers quickly set up printing industry environments without manually creating dozens of employees, machines, jobs, and skills. It sits in the backend/scripts/ directory as a standalone utility that directly manipulates the database using SQLAlchemy models.

WHAT THIS FILE DOES — step by step
1. Parses command-line arguments to allow automated tenant wiping and custom tenant creation parameters
2. Connects to the PostgreSQL database using the same SessionLocal used by the main application
3. Lists all existing tenants in the database and prompts the user to select which tenant to wipe (unless --wipe flag is used)
4. Completely deletes all data for the selected tenant across all tables (jobs, employees, machines, skills, etc.)
5. Creates a new tenant with either provided credentials or prompts for tenant name, slug, owner email, and password
6. Seeds the new tenant with 15 printing industry skills including flexo printing, offset printing, die cutting, and various finishing operations
7. Creates 12 employees with realistic Indian names, departments, availability percentages, hourly rates, and skill assignments typical of printing businesses
8. Sets up 10 machines including different color flexo printers, Heidelberg offset presses, die cutters, and finishing equipment with their required skills
9. Generates 7 realistic printing jobs with detailed specifications, customer names, raw materials lists, and proper employee/machine assignments
10. Commits all changes to the database and provides confirmation of successful seeding

KEY FUNCTIONS / CLASSES / COMPONENTS
Name         : SKILLS_DATA
Type         : Global constant list
Purpose      : Defines the complete set of skills available in a printing business, organized by category (Printing, Cutting, Finishing, Pre-press, Binding, Quality, General). Each skill has a name and category to help organize the workflow capabilities of the printing operation.
Parameters   : N/A (constant data)
Returns      : List of tuples containing (skill_name, category)
Calls        : N/A (static data)
DB/API       : Used to populate the Skill table in the database
Side effects : None (read-only data structure)

Name         : EMPLOYEES_DATA
Type         : Global constant list
Purpose      : Contains realistic employee profiles for a printing business including Indian names, departments, employment types, availability percentages, base hourly rates, overtime rates, and skill sets. Designed to represent a typical small-to-medium printing operation's workforce structure.
Parameters   : N/A (constant data)
Returns      : List of tuples containing (name, department, employment_type, availability_pct, hourly_rate, overtime_rate, skills_list)
Calls        : N/A (static data)
DB/API       : Used to populate Employee and EmployeeSkill tables
Side effects : None (read-only data structure)

Name         : MACHINES_DATA
Type         : Global constant list
Purpose      : Defines printing machinery typical of a modern printing facility including single and multi-color flexo printers, Heidelberg offset presses, die cutters, and finishing equipment. Each machine has operational parameters, bay locations, availability percentages, hourly rates, and required skill levels for operation.
Parameters   : N/A (constant data)
Returns      : List of tuples containing (name, type, bay_location, availability_pct, hourly_rate, skills_requirements_list)
Calls        : N/A (static data)
DB/API       : Used to populate Machine and MachineSkillRequirement tables
Side effects : None (read-only data structure)

Name         : JOBS_DATA
Type         : Global constant list
Purpose      : Provides realistic printing job orders with complete specifications including customer details, job descriptions, timelines, financial information, resource assignments, and detailed raw materials lists. Jobs represent typical orders from food packaging, pharmaceuticals, electronics, and publishing industries.
Parameters   : N/A (constant data)
Returns      : List of dictionaries containing comprehensive job specifications including dates, costs, priorities, assigned resources, and materials
Calls        : N/A (static data)
DB/API       : Used to populate Job, JobSkillRequirement, and JobAssignment tables
Side effects : None (read-only data structure)

Name         : parser (argparse.ArgumentParser instance)
Type         : Command-line argument parser
Purpose      : Handles command-line arguments to allow automated execution of the script without interactive prompts. Supports specifying which tenant to wipe, seeding into existing tenants, and providing custom tenant creation parameters to streamline development and testing workflows.
Parameters   : --wipe (int): Tenant ID to wipe without prompting, --seed-tenant (int): Existing tenant ID to seed into, --name/--slug/--email/--password (str): New tenant creation parameters
Returns      : Namespace object with parsed command-line arguments
Calls        : Standard argparse module functionality
DB/API       : None (argument parsing only)
Side effects : Modifies global args variable with parsed command-line arguments

WHO CALLS THIS FILE
This script is executed directly from the command line and is not imported by other Python files. It's typically called by developers, testers, or during development environment setup using commands like "python scripts/reset_and_seed_printing.py" from the backend directory. The script may be referenced in documentation, setup guides, or automation scripts for development environment provisioning.

IMPORTS EXPLAINED
sys, os, argparse: Standard Python modules for system operations, file path manipulation, and command-line argument parsing needed for script execution and path management.
datetime.date, datetime.timedelta: Used to generate realistic job start and end dates relative to today's date, ensuring seeded jobs have proper scheduling timelines.
app.database.SessionLocal: The main database session factory used throughout the application, ensuring the script uses the same database connection configuration as the running application.
app.models.auth.Tenant, app.models.auth.User: SQLAlchemy ORM models for tenant and user management, needed to create the new tenant and owner user account.
app.models.skill.Skill: SQLAlchemy model for skill definitions that employees and machines can have, central to the scheduling engine's capability matching.
app.models.employee.Employee, app.models.employee.EmployeeSkill: Models for workforce management including employee profiles and their skill associations.
app.models.machine.Machine, app.models.machine.MachineSkillRequirement: Models for equipment management including machine definitions and their required operator skills.
app.models.job.Job, app.models.job.JobSkillRequirement, app.models.job.JobAssignment: Core scheduling models for job definitions, required skills, and resource assignments that the scheduling engine processes.

INTERN NOTES
- Easiest thing to break: Running this script against a production database will permanently delete tenant data with no recovery option, always verify database connection settings before execution
- Non-obvious design decision: The script creates jobs with start dates in the future (today + timedelta) to ensure they appear in the scheduling queue rather than as historical completed jobs
- Most common mistake: Forgetting to run from the backend/ directory will cause import failures since the script adds the parent directory to sys.path to import app modules
- This file implements design principle #2 (tenant scoping) by ensuring all created records include proper tenant_id foreign key relationships for data isolation
- If jobs don't appear in scheduling: Check that job start_date is in the future, status is "Scheduled", and all referenced employees/machines exist and have required skills
- This is v4-dev only: The script doesn't include WhatsApp-related models (PhoneTenantMap, WhatsAppConvers
"""

import sys, os, argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.auth import Tenant, User
from app.models.skill import Skill
from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine, MachineSkillRequirement
from app.models.job import Job, JobSkillRequirement, JobAssignment

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--wipe",        type=int,  default=None, help="Tenant ID to wipe (skips prompt)")
parser.add_argument("--seed-tenant", type=int,  default=None, help="Seed into this existing tenant ID (no new tenant created)")
parser.add_argument("--name",     default=None, help="New tenant name")
parser.add_argument("--slug",     default=None, help="New tenant slug")
parser.add_argument("--email",    default=None, help="Owner email for new tenant")
parser.add_argument("--password", default=None, help="Owner password for new tenant")
args = parser.parse_args()

today = date.today()

# ─────────────────────────────────────────────────────────────────────────────
#  PRINTING INDUSTRY DATA
# ─────────────────────────────────────────────────────────────────────────────
SKILLS_DATA = [
    ("Flexo Printing",       "Printing"),
    ("Offset Printing",      "Printing"),
    ("Die Cutting",          "Cutting"),
    ("Folder Gluing",        "Finishing"),
    ("Stitching / Stapling", "Finishing"),
    ("Lamination",           "Finishing"),
    ("Plate Making",         "Pre-press"),
    ("Barcode Printing",     "Printing"),
    ("Waterproof Coating",   "Finishing"),
    ("Book Binding",         "Binding"),
    ("Section Sewing",       "Binding"),
    ("Case Binding",         "Binding"),
    ("Perfect Binding",      "Binding"),
    ("Quality Control",      "Quality"),
    ("Machine Helper",       "General"),
]

EMPLOYEES_DATA = [
    # (name, dept, type, avail%, rate, ot_rate, [skills])
    ("Ramesh Kumar",  "Flexo Printing",  "Full-time", 100, 220, 330, ["Flexo Printing", "Plate Making"]),
    ("Suresh Patel",  "Flexo Printing",  "Full-time", 100, 250, 375, ["Flexo Printing", "Plate Making", "Barcode Printing"]),
    ("Harish Nair",   "Offset Printing", "Full-time", 100, 300, 450, ["Offset Printing", "Plate Making", "Lamination"]),
    ("Mahesh Rao",    "Flexo Printing",  "Full-time", 100, 220, 330, ["Flexo Printing", "Waterproof Coating"]),
    ("Prakash Singh", "Flexo Printing",  "Full-time", 100, 220, 330, ["Flexo Printing", "Barcode Printing", "Plate Making"]),
    ("Anil Desai",    "Flexo Printing",  "Full-time", 100, 200, 300, ["Flexo Printing", "Folder Gluing"]),
    ("Deepak Sharma", "Offset Printing", "Full-time", 100, 260, 390, ["Offset Printing", "Plate Making", "Book Binding"]),
    ("Vijay Menon",   "Offset Printing", "Full-time", 100, 240, 360, ["Offset Printing", "Case Binding"]),
    ("Ajay Thakur",   "Die Cutting",     "Full-time", 100, 180, 270, ["Die Cutting"]),
    ("Ravi Helper",   "Production",      "Full-time", 100, 120, 180, ["Machine Helper"]),
    ("Sita Bai",      "Production",      "Full-time", 100, 120, 180, ["Machine Helper", "Folder Gluing"]),
    ("Mohan Lal",     "Finishing",       "Full-time", 100, 150, 225, ["Lamination", "Quality Control"]),
]

MACHINES_DATA = [
    # (name, type, bay, avail%, rate, [(skill, level, ops)])
    ("1-Color Flexo Printer Slotter",   "Flexo Printer", "Bay A", 100,  480, [("Flexo Printing",  "Intermediate", 1)]),
    ("2-Color Flexo Printer Slotter",   "Flexo Printer", "Bay A", 100,  560, [("Flexo Printing",  "Intermediate", 1)]),
    ("3-Color Flexo Printer Slotter",   "Flexo Printer", "Bay B", 100,  640, [("Flexo Printing",  "Intermediate", 1)]),
    ("4-Color Flexo Printer Slotter",   "Flexo Printer", "Bay B", 100,  720, [("Flexo Printing",  "Intermediate", 1)]),
    ("Heidelberg 4-Color Offset Press", "Offset Press",  "Bay C", 100,  950, [("Offset Printing", "Premium",      1)]),
    ("Heidelberg 5-Color Offset Press", "Offset Press",  "Bay C", 100, 1100, [("Offset Printing", "Premium",      1)]),
    ("Rotary Die Cutter",               "Die Cutter",    "Bay D", 100,  380, [("Die Cutting",     "Intermediate", 1)]),
    ("Folder Gluer",                    "Folder Gluer",  "Bay D", 100,  320, [("Folder Gluing",   "Generic",      1)]),
    ("Automatic Laminator",             "Laminator",     "Bay E",  90,  420, [("Lamination",      "Intermediate", 1)]),
    ("Perfect Binder",                  "Binder",        "Bay E", 100,  350, [("Perfect Binding", "Intermediate", 1)]),
]

JOBS_DATA = [
    {
        "name":        "ABC Foods – Corrugated Cartons 50K",
        "customer":    "ABC Foods Pvt Ltd",
        "description": "50,000 corrugated cartons (450×300×300 mm), 5-ply board, 1-color flexo print",
        "start_date":  today + timedelta(days=2),  "end_date": today + timedelta(days=14),
        "hours_per_day": 8.0, "order_value": 820000,  "misc_cost": 8000,
        "priority": "High",     "status": "Scheduled",
        "employees": ["Ramesh Kumar", "Ravi Helper", "Sita Bai", "Ajay Thakur"],
        "machines":  ["1-Color Flexo Printer Slotter", "Rotary Die Cutter"],
        "skills":    [("Flexo Printing", "Intermediate", 1), ("Die Cutting", "Intermediate", 1)],
        "raw_materials": [
            ("5-ply Corrugated Sheets", "pcs", 50000, 28.0),
            ("Black Flexo Ink",         "kg",     18, 220.0),
            ("Printing Plates 1-color", "pcs",     2, 1200.0),
            ("Stitch Wire",             "kg",     15, 180.0),
            ("Starch Glue",             "kg",     50,  45.0),
        ],
    },
    {
        "name":        "Sunrise Biscuits – 4-Color Cartons 120K",
        "customer":    "Sunrise Biscuits Ltd",
        "description": "1,20,000 cartons (320×240×200 mm), 4-color flexo printing",
        "start_date":  today + timedelta(days=5),  "end_date": today + timedelta(days=22),
        "hours_per_day": 8.0, "order_value": 2500000, "misc_cost": 18000,
        "priority": "Critical", "status": "Scheduled",
        "employees": ["Suresh Patel", "Ravi Helper", "Sita Bai", "Mohan Lal", "Ajay Thakur"],
        "machines":  ["4-Color Flexo Printer Slotter", "Rotary Die Cutter", "Folder Gluer"],
        "skills":    [("Flexo Printing", "Intermediate", 1), ("Die Cutting", "Intermediate", 1), ("Folder Gluing", "Generic", 1)],
        "raw_materials": [
            ("3-ply Corrugated Sheets", "pcs", 120000, 18.0),
            ("CMYK Flexo Inks",         "kg",      45, 240.0),
            ("Printing Plates 4-color", "pcs",      8, 1200.0),
            ("Starch Glue",             "kg",     100,  45.0),
        ],
    },
    {
        "name":        "Omega Electronics – Laminated Boxes 20K",
        "customer":    "Omega Electronics",
        "description": "20,000 laminated corrugated boxes, 5-color offset printing (Heidelberg)",
        "start_date":  today + timedelta(days=8),  "end_date": today + timedelta(days=25),
        "hours_per_day": 8.0, "order_value": 1850000, "misc_cost": 15000,
        "priority": "High",     "status": "Scheduled",
        "employees": ["Harish Nair", "Ravi Helper", "Sita Bai", "Mohan Lal", "Ajay Thakur"],
        "machines":  ["Heidelberg 5-Color Offset Press", "Automatic Laminator", "Rotary Die Cutter"],
        "skills":    [("Offset Printing", "Premium", 1), ("Lamination", "Intermediate", 1), ("Die Cutting", "Intermediate", 1)],
        "raw_materials": [
            ("Corrugated Board Blanks", "pcs", 20000,  32.0),
            ("Art Paper Liner",         "pcs", 20000,  12.0),
            ("Offset Inks 5-color",     "kg",     22, 380.0),
            ("Lamination Glue",         "kg",     60,  95.0),
            ("Gloss Varnish",           "kg",     15, 320.0),
        ],
    },
    {
        "name":        "Coastal Seafood – Waterproof Export Cartons 60K",
        "customer":    "Coastal Seafood Exports",
        "description": "60,000 waterproof export cartons, 3-color flexo",
        "start_date":  today + timedelta(days=3),  "end_date": today + timedelta(days=18),
        "hours_per_day": 8.0, "order_value": 1400000, "misc_cost": 12000,
        "priority": "High",     "status": "Scheduled",
        "employees": ["Mahesh Rao", "Ravi Helper", "Sita Bai", "Ajay Thakur"],
        "machines":  ["3-Color Flexo Printer Slotter", "Rotary Die Cutter"],
        "skills":    [("Flexo Printing", "Intermediate", 1), ("Waterproof Coating", "Generic", 1), ("Die Cutting", "Intermediate", 1)],
        "raw_materials": [
            ("Waterproof 5-ply Sheets",     "pcs", 60000, 32.0),
            ("Flexo Inks 3-color",          "kg",     30, 230.0),
            ("Waterproof Coating Chemical", "kg",     40, 420.0),
            ("Printing Plates 3-color",     "pcs",     6, 1200.0),
        ],
    },
    {
        "name":        "MedCare Pharma – Barcode Cartons 80K",
        "customer":    "MedCare Pharma",
        "description": "80,000 pharma cartons with barcode printing (2 colors)",
        "start_date":  today + timedelta(days=1),  "end_date": today + timedelta(days=12),
        "hours_per_day": 8.0, "order_value": 1100000, "misc_cost": 9000,
        "priority": "Critical", "status": "Scheduled",
        "employees": ["Prakash Singh", "Ravi Helper", "Sita Bai", "Mohan Lal"],
        "machines":  ["2-Color Flexo Printer Slotter", "Rotary Die Cutter"],
        "skills":    [("Flexo Printing", "Intermediate", 1), ("Barcode Printing", "Generic", 1), ("Quality Control", "Generic", 1)],
        "raw_materials": [
            ("3-ply Board Sheets",       "pcs", 80000, 18.0),
            ("Flexo Inks 2-color",       "kg",     25, 230.0),
            ("Printing Plates 2-color",  "pcs",     4, 1200.0),
            ("Starch Glue",              "kg",     80,  45.0),
        ],
    },
    {
        "name":        "UrbanKart – Shipping Boxes 40K",
        "customer":    "UrbanKart E-commerce",
        "description": "40,000 shipping boxes, 2-color flexo",
        "start_date":  today + timedelta(days=6),  "end_date": today + timedelta(days=16),
        "hours_per_day": 8.0, "order_value": 620000,  "misc_cost": 5500,
        "priority": "Medium",   "status": "Scheduled",
        "employees": ["Anil Desai", "Ravi Helper", "Sita Bai"],
        "machines":  ["2-Color Flexo Printer Slotter", "Folder Gluer"],
        "skills":    [("Flexo Printing", "Intermediate", 1), ("Folder Gluing", "Generic", 1)],
        "raw_materials": [
            ("3-ply Corrugated Sheets", "pcs", 40000, 18.0),
            ("Flexo Inks 2-color",      "kg",     12, 230.0),
            ("Printing Plates 2-color", "pcs",     4, 1200.0),
            ("Starch Glue",             "kg",     40,  45.0),
        ],
    },
    {
        "name":        "Prakashan Publishers – Paperback Novels 10K",
        "customer":    "Prakashan Publishers",
        "description": "10,000 paperback novels (220 pages), 4-color offset cover",
        "start_date":  today + timedelta(days=10), "end_date": today + timedelta(days=28),
        "hours_per_day": 8.0, "order_value": 950000,  "misc_cost": 11000,
        "priority": "Medium",   "status": "Scheduled",
        "employees": ["Deepak Sharma", "Ravi Helper", "Sita Bai", "Mohan Lal"],
        "machines":  ["Heidelberg 4-Color Offset Press", "Folder Gluer", "Perfect Binder"],
        "skills":    [("Offset Printing", "Premium", 1), ("Perfect Binding", "Intermediate", 1)],
        "raw_materials": [
            ("70 GSM Book Paper",    "ton",   5.5, 58000.0),
            ("Cover Art Paper",      "pcs", 10000,    12.0),
            ("Offset Ink Black",     "kg",     22,   320.0),
            ("CMYK Cover Inks",      "kg",      8,   380.0),
            ("Perfect Binding Glue", "kg",     45,   180.0),
        ],
    },
    {
        "name":        "EduTech – Textbooks 4-Color 5K",
        "customer":    "EduTech Learning Pvt Ltd",
        "description": "5,000 textbooks, 4-color printing throughout",
        "start_date":  today + timedelta(days=12), "end_date": today + timedelta(days=35),
        "hours_per_day": 8.0, "order_value": 1250000, "misc_cost": 14000,
        "priority": "High",     "status": "Draft",
        "employees": ["Harish Nair", "Ravi Helper", "Sita Bai", "Mohan Lal"],
        "machines":  ["Heidelberg 5-Color Offset Press", "Folder Gluer", "Perfect Binder"],
        "skills":    [("Offset Printing", "Premium", 1), ("Section Sewing", "Intermediate", 1), ("Perfect Binding", "Intermediate", 1)],
        "raw_materials": [
            ("80 GSM Book Paper", "ton",  4.1, 62000.0),
            ("Offset Inks CMYK",  "kg",    25,   380.0),
            ("Lamination Film",   "pcs", 6000,     8.5),
        ],
    },
    {
        "name":        "Literary House – Hardcover Novels 3K",
        "customer":    "Literary House Publishing",
        "description": "3,000 hardcover novels with dust jacket",
        "start_date":  today + timedelta(days=15), "end_date": today + timedelta(days=38),
        "hours_per_day": 7.0, "order_value": 780000,  "misc_cost": 9500,
        "priority": "Medium",   "status": "Draft",
        "employees": ["Vijay Menon", "Ravi Helper", "Mohan Lal"],
        "machines":  ["Heidelberg 4-Color Offset Press", "Perfect Binder"],
        "skills":    [("Offset Printing", "Intermediate", 1), ("Case Binding", "Intermediate", 1)],
        "raw_materials": [
            ("Creamwove Paper",   "ton",  1.5, 55000.0),
            ("Hardboard Covers",  "pcs", 3000,    35.0),
            ("Dust Jacket Paper", "pcs", 3000,    18.0),
            ("Book Binding Ink",  "kg",     8,   320.0),
        ],
    },
    {
        "name":        "New Customer – Sample Run 1K",
        "customer":    "New Customer",
        "description": "Trial order — 1,000 custom printed boxes, 2-color. Awaiting final specs.",
        "start_date":  today + timedelta(days=20), "end_date": today + timedelta(days=26),
        "hours_per_day": 8.0, "order_value": 85000,   "misc_cost": 2000,
        "priority": "Low",      "status": "Draft",
        "employees": ["Anil Desai", "Ravi Helper"],
        "machines":  ["2-Color Flexo Printer Slotter"],
        "skills":    [("Flexo Printing", "Generic", 1)],
        "raw_materials": [
            ("3-ply Corrugated Sheets", "pcs", 1000, 18.0),
            ("Flexo Inks 2-color",      "kg",     3, 230.0),
            ("Printing Plates 2-color", "pcs",    2, 1200.0),
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def divider(char="═", width=62): print(char * width)

def show_tenants(db):
    tenants = db.query(Tenant).order_by(Tenant.id).all()
    divider()
    print(f"  {'ID':<5} {'Name':<28} {'Slug':<20} {'Plan':<8} Jobs   Emp  Mac")
    divider("─")
    for t in tenants:
        jobs = db.query(Job).filter(Job.tenant_id == t.id).count()
        emps = db.query(Employee).filter(Employee.tenant_id == t.id).count()
        macs = db.query(Machine).filter(Machine.tenant_id == t.id).count()
        users = db.query(User).filter(User.tenant_id == t.id).all()
        emails = ", ".join(u.email for u in users)
        print(f"  {t.id:<5} {t.name:<28} {t.slug:<20} {t.plan:<8} {jobs:<7}{emps:<5}{macs}")
        print(f"  {'':5} 👤 {emails}")
    divider()
    return tenants


def wipe_tenant(db, tid: int):
    print(f"\n  🗑  Wiping tenant {tid}…")
    job_ids = [j.id for j in db.query(Job).filter(Job.tenant_id == tid).all()]
    if job_ids:
        db.query(JobAssignment).filter(JobAssignment.job_id.in_(job_ids)).delete(synchronize_session=False)
        db.query(JobSkillRequirement).filter(JobSkillRequirement.job_id.in_(job_ids)).delete(synchronize_session=False)
    n_jobs = db.query(Job).filter(Job.tenant_id == tid).delete(synchronize_session=False)

    mac_ids = [m.id for m in db.query(Machine).filter(Machine.tenant_id == tid).all()]
    if mac_ids:
        db.query(MachineSkillRequirement).filter(MachineSkillRequirement.machine_id.in_(mac_ids)).delete(synchronize_session=False)
    n_mac = db.query(Machine).filter(Machine.tenant_id == tid).delete(synchronize_session=False)

    emp_ids = [e.id for e in db.query(Employee).filter(Employee.tenant_id == tid).all()]
    if emp_ids:
        db.query(EmployeeSkill).filter(EmployeeSkill.employee_id.in_(emp_ids)).delete(synchronize_session=False)
    n_emp = db.query(Employee).filter(Employee.tenant_id == tid).delete(synchronize_session=False)

    n_sk = db.query(Skill).filter(Skill.tenant_id == tid).delete(synchronize_session=False)
    db.commit()

    print(f"     ✅ Deleted: {n_jobs} jobs | {n_emp} employees | {n_mac} machines | {n_sk} skills")


def create_tenant(db, name, slug, email, password):
    import bcrypt

    # Ensure unique slug
    base_slug, i = slug, 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        slug = f"{base_slug}-{i}"; i += 1

    # Ensure unique email
    if db.query(User).filter(User.email == email).first():
        print(f"\n  ⚠️  Email {email!r} already in use. Choose a different email.")
        sys.exit(1)

    tenant = Tenant(name=name, slug=slug, plan="paid", is_active=True)
    db.add(tenant); db.flush()

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.add(User(tenant_id=tenant.id, email=email,
                hashed_password=hashed, role="proprietor", is_active=True))
    db.commit()

    print(f"\n  ✅ New tenant created!")
    print(f"     ID       : {tenant.id}")
    print(f"     Name     : {name}")
    print(f"     Email    : {email}")
    print(f"     Password : {password}")
    return tenant.id


def seed(db, tid):
    emp_rate = {e[0]: e[4] for e in EMPLOYEES_DATA}
    mac_rate = {m[0]: m[4] for m in MACHINES_DATA}

    # Skills
    print("\n📚 Skills…")
    skill_map = {}
    for name, cat in SKILLS_DATA:
        ex = db.query(Skill).filter(Skill.tenant_id == tid, Skill.name == name).first()
        skill_map[name] = ex.id if ex else None
        if not ex:
            s = Skill(tenant_id=tid, name=name, category=cat)
            db.add(s); db.flush()
            skill_map[name] = s.id
            print(f"   + {name}")
    db.commit()
    print(f"   ✅ {len(skill_map)} skills")

    # Employees
    print("\n👷 Employees…")
    emp_map = {}
    for name, dept, etype, avail, rate, ot, skills in EMPLOYEES_DATA:
        ex = db.query(Employee).filter(Employee.tenant_id == tid, Employee.full_name == name).first()
        if ex:
            emp_map[name] = ex.id; continue
        emp = Employee(tenant_id=tid, full_name=name, department=dept,
                       employment_type=etype, base_availability_pct=avail,
                       hourly_rate=rate, overtime_rate=ot, status="Active")
        db.add(emp); db.flush()
        for sk in skills:
            if skill_map.get(sk):
                db.add(EmployeeSkill(tenant_id=tid, employee_id=emp.id,
                                     skill_id=skill_map[sk], skill_level="Intermediate"))
        emp_map[name] = emp.id
        print(f"   + {name:<22}  ₹{rate}/hr  {dept}")
    db.commit()
    print(f"   ✅ {len(emp_map)} employees")

    # Machines
    print("\n🏭 Machines…")
    mac_map = {}
    for name, mtype, bay, avail, rate, skill_reqs in MACHINES_DATA:
        ex = db.query(Machine).filter(Machine.tenant_id == tid, Machine.name == name).first()
        if ex:
            mac_map[name] = ex.id; continue
        mac = Machine(tenant_id=tid, name=name, machine_type=mtype, location_bay=bay,
                      base_availability_pct=avail, hourly_rate=rate, status="Operational")
        db.add(mac); db.flush()
        for sk, level, ops in skill_reqs:
            if skill_map.get(sk):
                db.add(MachineSkillRequirement(tenant_id=tid, machine_id=mac.id,
                                               skill_id=skill_map[sk],
                                               min_skill_level=level, employees_required=ops))
        mac_map[name] = mac.id
        print(f"   + {name:<42}  ₹{rate}/hr  {bay}")
    db.commit()
    print(f"   ✅ {len(mac_map)} machines")

    # Jobs
    print("\n📋 Jobs…")
    n_created = 0
    for jd in JOBS_DATA:
        if db.query(Job).filter(Job.tenant_id == tid, Job.name == jd["name"]).first():
            print(f"   ~ {jd['name']} (exists)"); continue

        rms, rm_total = [], 0.0
        for rm_name, unit, qty, unit_cost in jd["raw_materials"]:
            tc = round(qty * unit_cost, 2); rm_total += tc
            rms.append({"name": rm_name, "unit": unit, "quantity": qty,
                        "unit_cost": unit_cost, "total_cost": tc})

        job = Job(tenant_id=tid, name=jd["name"], customer=jd["customer"],
                  description=jd["description"], start_date=jd["start_date"],
                  end_date=jd["end_date"], estimated_hours_per_day=jd["hours_per_day"],
                  order_value=jd["order_value"], misc_cost=jd["misc_cost"],
                  priority=jd["priority"], status=jd["status"],
                  raw_materials=rms, timer_status="idle", paused_seconds=0, timer_log=[])
        db.add(job); db.flush()

        for sk, level, qty in jd["skills"]:
            if skill_map.get(sk):
                db.add(JobSkillRequirement(tenant_id=tid, job_id=job.id,
                                           skill_id=skill_map[sk],
                                           min_skill_level=level, employees_required=qty))
        for n in jd["employees"]:
            if emp_map.get(n):
                db.add(JobAssignment(tenant_id=tid, job_id=job.id,
                                     employee_id=emp_map[n], machine_id=None))
        for n in jd["machines"]:
            if mac_map.get(n):
                db.add(JobAssignment(tenant_id=tid, job_id=job.id,
                                     employee_id=None, machine_id=mac_map[n]))

        dur = (jd["end_date"] - jd["start_date"]).days + 1
        hrs = dur * jd["hours_per_day"]
        emp_cost = sum(emp_rate.get(n, 0) * hrs for n in jd["employees"])
        mac_cost = sum(mac_rate.get(n, 0) * hrs for n in jd["machines"])
        profit   = jd["order_value"] - (emp_cost + mac_cost + rm_total + jd["misc_cost"])

        print(f"   + [{jd['priority']:<8}] {jd['name']}")
        print(f"            RM ₹{rm_total:>10,.0f}  Order ₹{jd['order_value']:>10,.0f}  Profit ₹{profit:>10,.0f}")
        n_created += 1
    db.commit()
    print(f"\n   ✅ {n_created} jobs created")
    return n_created


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run():
    db = SessionLocal()
    try:
        divider()
        print("  🖨️   MSME — Reset & Seed (Printing Industry)")
        divider()

        # ── Show all tenants ──────────────────────────────────────────────────
        print("\n  Current tenants in database:\n")
        tenants = show_tenants(db)

        if not tenants:
            print("\n  ⚠️  No tenants found. Register first, then re-run.\n")
            return

        # ── Which tenant to wipe? ─────────────────────────────────────────────
        if args.wipe is not None:
            wipe_id = args.wipe
        else:
            print("\n  Enter the Tenant ID to WIPE (all jobs/employees/machines/skills deleted).")
            print("  Type 0 to skip wipe and just create a new tenant.\n")
            while True:
                try:
                    wipe_id = int(input("  Wipe Tenant ID (or 0 to skip): ").strip())
                    break
                except ValueError:
                    print("  Please enter a number.")

        if wipe_id != 0:
            target = db.query(Tenant).filter(Tenant.id == wipe_id).first()
            if not target:
                print(f"\n  ❌ Tenant ID {wipe_id} not found.\n")
                return

            # Count what will be deleted
            n_jobs = db.query(Job).filter(Job.tenant_id == wipe_id).count()
            n_emps = db.query(Employee).filter(Employee.tenant_id == wipe_id).count()
            n_macs = db.query(Machine).filter(Machine.tenant_id == wipe_id).count()
            n_sks  = db.query(Skill).filter(Skill.tenant_id == wipe_id).count()
            users  = db.query(User).filter(User.tenant_id == wipe_id).all()

            print(f"\n  ⚠️  You are about to DELETE from tenant '{target.name}' (ID {wipe_id}):")
            print(f"     • {n_jobs} jobs")
            print(f"     • {n_emps} employees")
            print(f"     • {n_macs} machines")
            print(f"     • {n_sks} skills")
            print(f"     Users kept: {', '.join(u.email for u in users)}")
            print(f"\n  ⚠️  This CANNOT be undone!\n")

            confirm = input("  Type YES to confirm wipe: ").strip()
            if confirm != "YES":
                print("\n  Aborted — nothing deleted.\n")
                return

            wipe_tenant(db, wipe_id)

        # ── Get or create target tenant ───────────────────────────────────────
        if args.seed_tenant:
            target = db.query(Tenant).filter(Tenant.id == args.seed_tenant).first()
            if not target:
                print(f"\n  ❌ Tenant ID {args.seed_tenant} not found.\n")
                return
            tid = target.id
            name = target.name
            email = "(existing)"
            print(f"\n  📥 Seeding into existing tenant: '{target.name}' (ID {tid})\n")
        else:
            print("\n" + "─" * 62)
            print("  Create new tenant (press Enter to use defaults)\n")

            name     = args.name     or input("  Tenant name     [PrintMaster Industries]: ").strip() or "PrintMaster Industries"
            slug     = args.slug     or input("  Tenant slug     [printmaster]:            ").strip() or "printmaster"
            email    = args.email    or input("  Owner email     [owner@printmaster.com]:   ").strip() or "owner@printmaster.com"
            password = args.password or input("  Owner password  [print1234]:              ").strip() or "print1234"

            tid = create_tenant(db, name, slug, email, password)

        # ── Seed ─────────────────────────────────────────────────────────────
        print("\n" + "─" * 62)
        n_jobs = seed(db, tid)

        # ── Final summary ─────────────────────────────────────────────────────
        total_order = sum(j["order_value"] for j in JOBS_DATA)
        print()
        divider()
        print(f"  ✅  All done!")
        print(f"  Tenant     : {name}  (ID {tid})")
        print(f"  Skills     : {len(SKILLS_DATA)}")
        print(f"  Employees  : {len(EMPLOYEES_DATA)}")
        print(f"  Machines   : {len(MACHINES_DATA)}")
        print(f"  Jobs       : {n_jobs}")
        print(f"  Order book : ₹{total_order:,.0f}")
        print()
        print(f"  🔑 Login at http://localhost:3000")
        if not args.seed_tenant:
            print(f"     Email    : {email}")
            print(f"     Password : {password}")
        else:
            users = db.query(User).filter(User.tenant_id == tid).all()
            for u in users:
                print(f"     Email    : {u.email}  (existing login)")
        divider()

    finally:
        db.close()


if __name__ == "__main__":
    run()
