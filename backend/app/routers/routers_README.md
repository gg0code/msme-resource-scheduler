# backend/app/routers/

FastAPI route handlers. Each file defines the API endpoints for one resource.
This is where HTTP requests come in and responses go out.

## Files in this folder

| File | What it does |
|------|--------------|
| auth.py | Login, logout, and token refresh endpoints |
| employees.py | CRUD endpoints for employees |
| jobs.py | CRUD endpoints for jobs |
| machines.py | CRUD endpoints for machines |
| skills.py | CRUD endpoints for skills |
| availability.py | Endpoints for employee availability rules |
| unavailability.py | Endpoints for employee unavailability exceptions |
| assignments.py | Endpoints for assigning employees/machines to jobs |
| scheduling.py | Endpoints that trigger or query the scheduler |
| scheduler_router.py | Additional scheduler endpoints (run, status, results) |
| gantt.py | Endpoint that returns Gantt chart data for the frontend |
| dashboard.py | Endpoint that returns summary statistics for the dashboard |
| import_csv.py | Endpoint that accepts a CSV file and bulk-imports data |
| scan.py | Endpoint for QR code scanning to look up a job |
| timer.py | Endpoints for starting and stopping job timers |
| steps.py | Endpoints for managing steps within a job |
| features.py | Endpoint that returns which features are enabled for the current tenant |
| ai_chat.py | Endpoint that sends messages to the AI assistant |
| resource_availability.py | GET /api/jobs/{job_id}/resource-availability — returns real-time computed free capacity for each employee and machine assigned to a job, scoped to the job's date range (added v3.9.4) |
| __init__.py | Marks folder as Python package |

## Important notes
- Every router is registered in app/main.py — new routers must be added there
- All routes require authentication via the dependency in core/dependencies.py
- Routes are tenant-scoped — a user can only see their own tenant's data
- resource_availability.py is mounted under prefix /api/jobs so the endpoint resolves to /api/jobs/{job_id}/resource-availability
