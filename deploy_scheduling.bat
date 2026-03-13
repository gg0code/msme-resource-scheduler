@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: deploy_scheduling.bat
:: Deploys job1prom1.zip files to correct project locations
:: Run from: C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler\
:: Usage:    Double-click or run from project root
:: ============================================================

set ROOT=%~dp0
set ROOT=%ROOT:~0,-1%
set ZIP=%ROOT%\job1prom1.zip
set TEMP_DIR=%ROOT%\_deploy_temp

echo.
echo ============================================================
echo  MSME Resource Scheduler - Scheduling Engine Deployment
echo ============================================================
echo.
echo ROOT : %ROOT%
echo ZIP  : %ZIP%
echo.

:: -- Verify zip exists ----------------------------------------
if not exist "%ZIP%" (
    echo [ERROR] job1prom1.zip not found at:
    echo         %ZIP%
    echo.
    echo Please make sure job1prom1.zip is in:
    echo   C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler\
    pause
    exit /b 1
)

:: -- Extract zip to temp folder -------------------------------
echo [1/4] Extracting zip...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"

powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TEMP_DIR%' -Force"

if errorlevel 1 (
    echo [ERROR] Failed to extract zip.
    pause
    exit /b 1
)
echo        Done.
echo.

:: -- Create destination folders if missing --------------------
echo [2/4] Creating directories (if not exist)...

if not exist "%ROOT%\backend\app\models"          mkdir "%ROOT%\backend\app\models"
if not exist "%ROOT%\backend\app\schemas"         mkdir "%ROOT%\backend\app\schemas"
if not exist "%ROOT%\backend\app\crud"            mkdir "%ROOT%\backend\app\crud"
if not exist "%ROOT%\backend\app\routers"         mkdir "%ROOT%\backend\app\routers"
if not exist "%ROOT%\backend\alembic\versions"    mkdir "%ROOT%\backend\alembic\versions"
if not exist "%ROOT%\backend\scripts"             mkdir "%ROOT%\backend\scripts"
if not exist "%ROOT%\frontend\src\api"            mkdir "%ROOT%\frontend\src\api"
if not exist "%ROOT%\frontend\src\pages"          mkdir "%ROOT%\frontend\src\pages"
if not exist "%ROOT%\frontend\src\components"     mkdir "%ROOT%\frontend\src\components"

echo        Done.
echo.

:: -- Copy files -----------------------------------------------
echo [3/4] Copying files...
echo.
set ERRORS=0

call :copy_file "scheduling.py"                "%ROOT%\backend\app\models\scheduling.py"
call :copy_file "schemas_scheduling.py"        "%ROOT%\backend\app\schemas\scheduling.py"
call :copy_file "crud_scheduling.py"           "%ROOT%\backend\app\crud\scheduling.py"
call :copy_file "router_scheduling.py"         "%ROOT%\backend\app\routers\scheduling.py"
call :copy_file "010_add_scheduling_tables.py" "%ROOT%\backend\alembic\versions\010_add_scheduling_tables.py"
call :copy_file "seed_scheduling.py"           "%ROOT%\backend\scripts\seed_scheduling.py"
call :copy_file "main_updated.py"              "%ROOT%\backend\app\main.py"
call :copy_file "scheduling_api.ts"            "%ROOT%\frontend\src\api\scheduling.ts"
call :copy_file "SchedJobsPage.tsx"            "%ROOT%\frontend\src\pages\SchedJobsPage.tsx"
call :copy_file "SchedStepsPage.tsx"           "%ROOT%\frontend\src\pages\SchedStepsPage.tsx"
call :copy_file "JobPrintPage.tsx"             "%ROOT%\frontend\src\pages\JobPrintPage.tsx"
call :copy_file "App_updated.tsx"              "%ROOT%\frontend\src\App.tsx"
call :copy_file "Layout_updated.tsx"           "%ROOT%\frontend\src\components\Layout.tsx"

echo.

:: -- Cleanup --------------------------------------------------
echo [4/4] Cleaning up temp folder...
rmdir /s /q "%TEMP_DIR%"
echo        Done.
echo.

:: -- Summary --------------------------------------------------
echo ============================================================
if %ERRORS% == 0 (
    echo  SUCCESS: All 13 files deployed!
) else (
    echo  DONE with %ERRORS% issue(s) - check log above.
)
echo ============================================================
echo.
echo NEXT STEPS:
echo.
echo  1. Run DB migration  (from backend\ folder^):
echo        venv\Scripts\activate
echo        alembic upgrade head
echo.
echo  2. Seed XY1 / XY2 test jobs:
echo        venv\Scripts\python.exe scripts\seed_scheduling.py
echo.
echo  3. Install QR package  (from frontend\ folder^):
echo        npm install qrcode @types/qrcode
echo.
echo  4. Restart services:
echo        backend : uvicorn app.main:app --reload --port 8000
echo        frontend: npm run dev
echo.
pause
exit /b 0


:: ---- Subroutine: search temp dir recursively and copy -------
:copy_file
set SRC_NAME=%~1
set DEST_PATH=%~2

echo   Copying %SRC_NAME% ...

for /r "%TEMP_DIR%" %%F in ("%SRC_NAME%") do (
    copy /y "%%F" "%DEST_PATH%" >nul 2>&1
    if errorlevel 1 (
        echo   [FAIL]    %SRC_NAME%
        echo             Could not write to: %DEST_PATH%
        set /a ERRORS+=1
    ) else (
        echo   [DONE]    %SRC_NAME%
        echo             Destination : %DEST_PATH%
        echo.
    )
    goto :eof
)

echo   [MISSING] %SRC_NAME%  ^(not found in zip^)
echo             Expected at: %DEST_PATH%
echo.
set /a ERRORS+=1
goto :eof
