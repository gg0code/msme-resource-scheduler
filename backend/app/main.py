"""
app/main.py — V3.2 (Block 2)
Added: scan router, auto-advance background task
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    auth, assignments, availability, dashboard,
    employees, import_csv, jobs, machines, skills,
    timer, gantt,
    scheduling,
    scheduler_router as scheduler,
)
from app.routers import scan as scan_router
from app.routers import steps as steps_router
from app.tasks.auto_advance import auto_advance_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(auto_advance_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


app.include_router(auth.router)
app.include_router(assignments.router,  prefix="/api/assignments",  tags=["assignments"])
app.include_router(availability.router, prefix="/api/availability", tags=["availability"])
app.include_router(dashboard.router,    prefix="/api/dashboard",    tags=["dashboard"])
app.include_router(employees.router,    prefix="/api/employees",    tags=["employees"])
app.include_router(import_csv.router,   prefix="/api/import",       tags=["import"])
app.include_router(jobs.router,         prefix="/api/jobs",         tags=["jobs"])
app.include_router(machines.router,     prefix="/api/machines",     tags=["machines"])
app.include_router(skills.router,       prefix="/api/skills",       tags=["skills"])
app.include_router(timer.router,        prefix="/api/timer",        tags=["timer"])
app.include_router(gantt.router,        prefix="/api/gantt",        tags=["gantt"])
app.include_router(scheduling.router,   prefix="/api",              tags=["scheduling"])
app.include_router(scheduler.router,    prefix="/api",              tags=["scheduler"])
app.include_router(steps_router.router, prefix="/api",              tags=["steps"])
app.include_router(scan_router.router,  prefix="/api",              tags=["scan"])
