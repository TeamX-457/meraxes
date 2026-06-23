@echo off

title Restart Nova V2

cd /d "%~dp0"



echo Stopping anything on port 8006...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8006" ^| findstr LISTENING') do (

    taskkill /F /PID %%a >nul 2>&1

)

ping -n 3 127.0.0.1 >nul



echo Starting Nova V2 on http://127.0.0.1:8006

start "Nova V2" cmd /k "ml-env\Scripts\python.exe -m uvicorn v2_llm_agent.main:app --host 0.0.0.0 --port 8006"



echo.

echo Open http://127.0.0.1:8006 and press Ctrl+F5

echo Silent training + Ollama export load automatically from .env

pause

