:: 최초 수동 설정 완료 후 Backend와 Frontend 개발 서버를 한 번에 실행합니다.
:: 패키지 설치는 수행하지 않으며 Python 3.12 가상환경과 node_modules가 필요합니다.

@echo off
setlocal
chcp 65001 > nul
title Medical AI Project Launcher

set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%backend"
set "FRONTEND_DIR=%PROJECT_ROOT%frontend"
set "VENV_ACTIVATE=%BACKEND_DIR%\.venv\Scripts\activate.bat"
set "VENV_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "PYTHONPATH=%PROJECT_ROOT%"

echo ========================================
echo   Medical AI Project Start
echo ========================================
echo.

REM Validate everything before opening either development server.
if not exist "%PROJECT_ROOT%.env" (
    echo [ERROR] Root environment file was not found:
    echo         "%PROJECT_ROOT%.env"
    echo.
    echo Create it once with: Copy-Item .env.example .env
    echo Then edit the copied file with the local development values.
    pause
    exit /b 1
)

if not exist "%VENV_ACTIVATE%" (
    echo [ERROR] Backend virtual environment was not found:
    echo         "%BACKEND_DIR%\.venv"
    echo.
    echo Create it with: py -3.12 -m venv backend\.venv
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Python executable was not found in backend\.venv:
    echo         "%VENV_PYTHON%"
    echo.
    echo Recreate it with: py -3.12 -m venv backend\.venv
    pause
    exit /b 1
)

"%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" > nul 2>&1
if errorlevel 1 (
    echo [ERROR] backend\.venv must use Python 3.12.
    echo Current virtual environment version:
    "%VENV_PYTHON%" --version
    echo.
    echo Recreate backend\.venv with: py -3.12 -m venv backend\.venv
    pause
    exit /b 1
)

"%VENV_PYTHON%" -c "import ai.ocr, fastapi, uvicorn, docx, pptx, httpx; import google.genai" > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Required Backend packages are not installed.
    echo.
    echo Install them with:
    echo backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] Frontend package.json was not found:
    echo         "%FRONTEND_DIR%\package.json"
    pause
    exit /b 1
)

where npm.cmd > nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm was not found. Install Node.js and try again.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules\" (
    echo [ERROR] Frontend packages are not installed:
    echo         "%FRONTEND_DIR%\node_modules"
    echo.
    echo Install them with: cd frontend ^&^& npm.cmd install
    pause
    exit /b 1
)

echo [1/2] Starting Backend with backend\.venv...
start "FastAPI Backend" /D "%BACKEND_DIR%" cmd.exe /k "call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --reload"

echo [2/2] Starting Frontend with npm run dev...
start "React Frontend" /D "%FRONTEND_DIR%" cmd.exe /k "npm.cmd run dev"

echo.
echo ========================================
echo   Backend / Frontend launched
echo ========================================
echo.
echo Backend      : http://localhost:8000
echo Swagger Docs : http://localhost:8000/docs
echo Frontend     : http://localhost:5173
echo Admin Page   : http://localhost:5173/admin
echo.
echo Each server is running in its own terminal window.
echo Close those windows or press Ctrl+C in each one to stop the servers.
echo.
pause

endlocal
