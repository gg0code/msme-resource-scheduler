AUTO-GENERATED - frontend/src/types/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/types/
PURPOSE: Single source of truth for all shared TypeScript domain interfaces.

FILES
  types_index.ts  - All shared interfaces: Skill, Employee, Machine, Job,
                    DashboardJob, DashboardData, AvailabilityOverride,
                    ImportResult, JobStep, PlanLimits, and all sub-types.
                    Named union types: StartMode, TimerStatus, JobStatus.
                    Branch: both.

ARCHITECTURE NOTES
This is the most imported file in the frontend after api/client.ts. Every API
function and most page components import types from here. Industry config types
live separately in src/config/industries/types.ts and are never duplicated here.
The Job interface mirrors the backend Job SQLAlchemy model exactly - 30+ fields.
DashboardJob is a separate, smaller interface for the dashboard endpoint response.

DESIGN PRINCIPLES
Principle 11: Any error in this file causes cascading tsc failures across the entire
  project. Always run npx tsc --noEmit after any change. Zero errors required.

GOTCHAS
1. Never create types in random files - add all shared types here.
2. All optional fields use T | null, never undefined. This matches FastAPI JSON.
3. DashboardJob and Job are separate interfaces - do not merge them. They come
   from different endpoints with different response shapes.
4. Named union types (StartMode, TimerStatus, JobStatus) must be updated if the
   backend adds new valid values for these fields.
