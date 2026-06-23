@echo off
title Nova AI V2 — port 8006
cd /d "%~dp0"

echo.
echo   Nova AI V2 + embedded Multi-LLM Router
echo   Open: http://127.0.0.1:8006
echo   (V1 disabled — focus on V2 only)
echo.

if not exist "ml-env\Scripts\python.exe" (
    echo ERROR: ml-env missing in AImodel folder
    pause
    exit /b 1
)

"ml-env\Scripts\python.exe" -m uvicorn v2_llm_agent.main:app --host 0.0.0.0 --port 8006

pause
