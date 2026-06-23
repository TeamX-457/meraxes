@echo off
cd /d "%~dp0"
echo Stopping old server on port 8005...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8005" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul
echo Starting V1 Chatbot Platform...
echo Open: http://127.0.0.1:8005
echo.
if exist "..\ml-env\Scripts\python.exe" (
    "..\ml-env\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8005
) else (
    py -3.11 -m uvicorn main:app --host 0.0.0.0 --port 8005
)
pause
