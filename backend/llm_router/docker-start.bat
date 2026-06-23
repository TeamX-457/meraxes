@echo off
cd /d "%~dp0"
echo Building and starting Multi-LLM Router on http://127.0.0.1:8020
docker compose up --build -d
echo.
echo Test: curl http://127.0.0.1:8020/health
echo UI:  http://127.0.0.1:8020
echo Logs: docker compose logs -f
pause
