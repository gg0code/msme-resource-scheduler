"""
app/main.py — V1.1
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    auth, assignments, availability, dashboard,
    employees, import_csv, jobs, machines, skills,
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
