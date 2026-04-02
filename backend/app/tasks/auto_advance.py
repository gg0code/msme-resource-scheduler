"""
```python
"""
backend/app/tasks/auto_advance.py — Background Task for Automatic Step Completion

FILE PURPOSE
This file contains the background task engine that automatically advances overdue job steps
from 'in_progress' to 'complete' status. Introduced in v3.2 as part of the ZetaOps Copilot
manufacturing scheduler, this runs as an async background loop to prevent jobs from getting
stuck when workers forget to manually mark steps as complete. It sits in the tasks layer
of our FastAPI backend architecture, operating independently of user interactions to maintain
job flow continuity across all tenant manufacturing operations.

WHAT THIS FILE DOES — step by step
1. Defines a synchronous helper function _run_auto_advance() that performs the core database operations
2. Queries all JobStep records with status='in_progress' across all tenants
3. For each in-progress step, calculates if it's overdue using a 1.5x grace period multiplier
4. Auto-completes overdue steps by setting status='complete' and updating timestamps
5. Unlocks the next sequential step in the job by changing its status from 'locked' to 'ready'
6. Checks if all steps in a job are complete and marks the parent Job as 'completed' if so
7. Commits all changes to the database and logs the number of steps advanced
8. Defines an async loop function that runs the auto-advance logic every 15 minutes
9. Handles database session management and error logging for the background process

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _run_auto_advance
Type         : function (private helper)
Purpose      : Core synchronous function that performs the actual auto-advancement logic for overdue job steps. It finds in-progress steps that have exceeded their grace period (duration * 1.5), marks them complete, unlocks subsequent steps, and potentially completes entire jobs. This is the business logic heart of the auto-advance system.
Parameters   : db (Session) - SQLAlchemy database session for performing queries and updates
Returns      : None - operates via side effects on the database
Calls        : app.models.job_steps.JobStep and app.models.job.Job for ORM operations
DB/API       : Queries JobStep for in_progress status, queries for next steps by sequence_no, queries Job for completion updates, commits transaction
Side effects : Updates JobStep.status and updated_at, modifies next step status, changes Job.status to completed, logs advancement actions

Name         : auto_advance_loop
Type         : function (async)
Purpose      : Infinite async loop that runs the auto-advance engine every 15 minutes. This is the entry point for the background task system, designed to be started from FastAPI's lifespan context manager. It handles database session creation/cleanup and error recovery to ensure the background process remains stable across application lifetime.
Parameters   : None - runs indefinitely once started
Returns      : None (never returns, infinite loop)
Calls        : _run_auto_advance() for the core logic, SessionLocal() for database connections
DB/API       : Creates new database sessions via SessionLocal, no direct queries
Side effects : Runs continuously, creates/closes DB sessions, sleeps for 15-minute intervals, logs startup and error messages

WHO CALLS THIS FILE
- backend/app/main.py (lifespan context manager starts auto_advance_loop during application startup)
- No direct imports from other application files - this is a standalone background service

IMPORTS EXPLAINED
- asyncio: Provides async/await support and sleep functionality for the 15-minute loop interval
- logging: Creates logger instance for tracking auto-advance operations and debugging issues
- datetime, timedelta, timezone: Handle timezone-aware datetime calculations for determining if steps are overdue
- sqlalchemy.orm.Session: Type hint for database session parameter in the helper function
- app.database.SessionLocal: Database session factory for creating new connections in the background loop

INTERN NOTES
- Easiest thing to break: Forgetting timezone handling when comparing started_at times - naive datetimes will cause incorrect overdue calculations
- Non-obvious design decision: Uses 1.5x grace period multiplier instead of exact duration to account for worker delays and prevent premature auto-completion
- Most common mistake: Modifying the grace period calculation without considering that workers expect reasonable buffer time before auto-advancement
- Design principles: Implements principle #2 (tenant scoping) by filtering JobStep queries by tenant_id, and principle #1 (engine computes) by using pure database logic without AI involvement
- Debugging checklist: Verify the loop is running via logs, check timezone consistency in started_at fields, confirm database sessions are being closed properly, validate sequence_no increments are correct
- Background task considerations: This runs independently of user requests so database connection pool limits and long-running transaction impacts must be monitored in production
"""
```
"""

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

        # Check if all steps complete → close job
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
