from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.models.skill import Skill
from app.models.employee import Employee, EmployeeSkill
from app.models.machine import Machine, MachineSkillRequirement
from app.models.job import Job, JobSkillRequirement, JobAssignment
from app.models.job_steps import JobStep


# --- Helper -------------------------------------------------------------------

def _today_plus(days: int) -> date:
    return date.today() + timedelta(days=days)


def _seed_skill(db: Session, tid: int, name: str, category: str, is_premium: bool) -> Skill:
    existing = db.query(Skill).filter(Skill.tenant_id == tid, Skill.name == name).first()
    if existing:
        return existing
    obj = Skill(tenant_id=tid, name=name, category=category, is_premium=is_premium,
                description=name, is_active=True)
    db.add(obj)
    db.flush()
    return obj


def _seed_employee(db: Session, tid: int, full_name: str, department: str,
                   employment_type: str, skills: list[tuple]) -> Employee:
    existing = db.query(Employee).filter(Employee.tenant_id == tid,
                                          Employee.full_name == full_name).first()
    if existing:
        return existing
    emp = Employee(tenant_id=tid, full_name=full_name, department=department,
                   employment_type=employment_type, base_availability_pct=100,
                   status="Active")
    db.add(emp)
    db.flush()
    for skill_obj, level in skills:
        db.add(EmployeeSkill(tenant_id=tid, employee_id=emp.id,
                              skill_id=skill_obj.id, skill_level=level))
    return emp


def _seed_machine(db: Session, tid: int, name: str, machine_type: str,
                  location_bay: str, skill_reqs: list[tuple]) -> Machine:
    existing = db.query(Machine).filter(Machine.tenant_id == tid,
                                         Machine.name == name).first()
    if existing:
        return existing
    m = Machine(tenant_id=tid, name=name, machine_type=machine_type,
                base_availability_pct=100, location_bay=location_bay,
                status="Operational")
    db.add(m)
    db.flush()
    for skill_obj, level, headcount in skill_reqs:
        db.add(MachineSkillRequirement(tenant_id=tid, machine_id=m.id,
                                        skill_id=skill_obj.id,
                                        min_skill_level=level,
                                        employees_required=headcount))
    return m


def _seed_job(db: Session, tid: int, name: str, customer: str,
              start_offset: int, end_offset: int, priority: str,
              status: str, profit: float, order_value: float,
              job_type: str, quantity: float,
              raw_materials: list[dict],
              skill_reqs: list[tuple],
              machines: list[Machine],
              employees: list[Employee],
              steps: list[dict]) -> Job:
    existing = db.query(Job).filter(Job.tenant_id == tid, Job.name == name).first()
    if existing:
        return existing
    job = Job(
        tenant_id=tid, name=name, customer=customer,
        start_date=_today_plus(start_offset),
        end_date=_today_plus(end_offset),
        estimated_hours_per_day=8.0,
        tentative_profit=profit, order_value=order_value,
        priority=priority, status=status,
        job_type=job_type, quantity=quantity,
        raw_materials=raw_materials,
        timer_status="idle", paused_seconds=0, timer_log=[],
    )
    db.add(job)
    db.flush()

    for skill_obj, level, headcount in skill_reqs:
        db.add(JobSkillRequirement(tenant_id=tid, job_id=job.id,
                                    skill_id=skill_obj.id,
                                    min_skill_level=level,
                                    employees_required=headcount))

    for machine in machines:
        db.add(JobAssignment(tenant_id=tid, job_id=job.id,
                              machine_id=machine.id, allocation_pct=100))

    for emp in employees:
        db.add(JobAssignment(tenant_id=tid, job_id=job.id,
                              employee_id=emp.id, allocation_pct=100))

    for i, step in enumerate(steps, 1):
        db.add(JobStep(
            tenant_id=tid, job_id=job.id,
            sequence_no=i, name=step["name"],
            step_type=step.get("type", "production"),
            duration_minutes=step["duration"],
            status="ready" if i == 1 else "locked",
        ))

    return job


# --- Industry seeders ---------------------------------------------------------

