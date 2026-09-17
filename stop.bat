:: run.bat으로 실행한 Backend, Frontend와 로컬 Ollama 프로세스를 종료합니다.
:: 다른 용도의 Python/Node 프로세스는 종료하지 않고 개발 포트의 프로세스만 확인합니다.

@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 > nul
title Medical AI Project Stopper

echo ========================================
echo   Medical AI Project Stop
echo ========================================
echo.

set "STOPPED_ANY=0"

REM Close the terminal trees created by run.bat first.
call :stop_window "FastAPI Backend"
call :stop_window "React Frontend"

REM Stop only expected executable types if a development port is still occupied.
call :stop_port 8000 python.exe Backend
call :stop_port 8000 pythonw.exe Backend
call :stop_port 5173 node.exe Frontend

REM Stop Ollama desktop/server/runner processes used by the local LLM provider.
call :stop_image "ollama app.exe" "Ollama desktop app"
call :stop_image "ollama.exe" "Ollama server"
call :stop_image "ollama_llama_server.exe" "Ollama model runner"

echo.
if "%STOPPED_ANY%"=="1" (
    echo [OK] Related development processes were stopped.
) else (
    echo [INFO] No running related process was found.
)

call :report_port 8000 Backend
call :report_port 5173 Frontend

echo.
if /i not "%~1"=="--no-pause" pause
exit /b 0

:stop_window
taskkill /FI "WINDOWTITLE eq %~1*" /T /F > nul 2>&1
if not errorlevel 1 (
    echo [STOPPED] %~1 window and child processes
    set "STOPPED_ANY=1"
)
exit /b 0

:stop_port
set "TARGET_PORT=%~1"
set "EXPECTED_IMAGE=%~2"
set "SERVICE_NAME=%~3"
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":!TARGET_PORT! .*LISTENING"') do (
    call :stop_pid_if_expected "%%P" "!EXPECTED_IMAGE!" "!TARGET_PORT!" "!SERVICE_NAME!"
)
exit /b 0

:stop_pid_if_expected
set "TARGET_PID=%~1"
set "EXPECTED_IMAGE=%~2"
set "TARGET_PORT=%~3"
set "SERVICE_NAME=%~4"
set "ACTUAL_IMAGE="
for /f "tokens=1 delims=," %%I in ('tasklist /FI "PID eq !TARGET_PID!" /FO CSV /NH 2^> nul') do set "ACTUAL_IMAGE=%%~I"

if /i "!ACTUAL_IMAGE!"=="!EXPECTED_IMAGE!" (
    taskkill /PID !TARGET_PID! /T /F > nul 2>&1
    if not errorlevel 1 (
        echo [STOPPED] !SERVICE_NAME! !ACTUAL_IMAGE! PID !TARGET_PID! on port !TARGET_PORT!
        set "STOPPED_ANY=1"
    )
) else if defined ACTUAL_IMAGE (
    echo [SKIPPED] Port !TARGET_PORT! belongs to !ACTUAL_IMAGE! PID !TARGET_PID!, not !EXPECTED_IMAGE!.
)
exit /b 0

:stop_image
taskkill /IM "%~1" /T /F > nul 2>&1
if not errorlevel 1 (
    echo [STOPPED] %~2
    set "STOPPED_ANY=1"
)
exit /b 0

:report_port
netstat -ano -p tcp | findstr /R /C:":%~1 .*LISTENING" > nul 2>&1
if errorlevel 1 (
    echo [OK] %~2 port %~1 is free.
) else (
    echo [WARN] %~2 port %~1 is still in use. Review the skipped process above.
)
exit /b 0
