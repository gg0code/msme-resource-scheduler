"""
app/main.py — V3.1
Added: scheduler router (/api/scheduler/*)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    auth, assignments, availability, dashboard,
    employees, import_csv, jobs, machines, skills,
    timer, gantt,
    scan,          # V3.2 QR scan tokens
    scheduling,    # V3.0
    scheduler_router as scheduler,  # V3.1 NEW
    unavailability,  # V3.2 employee leaves + machine downtimes
    features,      # V3.7 feature flags
    ai_chat,       # V3.9 AI Copilot
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
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
app.include_router(scheduler.router,    prefix="/api",              tags=["scheduler"])  # V3.1
app.include_router(scan.router,           prefix="/api",               tags=["scan"])             # V3.2 QR
app.include_router(unavailability.router, prefix="/api/unavailability", tags=["unavailability"])  # V3.2
app.include_router(features.router,     prefix="/api",              tags=["features"])   # V3.7
app.include_router(ai_chat.router,      prefix="/api/ai",           tags=["ai"])         # V3.9