def _seed_printing(db: Session, tid: int):
    # Skills
    flexo    = _seed_skill(db, tid, "Flexo Printing",  "premium", True)
    die_cut  = _seed_skill(db, tid, "Die Cutting",     "premium", True)
    laminate = _seed_skill(db, tid, "Lamination",      "generic", False)
    qc       = _seed_skill(db, tid, "Quality Control", "generic", False)
    helper   = _seed_skill(db, tid, "Helper",          "generic", False)

    # Employees
    e1 = _seed_employee(db, tid, "Suresh Patel",   "Production", "Full-time",
                         [(flexo, "Premium"), (die_cut, "Intermediate")])
    e2 = _seed_employee(db, tid, "Mohan Lal",      "Production", "Full-time",
                         [(die_cut, "Premium"), (laminate, "Generic")])
    e3 = _seed_employee(db, tid, "Ramesh Kumar",   "Quality",    "Full-time",
                         [(qc, "Premium"), (flexo, "Generic")])
    e4 = _seed_employee(db, tid, "Ganesh Rao",     "Production", "Full-time",
                         [(laminate, "Intermediate"), (helper, "Generic")])
    e5 = _seed_employee(db, tid, "Priya Sharma",   "Quality",    "Full-time",
                         [(qc, "Intermediate"), (helper, "Generic")])
    e6 = _seed_employee(db, tid, "Anil Desai",     "Production", "Part-time",
                         [(helper, "Generic")])

    # Machines
    m1 = _seed_machine(db, tid, "2-Color Flexo Printer", "Flexo Printer", "Bay A",
                        [(flexo, "Intermediate", 1)])
    m2 = _seed_machine(db, tid, "Die Cutter #1",          "Die Cutter",    "Bay B",
                        [(die_cut, "Intermediate", 1)])
    m3 = _seed_machine(db, tid, "Laminator #1",           "Laminator",     "Bay C",
                        [(laminate, "Generic", 1)])

    # Jobs
    _seed_job(db, tid,
        name="Corrugated Box Run — EduTech",
        customer="EduTech Publishers",
        start_offset=2, end_offset=12,
        priority="High", status="Scheduled",
        profit=85000, order_value=180000,
        job_type="Corrugated Box", quantity=5000,
        raw_materials=[
            {"name": "Kraft Board", "quantity": 500, "unit": "kg",    "unit_cost": 80},
            {"name": "CMYK Ink",    "quantity": 20,  "unit": "litre", "unit_cost": 350},
            {"name": "Adhesive",    "quantity": 15,  "unit": "kg",    "unit_cost": 120},
        ],
        skill_reqs=[(flexo, "Intermediate", 1), (qc, "Generic", 1)],
        machines=[m1], employees=[e1, e3],
        steps=[
            {"name": "Pre-press setup",   "type": "setup",       "duration": 60},
            {"name": "Printing",          "type": "production",  "duration": 240},
            {"name": "Die cutting",       "type": "production",  "duration": 180},
            {"name": "Quality check",     "type": "inspection",  "duration": 60},
        ])

    _seed_job(db, tid,
        name="Mono Carton — Pharma Pack",
        customer="Cipla Ltd",
        start_offset=5, end_offset=18,
        priority="Critical", status="Pending Assignment",
        profit=120000, order_value=250000,
        job_type="Mono Carton", quantity=20000,
        raw_materials=[
            {"name": "SBS Board",  "quantity": 300, "unit": "kg",    "unit_cost": 95},
            {"name": "Varnish",    "quantity": 10,  "unit": "litre", "unit_cost": 500},
        ],
        skill_reqs=[(flexo, "Premium", 1), (die_cut, "Intermediate", 1)],
        machines=[m1, m2], employees=[e1, e2],
        steps=[
            {"name": "Plate making",     "type": "setup",      "duration": 90},
            {"name": "Printing",         "type": "production", "duration": 300},
            {"name": "Die cutting",      "type": "production", "duration": 200},
            {"name": "Lamination",       "type": "production", "duration": 120},
            {"name": "Final inspection", "type": "inspection", "duration": 90},
        ])

    _seed_job(db, tid,
        name="Label Print — FMCG Batch",
        customer="HUL",
        start_offset=15, end_offset=22,
        priority="Medium", status="Draft",
        profit=45000, order_value=90000,
        job_type="Label", quantity=50000,
        raw_materials=[
            {"name": "Label Stock", "quantity": 200, "unit": "kg",    "unit_cost": 60},
            {"name": "CMYK Ink",    "quantity": 8,   "unit": "litre", "unit_cost": 350},
        ],
        skill_reqs=[(flexo, "Intermediate", 1), (qc, "Generic", 1)],
        machines=[m1], employees=[e1, e5],
        steps=[
            {"name": "Setup",        "type": "setup",      "duration": 45},
            {"name": "Print run",    "type": "production", "duration": 180},
            {"name": "Inspection",   "type": "inspection", "duration": 60},
        ])


