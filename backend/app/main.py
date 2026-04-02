"""
```python
"""
FILE PURPOSE
This is the main FastAPI application entry point for ZetaOps Copilot (v4.0.9 production).
It creates the FastAPI app instance, configures CORS middleware, registers all API route 
handlers with their prefixes, and manages startup/shutdown lifecycle events including the
WhatsApp alert scheduler (v5 feature) and auto-advance background tasks. This file was
introduced in the initial v1.0 and sits at the top of the backend architecture as the
single point where all API endpoints are assembled and exposed.

WHAT THIS FILE DOES — step by step
1. Imports FastAPI framework and CORS middleware for cross-origin requests
2. Imports application settings/configuration from app.config
3. Imports all router modules (auth, jobs, employees, machines, etc.) that contain API endpoints
4. Imports WhatsApp services and background task functions (v5-whatsapp features)
5. Creates the main FastAPI application instance with title, version, and docs URLs
6. Adds CORS middleware with allowed origins from settings to enable frontend communication
7. Defines startup event handler that starts WhatsApp alert scheduler and auto-advance loop
8. Defines shutdown event handler that gracefully stops the WhatsApp scheduler
9. Creates a /health endpoint for load balancer health checks
10. Registers all imported routers with their URL prefixes and OpenAPI tags
11. Exposes the configured app instance for ASGI servers (uvicorn/gunicorn) to run

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : app
Type         : FastAPI application instance
Purpose      : The main application object that ASGI servers run. Contains all middleware,
               routes, and lifecycle handlers. This is what uvicorn or gunicorn actually
               serves to handle HTTP requests.
Parameters   : title (APP_NAME from settings), version (APP_VERSION), docs_url, redoc_url
Returns      : N/A (global instance)
Calls        : settings.APP_NAME, settings.APP_VERSION for configuration
DB/API       : No direct calls, but enables all routers that do make DB/API calls
Side effects : Registers all API routes, enables CORS, starts background schedulers

Name         : startup_event
Type         : FastAPI lifecycle function
Purpose      : Executes once when the FastAPI server starts up. Initializes the WhatsApp
               alert scheduler (APScheduler) that sends proactive notifications to factory
               owners and starts the auto-advance background loop for completing overdue steps.
Parameters   : None (FastAPI event handler)
Returns      : None (async event handler)
Calls        : start_scheduler() from whatsapp_alerts, auto_advance_loop() from tasks
DB/API       : No direct calls, but enables services that will make WhatsApp API calls
Side effects : Starts APScheduler daemon, creates asyncio background task

Name         : shutdown_event  
Type         : FastAPI lifecycle function
Purpose      : Executes once when the FastAPI server shuts down. Gracefully stops the
               WhatsApp alert scheduler, waiting for any running jobs to finish before
               terminating to prevent message delivery issues.
Parameters   : None (FastAPI event handler)
Returns      : None (async event handler)
Calls        : stop_scheduler() from whatsapp_alerts
DB/API       : No direct calls
Side effects : Stops APScheduler, cancels pending WhatsApp alert jobs

Name         : health_check
Type         : FastAPI endpoint function
Purpose      : Provides a simple health check endpoint at /health for load balancers and
               monitoring systems to verify the application is running and responsive.
               Returns basic status and version information.
Parameters   : None (GET endpoint)
Returns      : Dict with "status": "ok" and "version": APP_VERSION
Calls        : settings.APP_VERSION for version info
DB/API       : No calls (intentionally lightweight for health checks)
Side effects : None (read-only status check)

