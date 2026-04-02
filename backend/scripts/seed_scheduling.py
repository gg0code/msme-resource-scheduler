"""
```python
"""
────────────────────────────────────────────────────────────────────────────────────────────────
SEED SCHEDULING DATA SCRIPT
────────────────────────────────────────────────────────────────────────────────────────────────

FILE PURPOSE
This is a development utility script that creates test data for the ZetaOps Copilot scheduling 
engine, specifically designed for "Prompt 1" testing scenarios. It was introduced in v4-dev to 
enable rapid testing of the core scheduling engine without manually creating complex job hierarchies 
through the UI. The script sits outside the main application architecture as a standalone database 
seeding tool and creates a realistic manufacturing scenario with interdependent jobs, multi-step 
workflows, and resource constraints that stress-test the scheduling algorithms.

WHAT THIS FILE DOES — step by step
1. Parses command-line arguments for tenant ID selection and optional data wiping
2. Calculates next Wednesday and Thursday dates as realistic job deadlines
3. Establishes database connection using the main app's SessionLocal
4. Optionally wipes existing seed data if --wipe flag is provided
5. Creates or retrieves four resources: two machines (M1, M2) and two helpers (H1, H2)
6. Sets all resources to morning shift schedule (08:00-16:00)
7. Creates Job XY1 with 4 sequential steps, critical priority, and Wednesday deadline
8. Creates Job XY2 with 3 sequential steps, urgent priority, and Thursday deadline
9. Links each job step to specific machines and helpers based on manufacturing workflow
10. Sets the first step of each job to "ready" status following scheduling Rule 1
11. Commits all changes to database and closes connection

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : next_weekday
Type         : function
Purpose      : Calculates the next occurrence of a specified weekday at 09:00 AM, used to 
               generate realistic job deadlines that fall on business days. This ensures 
               seeded jobs always have future deadlines regardless of when the script runs.
Parameters   : weekday (int) - day of week where 0=Monday through 6=Sunday
Returns      : datetime object representing the next occurrence of that weekday at 09:00
Calls        : Python datetime.now(), datetime.replace(), timedelta()
DB/API       : None - pure date calculation
Side effects : None

Name         : get_or_create_resource
Type         : function  
Purpose      : Database helper that either retrieves an existing SchedResource by name or 
               creates a new one with specified type and morning shift hours. Prevents 
               duplicate resource creation when script runs multiple times.
Parameters   : name (str) - resource identifier like "M1" or "H1"
               rtype (ResourceType) - enum value of ResourceType.machine or ResourceType.helper
Returns      : SchedResource ORM instance, either existing or newly created
Calls        : SQLAlchemy db.query(), db.add(), db.flush()
DB/API       : SELECT query on SchedResource table filtered by tenant_id and name
               INSERT into SchedResource if not found
Side effects : Prints status message, adds resource to database session

Name         : create_job_if_missing
Type         : function
Purpose      : Creates a complete SchedJob with all associated SchedStep records and their 
               machine/helper assignments, but only if a job with that name doesn't already 
               exist. Implements the full job creation workflow including step sequencing 
               and Rule 1 application (first step becomes ready).
Parameters   : name (str) - job identifier like "XY1"
               priority (SchedJobPriority) - enum value for job priority level
               profit (float) - expected profit value for scheduling priority calculation
               deadline (datetime) - when job must be completed
               steps_data (list) - list of dicts containing step configuration data
Returns      : None - creates database records as side effect
Calls        : SQLAlchemy db.query(), db.add(), db.flush(), db.commit()
DB/API       : SELECT query on SchedJob to check existence
               INSERT into SchedJob, SchedStep, SchedStepMachine, SchedStepHelper tables
Side effects : Creates complete job hierarchy in database, prints creation status

Name         : run
Type         : function
Purpose      : Main orchestration function that executes the entire seeding process from 
               database connection through resource and job creation. Handles the optional 
               wipe operation and ensures proper database session management with cleanup.
Parameters   : None - reads from global args variable
Returns      : None - performs seeding as side effect
Calls        : SessionLocal(), get_or_create_resource(), create_job_if_missing()
DB/API       : DELETE queries for wiping existing data
               Full resource and job creation through helper functions
Side effects : Creates or wipes database records, prints progress messages, closes DB session

WHO CALLS THIS FILE
This script is executed directly from the command line and is not imported by any other files 
in the codebase. It's run manually by developers using:
- venv\Scripts\python.exe scripts/seed_scheduling.py
- venv\Scripts\python.exe scripts/seed_scheduling.py --tenant-id 5  
- venv\Scripts\python.exe scripts/seed_scheduling.py --wipe

IMPORTS EXPLAINED
sys, os, argparse - Standard library modules for path manipulation and command-line argument parsing needed for script execution outside the main app context.
datetime, time, timedelta - Date/time handling for calculating realistic job deadlines and resource shift schedules.
app.database.SessionLocal - Database session factory from main application to connect to the same PostgreSQL instance.
app.models.scheduling - All ORM models for the legacy scheduling system including SchedResource, SchedJob, SchedStep and their associated enums and relationship tables.

INTERN NOTES
• Easiest thing to break: Running this script against the wrong tenant ID can pollute production data or create orphaned records that confuse the scheduling engine
• Non-obvious design decision: This script uses the LEGACY SchedJob/SchedStep models instead of the newer Job/JobStep models because it was created before the model migration was complete
• Most common mistake: Forgetting to run this from the backend/ directory causes import path failures since the script manipulates sys.path to find the app modules
• Design principle #2: The script properly implements tenant scoping on all database queries by consistently filtering with tenant_id, preventing cross-tenant data leakage
• What to check if behaving unexpectedly: Verify the database connection string matches your development environment and that alembic migrations are up to date, especially migration 018
• Migration consideration: When this script is eventually updated to use the new Job/JobStep models, the step sequencing logic and Rule 1 implementation may need adjustment
"""
```
"""