def _seed_manufacturing(db: Session, tid: int):
    cnc      = _seed_skill(db, tid, "CNC Operation",  "premium", True)
    welding  = _seed_skill(db, tid, "Welding",        "premium", True)
    assembly = _seed_skill(db, tid, "Assembly",       "generic", False)
    qc       = _seed_skill(db, tid, "Quality Check",  "generic", False)
    helper   = _seed_skill(db, tid, "Helper",         "generic", False)

    e1 = _seed_employee(db, tid, "Ramesh Sharma",  "Production", "Full-time",
                         [(cnc, "Premium"), (qc, "Generic")])
    e2 = _seed_employee(db, tid, "Suresh Patil",   "Production", "Full-time",
                         [(cnc, "Intermediate"), (assembly, "Generic")])
    e3 = _seed_employee(db, tid, "Mahesh Yadav",   "Production", "Full-time",
                         [(welding, "Premium"), (assembly, "Intermediate")])
    e4 = _seed_employee(db, tid, "Dinesh Kumar",   "Production", "Full-time",
                         [(welding, "Intermediate"), (helper, "Generic")])
    e5 = _seed_employee(db, tid, "Rajesh Verma",   "Quality",    "Full-time",
                         [(qc, "Premium"), (assembly, "Generic")])
    e6 = _seed_employee(db, tid, "Vikram Singh",   "Production", "Part-time",
                         [(assembly, "Intermediate"), (helper, "Generic")])

    m1 = _seed_machine(db, tid, "CNC Lathe #1",      "CNC Lathe",       "Bay A",
                        [(cnc, "Intermediate", 1)])
    m2 = _seed_machine(db, tid, "MIG Welder #1",     "Welding Station", "Bay B",
                        [(welding, "Generic", 1)])
    m3 = _seed_machine(db, tid, "Assembly Line #1",  "Assembly Line",   "Bay C",
                        [(assembly, "Generic", 2)])

    _seed_job(db, tid,
        name="Shaft Machining — Tata Motors",
        customer="Tata Motors",
        start_offset=2, end_offset=12,
        priority="High", status="Scheduled",
        profit=85000, order_value=180000,
        job_type="CNC Part", quantity=200,
        raw_materials=[
            {"name": "Steel Rod EN8", "quantity": 150, "unit": "kg",  "unit_cost": 95},
            {"name": "Cutting Oil",   "quantity": 10,  "unit": "litre","unit_cost": 80},
        ],
        skill_reqs=[(cnc, "Intermediate", 2), (qc, "Generic", 1)],
        machines=[m1], employees=[e1, e2, e5],
        steps=[
            {"name": "Material inspection", "type": "setup",      "duration": 30},
            {"name": "Rough machining",      "type": "production", "duration": 240},
            {"name": "Finish machining",     "type": "production", "duration": 180},
            {"name": "Dimensional check",    "type": "inspection", "duration": 60},
        ])

    _seed_job(db, tid,
        name="Frame Welding — L&T",
        customer="L&T Construction",
        start_offset=5, end_offset=18,
        priority="Critical", status="Pending Assignment",
        profit=120000, order_value=250000,
        job_type="Welded Assembly", quantity=50,
        raw_materials=[
            {"name": "MS Flat Bar", "quantity": 500, "unit": "kg",   "unit_cost": 75},
            {"name": "Welding Wire","quantity": 25,  "unit": "kg",   "unit_cost": 180},
        ],
        skill_reqs=[(welding, "Intermediate", 2), (assembly, "Generic", 2)],
        machines=[m2], employees=[e3, e4, e6],
        steps=[
            {"name": "Tack welding",  "type": "setup",      "duration": 60},
            {"name": "Full welding",  "type": "production", "duration": 300},
            {"name": "Grinding",      "type": "production", "duration": 120},
            {"name": "Inspection",    "type": "inspection", "duration": 60},
        ])

    _seed_job(db, tid,
        name="Gearbox Assembly — M&M",
        customer="Mahindra & Mahindra",
        start_offset=15, end_offset=28,
        priority="Medium", status="Draft",
        profit=200000, order_value=400000,
        job_type="Assembly", quantity=100,
        raw_materials=[
            {"name": "Gear Set",     "quantity": 100, "unit": "pcs", "unit_cost": 850},
            {"name": "Bearing Kit",  "quantity": 100, "unit": "pcs", "unit_cost": 320},
            {"name": "Gasket Set",   "quantity": 100, "unit": "pcs", "unit_cost": 95},
        ],
        skill_reqs=[(assembly, "Intermediate", 3), (qc, "Generic", 1)],
        machines=[m3], employees=[e2, e5, e6],
        steps=[
            {"name": "Sub-assembly",       "type": "production", "duration": 180},
            {"name": "Main assembly",      "type": "production", "duration": 240},
            {"name": "Leak test",          "type": "inspection", "duration": 60},
            {"name": "Final inspection",   "type": "inspection", "duration": 90},
        ])


