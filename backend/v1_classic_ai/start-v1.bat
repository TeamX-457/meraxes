@echo off
cd /d "%~dp0"
echo Starting V1 Chatbot Platform...
echo Dashboard: http://127.0.0.1:8005
echo.
if exist "..\ml-env\Scripts\python.exe" (
    "..\ml-env\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8005
) else if exist "venv311\Scripts\python.exe" (
    "venv311\Scripts\python.exe" -m pip install fastapi uvicorn sentence-transformers faiss-cpu torch scikit-learn -q
    "venv311\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8005
) else (
    py -3.11 -m pip install fastapi uvicorn sentence-transformers faiss-cpu torch scikit-learn -q
    py -3.11 -m uvicorn main:app --host 0.0.0.0 --port 8005
)
pause
