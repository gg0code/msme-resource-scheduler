@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: deploy_hotfix_toolbar.bat
:: Fixes duplicated Auto-Schedule button in the header
::
:: ZIP NAME EXPECTED : hotfix_toolbar.zip
:: Run from          : C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler\
:: ============================================================

set ROOT=%~dp0
set ROOT=%ROOT:~0,-1%
set ZIP=%ROOT%\hotfix_toolbar.zip
set TEMP_DIR=%ROOT%\_deploy_temp_hotfix

echo.
echo ============================================================
echo  MSME Scheduler — Hotfix: SchedulerToolbar duplicate button
echo ============================================================
echo.

if not exist "%ZIP%" (
    echo [ERROR] hotfix_toolbar.zip not found at:
    echo         %ZIP%
    pause
    exit /b 1
)

echo [1/3] Extracting...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TEMP_DIR%' -Force"
if errorlevel 1 ( echo [ERROR] Extraction failed. & pause & exit /b 1 )
echo        Done.
echo.

set ERRORS=0
echo [2/3] Copying file...
call :copy "SchedulerToolbar.tsx" "%ROOT%\frontend\src\scheduler\SchedulerToolbar.tsx"
echo.

echo [3/3] Cleaning up...
rmdir /s /q "%TEMP_DIR%"
echo.

echo ============================================================
if %ERRORS% == 0 (
    echo  SUCCESS: SchedulerToolbar.tsx updated!
) else (
    echo  ERROR: file not copied — check output above.
)
echo ============================================================
echo.
echo NEXT STEP: The frontend dev server hot-reloads automatically.
echo If it doesn't refresh, press Ctrl+S in any .tsx file or
echo restart: cd frontend ^&^& npm run dev
echo.
pause
exit /b 0

:copy
set SRC_NAME=%~1
set DEST_PATH=%~2
for /r "%TEMP_DIR%" %%F in ("%SRC_NAME%") do (
    copy /y "%%F" "%DEST_PATH%" >nul 2>&1
    if errorlevel 1 ( echo   [FAIL]    %SRC_NAME% & set /a ERRORS+=1 ) else ( echo   [OK]      %SRC_NAME% )
    goto :eof
)
echo   [MISSING] %SRC_NAME%
set /a ERRORS+=1
goto :eof
