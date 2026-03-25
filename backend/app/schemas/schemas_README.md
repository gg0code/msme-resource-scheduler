# backend/app/schemas/

Pydantic models that define the shape of API request bodies and responses.
These are NOT database tables — they are just data validators for the API.

## Files in this folder

| File | What it does |
|------|--------------|
| auth.py | Login request body and token response shapes |
| employee.py | Shapes for creating, updating, and reading employees |
| job.py | Shapes for creating, updating, and reading jobs |
| machine.py | Shapes for machine data in API requests and responses |
| skill.py | Shapes for skill data |
| availability.py | Shape for availability rules |
| scheduling.py | Shapes for scheduling requests and results |
| resource_availability.py | Response shapes for the real-time resource availability endpoint — EmployeeAvailability, MachineAvailability, ResourceAvailabilityResponse (added v3.9.4) |
| __init__.py | Marks folder as Python package |

## Important notes
- Schema files mirror model files but are not the same thing
- A schema controls what the API accepts and returns — the model controls the database
- Use BaseResponse schemas for GET responses and BaseCreate schemas for POST bodies
- resource_availability.py includes a materials: [] field reserved for v3.9.5 stock tracking