WHO CALLS THIS FILE
- ASGI servers like uvicorn or gunicorn import and run the `app` instance
- Docker containers and deployment scripts reference this as the application entry point
- No other application files import main.py directly (it's the top-level module)

IMPORTS EXPLAINED
- asyncio: Needed to create background tasks for auto-advance loop using create_task()
- FastAPI: The core web framework class used to create the application instance
- CORSMiddleware: Enables cross-origin requests from the React frontend running on different ports
- app.config.settings: Application configuration including APP_NAME, APP_VERSION, allowed_origins
- app.routers.*: All route handler modules containing FastAPI router instances with API endpoints
- app.routers.whatsapp.router: WhatsApp Copilot API endpoints for v5 feature branch
- app.services.whatsapp_alerts: Scheduler management functions for proactive WhatsApp notifications
- app.tasks.auto_advance: Background loop that auto-completes overdue job steps every 15 minutes

INTERN NOTES
- Easiest thing to break: Adding a router without the /api/ prefix violates design principle #4
- Non-obvious design: WhatsApp features are imported but won't function without proper feature flags and v5 branch
- Most common mistake: Forgetting to register new routers here after creating them, causing 404s for new endpoints
- Design principle #4: All backend routes must have /api/ prefix (see router registrations)
- What to check if unexpected behavior: Verify startup_event completed successfully and didn't throw scheduler errors
- v5-whatsapp merging: Remove whatsapp_router import and startup/shutdown scheduler calls when merging to v4-dev
"""
```
"""

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    auth, assignments, availability, dashboard,
    employees, import_csv, jobs, machines, skills,
    timer, gantt,
    scan,                # V3.2 QR scan tokens
    scheduling,          # V3.0
    scheduler_router as scheduler,      # V3.1
    unavailability,      # V3.2 employee leaves + machine downtimes
    features,            # V3.7 feature flags
    ai_chat,             # V3.9 AI Copilot
    resource_availability,              # V3.9.4 real-time resource availability
    steps,               # V3.9.5 job step CRUD
    schedule_suggestions,# V3.9.7 schedule suggestions
    material_estimate,   # V3.9.8 material estimate
)
# v5-whatsapp — WhatsApp Copilot router and alert scheduler
from app.routers.whatsapp import router as whatsapp_router
from app.services.whatsapp_alerts import start_scheduler, stop_scheduler
from app.tasks.auto_advance import auto_advance_loop

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


@app.on_event("startup")
async def startup_event():
    """
    Called when FastAPI app starts.
    Starts the WhatsApp alert scheduler (APScheduler).
    Scheduler sends proactive alerts to factory owners:
    morning briefing at 7am IST, job delay checks, conflict checks.
    """
    start_scheduler()
    asyncio.create_task(auto_advance_loop())  # auto-complete overdue steps every 15 min


@app.on_event("shutdown")
async def shutdown_event():
    """
    Called when FastAPI app shuts down.
    Stops the WhatsApp alert scheduler gracefully —
    waits for any running jobs to finish before stopping.
    """
    stop_scheduler()

# Returns a simple status response used by load balancers and monitoring tools.
# If this endpoint responds, the app is running and the process is healthy.
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


app.include_router(auth.router)
app.include_router(assignments.router,          prefix="/api/assignments",          tags=["assignments"])
app.include_router(availability.router,         prefix="/api/availability",         tags=["availability"])
app.include_router(dashboard.router,            prefix="/api/dashboard",            tags=["dashboard"])
app.include_router(employees.router,            prefix="/api/employees",            tags=["employees"])
app.include_router(import_csv.router,           prefix="/api/import",               tags=["import"])
app.include_router(jobs.router,                 prefix="/api/jobs",                 tags=["jobs"])
app.include_router(machines.router,             prefix="/api/machines",             tags=["machines"])
app.include_router(skills.router,               prefix="/api/skills",               tags=["skills"])
app.include_router(timer.router,                prefix="/api/timer",                tags=["timer"])
app.include_router(gantt.router,                prefix="/api/gantt",                tags=["gantt"])
app.include_router(scheduling.router,           prefix="/api",                      tags=["scheduling"])
app.include_router(scheduler.router,            prefix="/api",                      tags=["scheduler"])
app.include_router(scan.router,                 prefix="/api",                      tags=["scan"])
app.include_router(unavailability.router,       prefix="/api/unavailability",       tags=["unavailability"])
app.include_router(features.router,             prefix="/api",                      tags=["features"])
app.include_router(ai_chat.router,              prefix="/api/ai",                   tags=["ai"])
app.include_router(resource_availability.router, prefix="/api/jobs",               tags=["resource-availability"])  # V3.9.4
app.include_router(steps.router,                prefix="/api",                      tags=["steps"])               # V3.9.5
app.include_router(schedule_suggestions.router, prefix="/api",                      tags=["schedule-suggestions"])  # V3.9.7
app.include_router(material_estimate.router,    prefix="/api",                      tags=["material-estimate"])      # V3.9.8
app.include_router(whatsapp_router,             tags=["whatsapp"])                                                    # v5-whatsapp