def _seed_fabrication(db: Session, tid: int):
    fab     = _seed_skill(db, tid, "Fabrication",   "premium", True)
    weld    = _seed_skill(db, tid, "Welding",       "premium", True)
    grind   = _seed_skill(db, tid, "Grinding",      "generic", False)
    fit     = _seed_skill(db, tid, "Fitting",       "generic", False)
    helper  = _seed_skill(db, tid, "Helper",        "generic", False)

    e1 = _seed_employee(db, tid, "Raju Fabricator", "Fabrication", "Full-time",
                         [(fab, "Premium"), (weld, "Intermediate")])
    e2 = _seed_employee(db, tid, "Sanjay Welder",   "Fabrication", "Full-time",
                         [(weld, "Premium"), (grind, "Generic")])
    e3 = _seed_employee(db, tid, "Vijay Fitter",    "Fabrication", "Full-time",
                         [(fit, "Premium"), (fab, "Generic")])
    e4 = _seed_employee(db, tid, "Manoj Grinder",   "Fabrication", "Full-time",
                         [(grind, "Intermediate"), (helper, "Generic")])
    e5 = _seed_employee(db, tid, "Arun Helper",     "Fabrication", "Part-time",
                         [(helper, "Generic")])
    e6 = _seed_employee(db, tid, "Deepak Fitter",   "Fabrication", "Full-time",
                         [(fit, "Intermediate"), (grind, "Generic")])

    m1 = _seed_machine(db, tid, "Plasma Cutter #1", "Plasma Cutter", "Bay A",
                        [(fab, "Intermediate", 1)])
    m2 = _seed_machine(db, tid, "MIG Welder #1",    "MIG Welder",    "Bay B",
                        [(weld, "Generic", 1)])
    m3 = _seed_machine(db, tid, "Press Brake #1",   "Press Brake",   "Bay C",
                        [(fab, "Generic", 1)])

    _seed_job(db, tid,
        name="Steel Frame Fabrication — Site A",
        customer="Shapoorji Pallonji",
        start_offset=2, end_offset=14,
        priority="High", status="Scheduled",
        profit=95000, order_value=200000,
        job_type="Structural", quantity=20,
        raw_materials=[
            {"name": "MS Hollow Section", "quantity": 800, "unit": "kg",  "unit_cost": 72},
            {"name": "Welding Electrode", "quantity": 30,  "unit": "kg",  "unit_cost": 160},
            {"name": "Primer Paint",      "quantity": 15,  "unit": "litre","unit_cost": 220},
        ],
        skill_reqs=[(fab, "Intermediate", 1), (weld, "Intermediate", 2)],
        machines=[m1, m2], employees=[e1, e2, e3],
        steps=[
            {"name": "Marking & cutting", "type": "production", "duration": 180},
            {"name": "Fit-up",            "type": "production", "duration": 120},
            {"name": "Welding",           "type": "production", "duration": 240},
            {"name": "Grinding & finish", "type": "production", "duration": 90},
            {"name": "Painting",          "type": "production", "duration": 60},
        ])

    _seed_job(db, tid,
        name="Sheet Metal Enclosures — Batch",
        customer="Siemens India",
        start_offset=5, end_offset=16,
        priority="Critical", status="Pending Assignment",
        profit=75000, order_value=160000,
        job_type="Sheet Metal", quantity=50,
        raw_materials=[
            {"name": "CR Sheet 2mm", "quantity": 400, "unit": "kg",  "unit_cost": 88},
            {"name": "Zinc Primer",  "quantity": 8,   "unit": "litre","unit_cost": 280},
        ],
        skill_reqs=[(fab, "Premium", 1), (fit, "Intermediate", 1)],
        machines=[m3], employees=[e1, e3],
        steps=[
            {"name": "Blanking",    "type": "production", "duration": 120},
            {"name": "Bending",     "type": "production", "duration": 180},
            {"name": "Assembly",    "type": "production", "duration": 90},
            {"name": "Inspection",  "type": "inspection", "duration": 45},
        ])

    _seed_job(db, tid,
        name="Pipe Spool Fabrication",
        customer="ONGC",
        start_offset=12, end_offset=25,
        priority="Medium", status="Draft",
        profit=110000, order_value=230000,
        job_type="Pipe Work", quantity=30,
        raw_materials=[
            {"name": "CS Pipe 4 inch", "quantity": 600, "unit": "kg",  "unit_cost": 85},
            {"name": "Welding Wire",   "quantity": 20,  "unit": "kg",  "unit_cost": 180},
            {"name": "Flange Set",     "quantity": 30,  "unit": "pcs", "unit_cost": 450},
        ],
        skill_reqs=[(weld, "Premium", 2), (fit, "Intermediate", 1)],
        machines=[m2], employees=[e2, e3, e4],
        steps=[
            {"name": "Pipe cutting",  "type": "production", "duration": 90},
            {"name": "Fit-up",        "type": "production", "duration": 120},
            {"name": "Welding",       "type": "production", "duration": 300},
            {"name": "NDT check",     "type": "inspection", "duration": 90},
        ])