import sys, os, argparse
from datetime import datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.scheduling import (
    SchedResource, SchedJob, SchedStep,
    SchedStepMachine, SchedStepHelper,
    ResourceType, SchedJobPriority, SchedJobShift, SchedJobStatus,
    StepType, StepStatus,
)

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--wipe", action="store_true", help="Delete seeded data before re-seeding")
parser.add_argument("--tenant-id", type=int, default=2)
args = parser.parse_args()

TENANT_ID = args.tenant_id


def next_weekday(weekday: int) -> datetime:
    """Return next occurrence of weekday (0=Mon … 6=Sun) at 09:00."""
    today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


WEDNESDAY = 2
THURSDAY  = 3


def run():
    db = SessionLocal()
    try:
        if args.wipe:
            print("Wiping existing scheduling seed data...")
            for job in db.query(SchedJob).filter_by(tenant_id=TENANT_ID).all():
                db.delete(job)
            for res in db.query(SchedResource).filter_by(tenant_id=TENANT_ID).filter(
                SchedResource.name.in_(["M1", "M2", "H1", "H2"])
            ).all():
                db.delete(res)
            db.commit()
            print("  Wiped.")

        # ── Resources ─────────────────────────────────────────────────────────
        def get_or_create_resource(name: str, rtype: ResourceType) -> SchedResource:
            res = db.query(SchedResource).filter_by(
                tenant_id=TENANT_ID, name=name
            ).first()
            if res:
                print(f"  Resource '{name}' already exists — skipping.")
                return res
            res = SchedResource(
                tenant_id=TENANT_ID,
                name=name,
                type=rtype,
                shift_start=time(8, 0),
                shift_end=time(16, 0),
            )
            db.add(res)
            db.flush()
            print(f"  Created resource: {name} ({rtype.value})")
            return res

        print("\n── Resources ──────────────────────────────────────────")
        M1 = get_or_create_resource("M1", ResourceType.machine)
        M2 = get_or_create_resource("M2", ResourceType.machine)
        H1 = get_or_create_resource("H1", ResourceType.helper)
        H2 = get_or_create_resource("H2", ResourceType.helper)
        db.commit()

        # ── Helper: create job + steps ─────────────────────────────────────────
        def create_job_if_missing(
            name: str,
            priority: SchedJobPriority,
            profit: float,
            deadline: datetime,
            steps_data: list,
        ) -> None:
            existing = db.query(SchedJob).filter_by(
                tenant_id=TENANT_ID, name=name
            ).first()
            if existing:
                print(f"  Job '{name}' already exists — skipping.")
                return

            job = SchedJob(
                tenant_id=TENANT_ID,
                name=name,
                priority=priority,
                expected_profit=profit,
                deadline=deadline,
                shift=SchedJobShift.morning,
                lock_status=False,
                status=SchedJobStatus.pending,
            )
            db.add(job)
            db.flush()

            for i, sd in enumerate(steps_data, start=1):
                step = SchedStep(
                    job_id=job.id,
                    sequence_order=i,
                    step_type=sd["type"],
                    duration_minutes=sd["duration"],
                    reserve_machine_id=sd.get("reserve_machine_id"),
                    status=StepStatus.pending,
                )
                db.add(step)
                db.flush()

                for res in sd.get("machines", []):
                    db.add(SchedStepMachine(step_id=step.id, resource_id=res.id))
                for res in sd.get("helpers", []):
                    db.add(SchedStepHelper(step_id=step.id, resource_id=res.id))

            # Apply Rule 1: first step becomes ready
            first = db.query(SchedStep).filter_by(job_id=job.id, sequence_order=1).first()
            if first:
                first.status = StepStatus.ready

            db.commit()
            print(f"  Created job: {name} ({len(steps_data)} steps)")

        # ── Job XY1 ───────────────────────────────────────────────────────────
        print("\n── Jobs ───────────────────────────────────────────────")
        create_job_if_missing(
            name="XY1",
            priority=SchedJobPriority.critical,
            profit=70000.0,
            deadline=next_weekday(WEDNESDAY),
            steps_data=[
                {"type": StepType.regular, "machines": [M1],  "helpers": [H1], "duration": 120},
                {"type": StepType.regular, "machines": [M2],  "helpers": [H2], "duration": 90},
                {"type": StepType.setup,   "machines": [],    "helpers": [H1], "duration": 30, "reserve_machine_id": M1.id},
                {"type": StepType.regular, "machines": [M1],  "helpers": [H1], "duration": 60},
            ],
        )

        # ── Job XY2 ───────────────────────────────────────────────────────────
        create_job_if_missing(
            name="XY2",
            priority=SchedJobPriority.urgent,
            profit=90000.0,
            deadline=next_weekday(THURSDAY),
            steps_data=[
                {"type": StepType.regular, "machines": [M2],  "helpers": [H2], "duration": 60},
                {"type": StepType.setup,   "machines": [],    "helpers": [H2], "duration": 20, "reserve_machine_id": M1.id},
                {"type": StepType.regular, "machines": [M1],  "helpers": [H2], "duration": 120},
            ],
        )

        print("\n✓ Seed complete.")

    finally:
        db.close()


if __name__ == "__main__":
    run()
