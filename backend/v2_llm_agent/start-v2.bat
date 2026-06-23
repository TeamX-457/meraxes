@echo off

cd /d "%~dp0\.."

echo ============================================

echo  Nova AI V2 — Designer UI + Embedded Router

echo  http://127.0.0.1:8006

echo ============================================

echo.

echo  First run may download the memory model (~400MB) — wait for

echo  "Uvicorn running on http://127.0.0.1:8006" then open the URL.

echo.

echo  Local mode: USE_OPENAI=false in .env (no API key needed)

echo  Smarter models: pull-smart-local.bat (Ollama must be running)

echo.

if not exist "ml-env\Scripts\python.exe" (

    echo ERROR: ml-env not found. From AImodel folder run:

    echo   py -3.11 -m venv ml-env

    echo   ml-env\Scripts\pip install -r requirements.txt

    echo   ml-env\Scripts\pip install -r v2_llm_agent\requirements.txt

    pause

    exit /b 1

)

"ml-env\Scripts\python.exe" -m uvicorn v2_llm_agent.main:app --host 0.0.0.0 --port 8006

pause

