# app/main.py - Version 2.0
# Branch: both
#
# FILE PURPOSE
# Application entry point. Single source of truth for ALL router registrations.
# Every router in app/routers/ is registered here with the correct prefix.
# Layer: entrypoint
#
# WHAT THIS FILE DOES
# 1. Creates FastAPI app instance with settings
# 2. Attaches CORS middleware
# 3. Manages WhatsApp alert scheduler via lifespan context manager
# 4. Registers ALL routers with their definitive prefixes
#
# PREFIX RULES - memorise these
# - Standard routers: prefix="/api/routername"
# - Routers whose paths already start with /jobs/ or /scheduler/ etc:
#   use prefix="/api" so paths become /api/jobs/{id}/steps etc.
# - auth: no prefix (paths are /auth/*)
# - whatsapp: no prefix (self-contained webhook paths)
# - features: prefix="/api" only (single endpoint /features -> /api/features)
#
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    auth,
    assignments,
    availability,
    dashboard,
    employees,
    import_csv,
    jobs,
    machines,
    skills,
    features,
    ai_chat,
    gantt,
    timer,
    steps,
    material_estimate,
    onboarding,
    schedule_suggestions,
    scheduler_router,
    scan,
    team_management,
    unavailability,
)
from app.routers import whatsapp as whatsapp_router
from app.services.whatsapp_alerts import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


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


# =============================================================================
# ROUTER REGISTRATIONS
# =============================================================================

# -- Auth (no prefix - paths are /auth/register, /auth/login etc) -------------
app.include_router(auth.router)

# -- Dashboard -------------------------------------------------------------------
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])

# -- Standard /api/resource routers -------------------------------------------
app.include_router(assignments.router,  prefix="/api/assignments",  tags=["assignments"])
app.include_router(availability.router, prefix="/api/availability", tags=["availability"])
app.include_router(employees.router,    prefix="/api/employees",    tags=["employees"])
app.include_router(import_csv.router,   prefix="/api/import",       tags=["import"])
app.include_router(jobs.router,         prefix="/api/jobs",         tags=["jobs"])
app.include_router(machines.router,     prefix="/api/machines",     tags=["machines"])
app.include_router(skills.router,       prefix="/api/skills",       tags=["skills"])
app.include_router(gantt.router,        prefix="/api/gantt",        tags=["gantt"])
app.include_router(timer.router,        prefix="/api/timer",        tags=["timer"])
app.include_router(team_management.router, prefix="/api/team",      tags=["team"])

# -- /api prefix routers (paths already contain their resource segment) -------
# steps:                /jobs/{id}/steps/*               -> /api/jobs/{id}/steps/*
# material_estimate:    /jobs/{id}/material-estimate      -> /api/jobs/{id}/material-estimate
# schedule_suggestions: /jobs/{id}/schedule-suggestions   -> /api/jobs/{id}/schedule-suggestions
# scheduler_router:     /scheduler/run|entries            -> /api/scheduler/*
# scan:                 /jobs/{id}/scan-tokens, /scan/*   -> /api/jobs/{id}/scan-tokens etc
# features:             /features                         -> /api/features
app.include_router(steps.router,                prefix="/api", tags=["steps"])
app.include_router(material_estimate.router,    prefix="/api", tags=["material-estimate"])
app.include_router(schedule_suggestions.router, prefix="/api", tags=["schedule-suggestions"])
app.include_router(scheduler_router.router,     prefix="/api", tags=["scheduler"])
app.include_router(scan.router,                 prefix="/api", tags=["scan"])
app.include_router(unavailability.router,        prefix="/api", tags=["unavailability"])
app.include_router(features.router,             prefix="/api", tags=["features"])

# -- AI Copilot ---------------------------------------------------------------
app.include_router(ai_chat.router, prefix="/api/ai", tags=["ai"])

# -- Onboarding (v6.3.12 Day-1 confirmation) ---------------------------------
# POST /api/v1/onboarding/complete - fired once per tenant from the
# OnboardingSetup.tsx Save & Continue button, dispatches the Day-1
# WhatsApp confirmation message via app/services/onboarding_message.py.
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])

# -- WhatsApp (no prefix - webhook paths are self-contained) ------------------
app.include_router(whatsapp_router.router)

# -- scheduling.py (v2 scheduler API) NOT registered yet ---------------------
# Uncomment when v2 scheduling goes live:
# from app.routers import scheduling
# app.include_router(scheduling.router, prefix="/api", tags=["scheduling-v2"])