def _seed_chemical(db: Session, tid: int):
    process  = _seed_skill(db, tid, "Process Operation", "premium", True)
    quality  = _seed_skill(db, tid, "Quality Control",   "premium", True)
    filling  = _seed_skill(db, tid, "Filling Operation", "generic", False)
    safety   = _seed_skill(db, tid, "Safety Officer",    "generic", False)
    helper   = _seed_skill(db, tid, "Helper",            "generic", False)

    e1 = _seed_employee(db, tid, "Dr. Ravi Kumar",    "Process",  "Full-time",
                         [(process, "Premium"), (quality, "Intermediate")])
    e2 = _seed_employee(db, tid, "Anita Sharma",      "Process",  "Full-time",
                         [(process, "Intermediate"), (safety, "Generic")])
    e3 = _seed_employee(db, tid, "Vijay Chemist",     "Quality",  "Full-time",
                         [(quality, "Premium"), (process, "Generic")])
    e4 = _seed_employee(db, tid, "Rekha Filler",      "Filling",  "Full-time",
                         [(filling, "Intermediate"), (helper, "Generic")])
    e5 = _seed_employee(db, tid, "Sunil Safety",      "Safety",   "Full-time",
                         [(safety, "Premium"), (helper, "Generic")])
    e6 = _seed_employee(db, tid, "Meena Operator",    "Process",  "Part-time",
                         [(process, "Generic"), (helper, "Generic")])

    m1 = _seed_machine(db, tid, "Reactor R-101",     "Reactor",      "Block A",
                        [(process, "Intermediate", 1)])
    m2 = _seed_machine(db, tid, "Mixer Tank MT-1",   "Mixer",        "Block B",
                        [(process, "Generic", 1)])
    m3 = _seed_machine(db, tid, "Filling Line FL-1", "Filling Line", "Block C",
                        [(filling, "Generic", 1)])

    _seed_job(db, tid,
        name="Batch Mix A — Surfactant",
        customer="P&G India",
        start_offset=2, end_offset=8,
        priority="High", status="Scheduled",
        profit=95000, order_value=200000,
        job_type="Mixing", quantity=5000,
        raw_materials=[
            {"name": "Base Chemical",  "quantity": 2000, "unit": "kg",    "unit_cost": 45},
            {"name": "Surfactant",     "quantity": 500,  "unit": "kg",    "unit_cost": 120},
            {"name": "Preservative",   "quantity": 50,   "unit": "litre", "unit_cost": 380},
        ],
        skill_reqs=[(process, "Intermediate", 1), (quality, "Generic", 1)],
        machines=[m2], employees=[e1, e3],
        steps=[
            {"name": "Reactor prep",     "type": "setup",      "duration": 60},
            {"name": "Ingredient dosing","type": "production", "duration": 120},
            {"name": "Mixing & heating", "type": "production", "duration": 240},
            {"name": "Quality sampling", "type": "inspection", "duration": 60},
            {"name": "Transfer",         "type": "production", "duration": 45},
        ])

    _seed_job(db, tid,
        name="Reactor Run R-12 — Polymer",
        customer="Asian Paints",
        start_offset=5, end_offset=14,
        priority="Critical", status="Pending Assignment",
        profit=180000, order_value=380000,
        job_type="Reaction", quantity=8000,
        raw_materials=[
            {"name": "Monomer A",  "quantity": 3000, "unit": "kg",    "unit_cost": 85},
            {"name": "Catalyst",   "quantity": 30,   "unit": "kg",    "unit_cost": 2200},
            {"name": "Solvent",    "quantity": 800,  "unit": "litre", "unit_cost": 55},
        ],
        skill_reqs=[(process, "Premium", 1), (safety, "Generic", 1)],
        machines=[m1], employees=[e1, e2, e5],
        steps=[
            {"name": "Reactor cleaning",  "type": "setup",      "duration": 90},
            {"name": "Charge loading",    "type": "production", "duration": 60},
            {"name": "Reaction phase",    "type": "production", "duration": 480},
            {"name": "Sampling & test",   "type": "inspection", "duration": 120},
            {"name": "Discharge",         "type": "production", "duration": 60},
        ])

    _seed_job(db, tid,
        name="Filling Batch — Shampoo FL-55",
        customer="Marico",
        start_offset=10, end_offset=16,
        priority="Medium", status="Draft",
        profit=65000, order_value=140000,
        job_type="Filling", quantity=10000,
        raw_materials=[
            {"name": "Shampoo Bulk",  "quantity": 5000, "unit": "litre", "unit_cost": 22},
            {"name": "HDPE Bottle",   "quantity": 10000,"unit": "pcs",   "unit_cost": 4.5},
            {"name": "Label",         "quantity": 10000,"unit": "pcs",   "unit_cost": 0.8},
        ],
        skill_reqs=[(filling, "Intermediate", 2), (quality, "Generic", 1)],
        machines=[m3], employees=[e3, e4, e6],
        steps=[
            {"name": "Line setup",      "type": "setup",      "duration": 45},
            {"name": "Filling run",     "type": "production", "duration": 300},
            {"name": "Capping",         "type": "production", "duration": 120},
            {"name": "Labelling",       "type": "production", "duration": 120},
            {"name": "Final QC",        "type": "inspection", "duration": 60},
        ])


