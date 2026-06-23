@echo off
title AImodel - V1 + V2 + Multi-LLM Router
cd /d "%~dp0"

echo ============================================
echo  Starting all services (separate windows)
echo ============================================
echo  V1 Chatbot:     http://127.0.0.1:8005
echo  V2 Agent:       http://127.0.0.1:8006
echo  Multi-LLM Router http://127.0.0.1:8020  ^<-- YOUR ROUTER
echo ============================================
echo.

if not exist "ml-env\Scripts\python.exe" (
    echo ERROR: Run from AImodel folder with ml-env installed.
    pause
    exit /b 1
)

start "V1 Chatbot" cmd /k "cd /d %~dp0v1_classic_ai && ..\ml-env\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8005"
timeout /t 2 /nobreak >nul
start "V2 Agent" cmd /k "cd /d %~dp0 && ml-env\Scripts\python.exe -m uvicorn v2_llm_agent.main:app --host 127.0.0.1 --port 8006"
timeout /t 2 /nobreak >nul
start "LLM Router" cmd /k "cd /d %~dp0llm_router && ..\ml-env\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8020"

echo.
echo Open in browser: http://127.0.0.1:8020
echo.
pause
