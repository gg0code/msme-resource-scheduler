"""
scripts/seed_scheduling.py — Seed data for Prompt 1 scheduling engine

Seeds for tenant_id=2 (owner@abc.com) by default.
Usage (from backend/ directory):
  venv\\Scripts\\python.exe scripts/seed_scheduling.py
  venv\\Scripts\\python.exe scripts/seed_scheduling.py --tenant-id 5
  venv\\Scripts\\python.exe scripts/seed_scheduling.py --wipe

Creates:
  Resources: M1, M2 (machine), H1, H2 (helper)  — morning shift 08:00–16:00
  Job XY1 (critical, profit=70000, deadline=next Wednesday, shift=morning)
    seq=1 regular  machines=[M1]  helpers=[H1]  120 min
    seq=2 regular  machines=[M2]  helpers=[H2]   90 min
    seq=3 setup    machines=[]    helpers=[H1]   reserve=M1  30 min
    seq=4 regular  machines=[M1]  helpers=[H1]   60 min
  Job XY2 (urgent, profit=90000, deadline=next Thursday, shift=morning)
    seq=1 regular  machines=[M2]  helpers=[H2]   60 min
    seq=2 setup    machines=[]    helpers=[H2]   reserve=M1  20 min
    seq=3 regular  machines=[M1]  helpers=[H2]  120 min
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
