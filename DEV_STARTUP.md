# ZetaOps Copilot — Development Startup Guide
# =============================================
# Run BOTH terminals simultaneously. Backend first, then frontend.
# All checks are listed — skip none.

═══════════════════════════════════════════════════════════════
TERMINAL 1 — BACKEND
═══════════════════════════════════════════════════════════════

cd C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler\backend

# 1. Activate virtual environment
venv\Scripts\activate

# 2. Verify Python version (must be 3.11+ — 3.14 is fine)
python --version

# 3. Check .env exists and has required keys
#    Must contain at minimum:
#      DATABASE_URL=postgresql://user:pass@localhost:5432/zetaops
#      SECRET_KEY=your-secret-key-here
#      ALGORITHM=HS256
#      ACCESS_TOKEN_EXPIRE_MINUTES=30
#      REFRESH_TOKEN_EXPIRE_DAYS=7
#      GROQ_API_KEY=sk-...
#      ANTHROPIC_API_KEY=sk-ant-...  (only needed for generate_docs.py)
type .env

# 4. Check PostgreSQL is running
#    Open pgAdmin OR run:
psql -U postgres -c "SELECT version();"

# 5. Check the DB exists
psql -U postgres -c "\l" | findstr zetaops

# 6. Run Alembic migrations (safe to run multiple times — idempotent)
alembic upgrade head
#    Expected output: Running upgrade ... -> 018
#    If error: check DATABASE_URL in .env

# 7. Verify migration chain is healthy (single head)
alembic heads
#    Must show exactly ONE revision: 018

# 8. Install/verify dependencies
pip install -r requirements.txt --break-system-packages -q

# 9. Run Python syntax check on key files before starting
python -m py_compile app/main.py
python -m py_compile app/routers/jobs.py
python -m py_compile app/services/availability_engine.py
#    No output = all clean

# 10. Start the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

#    Watch for these on startup:
#    ✅ "Application startup complete"
#    ✅ "Auto-advance engine started (15-min interval)"
#    ❌ Any ImportError or AttributeError = fix before proceeding


═══════════════════════════════════════════════════════════════
TERMINAL 2 — FRONTEND
═══════════════════════════════════════════════════════════════

cd C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler\frontend

# 1. Install dependencies (only needed first time or after package.json changes)
npm install

# 2. TypeScript strict mode check — MANDATORY before every dev session
npx tsc --noEmit
#    Must output: (nothing) — zero errors
#    If errors appear: fix them before starting the dev server
#    Common errors and fixes:
#      "Cannot find module '../api/employees'" → change to '../api/api_employees'
#      "Property X does not exist on type Y"   → add field to types_index.ts
#      "Argument of type any"                  → add explicit type annotation

# 3. Check .env.local (or .env) exists with:
#    VITE_API_BASE_URL=http://localhost:8000
#    VITE_API_URL=http://localhost:8000
type .env.local

# 4. Start the dev server
npm run dev

#    Watch for these on startup:
#    ✅ "VITE ready in Xms"
#    ✅ "Local: http://localhost:5173/"
#    ❌ Any "Failed to resolve import" = wrong import path in a .ts/.tsx file


═══════════════════════════════════════════════════════════════
BROWSER CHECKS (after both servers are running)
═══════════════════════════════════════════════════════════════

Open: http://localhost:5173

# 1. Check backend is reachable
#    Open: http://localhost:8000/docs
#    Must show FastAPI Swagger UI with all routers listed

# 2. Register a test tenant (first time only)
#    Go to /register
#    Fill in company name, slug, industry type, email, password
#    Should redirect to /dashboard with demo data loaded

# 3. Check feature flags loaded
#    Open browser DevTools → Network tab
#    Filter: /api/features
#    Should return JSON with all flags

# 4. Check dashboard loads
#    Should show KPI cards and job list
#    If blank: check browser Console for errors

# 5. Check AI Copilot (if flags.ai_copilot = true)
#    Click AI Copilot button bottom-right
#    Should load greeting from /api/ai/greeting


═══════════════════════════════════════════════════════════════
TIGHT CHECKS — run these every time before committing
═══════════════════════════════════════════════════════════════

# Frontend — TypeScript
cd frontend
npx tsc --noEmit
# Zero errors = commit ready

# Backend — import check
cd ../backend
venv\Scripts\activate
python -c "from app.main import app; print('✅ main.py imports clean')"

# Backend — migration chain
alembic heads
# Must show: 018 (head)

# Backend — run tests
pytest tests/test_scheduler.py -v
# 4 tests must pass

# Backend — run skill tests (requires test DB)
pytest tests/test_skills.py -v
# 5 tests must pass (needs TEST_DATABASE_URL in env)


═══════════════════════════════════════════════════════════════
COMMON ERRORS AND FIXES
═══════════════════════════════════════════════════════════════

ERROR: "uvicorn: command not found"
FIX:   venv\Scripts\activate  (activate venv first)

ERROR: "relation 'tenants' does not exist"
FIX:   alembic upgrade head  (migrations not run)

ERROR: "FATAL: password authentication failed"
FIX:   Check DATABASE_URL in backend/.env

ERROR: "Failed to resolve import '../api/employees'"
FIX:   Change to '../api/api_employees' (underscore prefix)

ERROR: "Cannot find module 'groq'"
FIX:   pip install -r requirements.txt --break-system-packages

ERROR: tsc error "Property 'X' does not exist on type 'Job'"
FIX:   Add field X to Job interface in src/types/types_index.ts

ERROR: Frontend shows blank white screen
FIX:   Check browser console for errors
       Check that backend is running on port 8000
       Check VITE_API_BASE_URL in frontend/.env.local

ERROR: AI Copilot shows "temporarily busy"
FIX:   Check GROQ_API_KEY in backend/.env
       Check Groq console for rate limit status


═══════════════════════════════════════════════════════════════
QUICK REFERENCE — PORTS AND URLS
═══════════════════════════════════════════════════════════════

Frontend dev server : http://localhost:5173
Backend API         : http://localhost:8000
Backend API docs    : http://localhost:8000/docs
Backend health      : http://localhost:8000/health (if route exists)
PostgreSQL          : localhost:5432
pgAdmin             : http://localhost:5050 (if installed)
