# run_tests.ps1 — Run all backend + frontend tests before committing
# Usage: .\run_tests.ps1
# Exit code 0 = all passed. Non-zero = failures, do NOT commit.

$ErrorActionPreference = "Stop"
$failed = @()

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ZetaOps Copilot - Pre-Commit Tests   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Backend: syntax check all changed Python files ─────────────────────────
Write-Host "[1/5] Python syntax check..." -ForegroundColor Yellow
try {
    $pyFiles = @(
        "backend\app\routers\scheduler_router.py",
        "backend\app\routers\dashboard.py",
        "backend\app\routers\gantt.py",
        "backend\app\routers\jobs.py",
        "backend\app\models\job.py"
    )
    foreach ($f in $pyFiles) {
        python -m py_compile $f
    }
    Write-Host "  PASS: All Python files syntax OK" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: Syntax error detected" -ForegroundColor Red
    $failed += "Python syntax"
}

# ── 2. Backend: Alembic migration check ───────────────────────────────────────
Write-Host "[2/5] Alembic migrations..." -ForegroundColor Yellow
try {
    Push-Location backend
    $heads = alembic heads 2>&1
    if ($heads -match "ERROR") { throw "Alembic heads failed: $heads" }
    $history = alembic history 2>&1
    if ($history -match "ERROR") { throw "Alembic history failed" }
    Write-Host "  PASS: Migrations chain OK" -ForegroundColor Green
    Pop-Location
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
    $failed += "Alembic migrations"
    Pop-Location
}

# ── 3. Backend: pytest ─────────────────────────────────────────────────────────
Write-Host "[3/5] Backend pytest..." -ForegroundColor Yellow
try {
    Push-Location backend
    python -m pytest tests/ -v --tb=short -q 2>&1 | Tee-Object -Variable pytestOut
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
    Write-Host "  PASS: All backend tests passed" -ForegroundColor Green
    Pop-Location
} catch {
    Write-Host "  FAIL: Some backend tests failed" -ForegroundColor Red
    $failed += "Backend pytest"
    Pop-Location
}

# ── 4. Frontend: TypeScript check ─────────────────────────────────────────────
Write-Host "[4/5] TypeScript type check..." -ForegroundColor Yellow
try {
    Push-Location frontend
    $tscOut = npx tsc --noEmit 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host $tscOut -ForegroundColor Red
        throw "TypeScript errors found"
    }
    Write-Host "  PASS: No TypeScript errors" -ForegroundColor Green
    Pop-Location
} catch {
    Write-Host "  FAIL: TypeScript errors" -ForegroundColor Red
    $failed += "TypeScript"
    Pop-Location
}

# ── 5. Frontend: Vitest unit tests ────────────────────────────────────────────
Write-Host "[5/5] Frontend Vitest..." -ForegroundColor Yellow
try {
    Push-Location frontend
    npx vitest run 2>&1 | Tee-Object -Variable vitestOut
    if ($LASTEXITCODE -ne 0) { throw "Vitest failed" }
    Write-Host "  PASS: All frontend tests passed" -ForegroundColor Green
    Pop-Location
} catch {
    Write-Host "  FAIL: Some frontend tests failed" -ForegroundColor Red
    $failed += "Frontend Vitest"
    Pop-Location
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($failed.Count -eq 0) {
    Write-Host "  ALL TESTS PASSED - Safe to commit!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "  FAILED: $($failed -join ', ')" -ForegroundColor Red
    Write-Host "  Fix failures before committing." -ForegroundColor Red
    exit 1
}
