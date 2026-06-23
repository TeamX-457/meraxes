@echo off
cd /d "%~dp0"
echo Multi-LLM Router: http://127.0.0.1:8020
echo OpenAI-compatible: http://127.0.0.1:8020/v1/chat/completions
if exist "..\ml-env\Scripts\python.exe" (
    "..\ml-env\Scripts\pip.exe" install -q -r requirements.txt
    "..\ml-env\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8020
) else (
    pip install -q -r requirements.txt
    python -m uvicorn main:app --host 0.0.0.0 --port 8020
)
pause
