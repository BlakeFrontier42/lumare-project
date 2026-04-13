@echo off
REM ─── Lumare launcher ──────────────────────────────────────────
REM Starts the FastAPI backend, the Next.js frontend, then opens
REM the app in the default browser. Close either window to stop it.

setlocal
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║          LUMARE  -  STARTING UP          ║
echo  ╚══════════════════════════════════════════╝
echo.

REM Free port 8000 if a stale backend is bound
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo  Killing stale backend on PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

REM Free port 3000 if a stale frontend is bound
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo  Killing stale frontend on PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

REM Clear corrupt Next.js cache (OneDrive sync sometimes breaks it)
if exist "%PROJECT_DIR%frontend\.next" (
    echo  Clearing Next.js cache...
    rmdir /s /q "%PROJECT_DIR%frontend\.next" >nul 2>&1
)

echo  Launching backend  (FastAPI on :8000)...
start "Lumare Backend"  cmd /k "cd /d "%PROJECT_DIR%" && python -m uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload"

echo  Launching frontend (Next.js on :3000)...
start "Lumare Frontend" cmd /k "cd /d "%PROJECT_DIR%frontend" && npm run dev"

echo.
echo  Waiting for frontend to come online...
:wait_loop
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://localhost:3000 -UseBasicParsing -TimeoutSec 1).StatusCode } catch { 0 }" > "%TEMP%\lumare_status.txt"
set /p STATUS=<"%TEMP%\lumare_status.txt"
del "%TEMP%\lumare_status.txt" >nul 2>&1
if not "%STATUS%"=="200" goto wait_loop

echo  Frontend is live - opening browser.
start "" "http://localhost:3000"

echo.
echo  ──────────────────────────────────────────
echo   Lumare is running.
echo   Backend : http://localhost:8000
echo   Frontend: http://localhost:3000
echo  ──────────────────────────────────────────
echo   Close the Backend / Frontend windows to stop.
echo.
timeout /t 5 >nul
endlocal
exit
