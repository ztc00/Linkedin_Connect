@echo off
setlocal enabledelayedexpansion

echo.
echo   LinkedIn Prospect Intelligence — Setup
echo   -----------------------------------------
echo.

:: Check Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo   X Node.js not found. Install it from https://nodejs.org ^(v18+^)
    exit /b 1
)
for /f "tokens=*" %%i in ('node -v') do echo   + Node.js %%i

:: Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo   X Python 3 not found. Install it from https://python.org
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo   + Python %%i

:: Install frontend dependencies
echo.
echo   Installing frontend dependencies...
cd app && npm install && cd ..
echo   + Frontend ready

:: Create Python venv and install backend deps
echo.
echo   Setting up Python environment...
python -m venv .venv
call .venv\Scripts\activate.bat
pip install --quiet fastapi uvicorn anthropic python-dotenv httpx
echo   + Backend ready

:: Check for Connections.csv
echo.
if exist "Connections.csv" (
    echo   + Connections.csv found
    copy /Y Connections.csv app\public\Connections.csv >nul
    echo   + Copied to app\public\
) else if exist "app\public\Connections.csv" (
    echo   + Connections.csv found in app\public\
    copy /Y app\public\Connections.csv Connections.csv >nul
    echo   + Copied to project root
) else (
    echo   X Connections.csv not found!
    echo     Drop it in this folder and run setup.bat again.
    echo.
    echo     How to get it:
    echo     1. linkedin.com ^> Settings ^> Data Privacy ^> Get a copy of your data
    echo     2. Request full archive ^> wait for email ^> download zip
    echo     3. Find Connections.csv inside the zip
    exit /b 1
)

:: Check for API key
echo.
if defined ANTHROPIC_API_KEY (
    echo   + ANTHROPIC_API_KEY is set
) else (
    echo   X ANTHROPIC_API_KEY not set
    echo     Run: set ANTHROPIC_API_KEY=sk-ant-...
    echo     Get a key at: console.anthropic.com ^> API Keys
    exit /b 1
)

:: Client profile setup
echo.
if exist "client_config.json" (
    echo   + client_config.json already exists — skipping profile setup
) else (
    echo   -----------------------------------------
    echo   Client Profile Setup
    echo   -----------------------------------------
    echo.
    echo   I need to know a bit about you so the AI can score and
    echo   write outreach messages tailored to your goals.
    echo.

    set /p CLIENT_NAME="  Your name: "
    echo.

    echo   Q1: What job titles represent your ideal prospect —
    set /p Q1="      the people who could hire you or buy from you? "
    echo.

    echo   Q2: What industries or types of companies do you target?
    set /p Q2="      Anything that makes someone extra interesting? "
    echo.

    echo   Q3: How would you describe your communication voice?
    set /p Q3="      (e.g. casual, formal, direct, friendly^) "
    echo.

    echo   Q4: What's the ideal next step after someone reads your message?
    set /p Q4="      (e.g. book a call, set up a demo^) "
    echo.

    (
        echo {
        echo   "client_name": "!CLIENT_NAME!",
        echo   "q1_ideal_prospects": "!Q1!",
        echo   "q2_industries_and_signals": "!Q2!",
        echo   "q3_voice": "!Q3!",
        echo   "q4_cta": "!Q4!"
        echo }
    ) > client_config.json

    echo   + Saved to client_config.json
)

echo.
echo   -----------------------------------------
echo   + All prerequisites met!
echo.
echo   Next steps:
echo     1. cd app ^&^& npm run generate ^&^& cd ..   (score all connections, ~5 min)
echo     2. cd app ^&^& npm run dev                   (start frontend — Terminal 1)
echo     3. .venv\Scripts\activate ^&^& python backend.py   (start backend — Terminal 2)
echo     4. python enrichment_service.py              (optional — Terminal 3)
echo.
echo   The 'Ranked List' tab shows pre-scored prospects.
echo   The 'Ask My Network' tab uses Claude AI to search all your connections intelligently.
echo   With the enrichment service running, it also fetches LinkedIn profiles for better results.
echo.
