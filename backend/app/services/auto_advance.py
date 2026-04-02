import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal

logger = logging.getLogger("auto_advance")


def _run_auto_advance(db: Session):
    from app.models.job_steps import JobStep
    from app.models.job import Job

    now = datetime.now(timezone.utc)
    overdue_count = 0

    # Find all in_progress steps
    in_progress = db.query(JobStep).filter(JobStep.status == "in_progress").all()

    for step in in_progress:
        if step.started_at is None:
            continue

        started = step.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        grace_end = started + timedelta(minutes=step.duration_minutes * 1.5)

        if now < grace_end:
            continue  # not overdue yet

        # Auto-complete this step
        logger.info(f"Auto-advancing step {step.id} '{step.name}' (job {step.job_id})")
        step.status = "complete"
        step.updated_at = now

        # Unlock next step
        next_step = (
            db.query(JobStep)
            .filter(
                JobStep.job_id == step.job_id,
                JobStep.tenant_id == step.tenant_id,
                JobStep.sequence_no == step.sequence_no + 1,
            )
            .first()
        )
        if next_step and next_step.status == "locked":
            next_step.status = "ready"

        # Check if all steps complete -> close job
        all_steps = (
            db.query(JobStep)
            .filter(JobStep.job_id == step.job_id, JobStep.tenant_id == step.tenant_id)
            .all()
        )
        if all(s.status == "complete" for s in all_steps):
            job = db.query(Job).filter(Job.id == step.job_id).first()
            if job and job.status != "completed":
                job.status = "completed"
                logger.info(f"Auto-completed job {step.job_id}")

        overdue_count += 1

    if overdue_count:
        db.commit()
        logger.info(f"Auto-advance: completed {overdue_count} overdue step(s)")


async def auto_advance_loop():
    """Async loop — runs every 15 minutes. Start from FastAPI lifespan."""
    logger.info("Auto-advance engine started (15-min interval)")
    while True:
        try:
            db: Session = SessionLocal()
            try:
                _run_auto_advance(db)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Auto-advance error: {e}")
        await asyncio.sleep(15 * 60)  # 15 minutes