def _seed_field_service(db: Session, tid: int):
    hvac    = _seed_skill(db, tid, "HVAC",          "premium", True)
    elec    = _seed_skill(db, tid, "Electrical",    "premium", True)
    plumb   = _seed_skill(db, tid, "Plumbing",      "generic", False)
    civil   = _seed_skill(db, tid, "Civil Works",   "generic", False)
    helper  = _seed_skill(db, tid, "Helper",        "generic", False)

    e1 = _seed_employee(db, tid, "Ramesh HVAC",     "HVAC",       "Full-time",
                         [(hvac, "Premium"), (elec, "Generic")])
    e2 = _seed_employee(db, tid, "Suresh Electric", "Electrical", "Full-time",
                         [(elec, "Premium"), (helper, "Generic")])
    e3 = _seed_employee(db, tid, "Mahesh Plumber",  "Plumbing",   "Full-time",
                         [(plumb, "Premium"), (civil, "Generic")])
    e4 = _seed_employee(db, tid, "Dinesh Tech",     "HVAC",       "Full-time",
                         [(hvac, "Intermediate"), (elec, "Generic")])
    e5 = _seed_employee(db, tid, "Priya Civil",     "Civil",      "Full-time",
                         [(civil, "Intermediate"), (helper, "Generic")])
    e6 = _seed_employee(db, tid, "Anil Helper",     "General",    "Part-time",
                         [(helper, "Generic")])

    m1 = _seed_machine(db, tid, "Service Van #1",     "Van",            "Depot",
                        [(hvac, "Generic", 1)])
    m2 = _seed_machine(db, tid, "Hydraulic Lift #1",  "Hydraulic Lift", "Depot",
                        [(elec, "Generic", 1)])
    m3 = _seed_machine(db, tid, "Diagnostic Kit #1",  "Diagnostic Kit", "Depot",
                        [(elec, "Intermediate", 1)])

    _seed_job(db, tid,
        name="AC Maintenance — Infosys Campus",
        customer="Infosys Ltd",
        start_offset=1, end_offset=3,
        priority="High", status="Scheduled",
        profit=45000, order_value=95000,
        job_type="HVAC", quantity=20,
        raw_materials=[
            {"name": "Refrigerant R-32", "quantity": 10,  "unit": "kg",  "unit_cost": 450},
            {"name": "Filter Set",       "quantity": 20,  "unit": "pcs", "unit_cost": 180},
            {"name": "Copper Pipe",      "quantity": 50,  "unit": "m",   "unit_cost": 85},
        ],
        skill_reqs=[(hvac, "Intermediate", 2), (elec, "Generic", 1)],
        machines=[m1], employees=[e1, e4, e2],
        steps=[
            {"name": "Site survey",       "type": "setup",      "duration": 60},
            {"name": "Gas top-up",        "type": "production", "duration": 120},
            {"name": "Filter replacement","type": "production", "duration": 90},
            {"name": "Testing",           "type": "inspection", "duration": 45},
        ])

    _seed_job(db, tid,
        name="Generator Servicing — Hospital",
        customer="Apollo Hospitals",
        start_offset=3, end_offset=5,
        priority="Critical", status="Pending Assignment",
        profit=85000, order_value=175000,
        job_type="Generator", quantity=3,
        raw_materials=[
            {"name": "Engine Oil",    "quantity": 15,  "unit": "litre","unit_cost": 320},
            {"name": "Air Filter",    "quantity": 3,   "unit": "pcs",  "unit_cost": 850},
            {"name": "Battery",       "quantity": 3,   "unit": "pcs",  "unit_cost": 4500},
        ],
        skill_reqs=[(elec, "Premium", 1), (hvac, "Generic", 1)],
        machines=[m2, m3], employees=[e2, e1],
        steps=[
            {"name": "Initial check",   "type": "setup",      "duration": 30},
            {"name": "Oil change",      "type": "production", "duration": 60},
            {"name": "Filter service",  "type": "production", "duration": 45},
            {"name": "Load test",       "type": "inspection", "duration": 60},
        ])

    _seed_job(db, tid,
        name="Plumbing Overhaul — IT Park",
        customer="Embassy REIT",
        start_offset=7, end_offset=14,
        priority="Medium", status="Draft",
        profit=120000, order_value=250000,
        job_type="Plumbing", quantity=1,
        raw_materials=[
            {"name": "CPVC Pipe",     "quantity": 200, "unit": "m",   "unit_cost": 65},
            {"name": "Fitting Set",   "quantity": 50,  "unit": "pcs", "unit_cost": 120},
            {"name": "Sealant",       "quantity": 10,  "unit": "pcs", "unit_cost": 280},
        ],
        skill_reqs=[(plumb, "Premium", 2), (civil, "Generic", 1)],
        machines=[m1], employees=[e3, e5, e6],
        steps=[
            {"name": "Survey & marking", "type": "setup",      "duration": 120},
            {"name": "Pipe laying",      "type": "production", "duration": 480},
            {"name": "Fitting & joints", "type": "production", "duration": 240},
            {"name": "Pressure test",    "type": "inspection", "duration": 60},
        ])


# --- Main entry point ---------------------------------------------------------

SEEDERS = {
    "printing":     _seed_printing,
    "manufacturing":_seed_manufacturing,
    "fabrication":  _seed_fabrication,
    "chemical":     _seed_chemical,
    "field_service":_seed_field_service,
}


def seed_demo_data(db: Session, tenant_id: int, industry_type: str) -> None:
    """
    Seed demo data for a new tenant based on their industry_type.
    Called automatically after registration.
    Safe to call multiple times — skips existing records.
    """
    seeder = SEEDERS.get(industry_type or "printing")
    if seeder:
        seeder(db, tenant_id)
        db.commit()
