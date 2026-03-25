# frontend/src/api/

Functions that make HTTP requests to the backend API.
Each file handles one area of the application.
UI components import from here — they never call fetch() directly.

## Files in this folder

| File | What it does |
|------|--------------|
| client.ts | Sets up the base Axios/fetch instance with the API URL and auth headers |
| api_employees.ts | API calls for listing, creating, updating, and deleting employees |
| api_jobs.ts | API calls for job management |
| api_machines.ts | API calls for machine management |
| api_skills.ts | API calls for skill management |
| api_dashboard.ts | API call for fetching dashboard summary data |
| api_gantt.ts | API call for fetching Gantt chart data |
| api_timer.ts | API calls for starting and stopping job timers |
| scheduling.ts | API calls for triggering and checking the scheduler |
| api_resource_availability.ts | Fetches real-time computed free capacity for employees and machines on a job's date range. Also exports display helper functions (employeeStatusColor, employeeStatusLabel, machineStatusLabel) used by the job panel component (added v3.9.4) |

## Important notes
- All functions in these files return a Promise
- Auth token is attached automatically by client.ts — do not add it manually
- If the API base URL changes, update it in .env (VITE_API_BASE_URL) not here
- api_resource_availability.ts includes display helpers alongside the API call — keeps all resource availability logic in one place
