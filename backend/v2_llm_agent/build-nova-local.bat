@echo off

cd /d "%~dp0\.."



echo ============================================

echo  Build Nova local model from V2 chat export

echo  Requires Ollama: https://ollama.com

echo ============================================

echo.



where ollama >nul 2>&1

if errorlevel 1 (

    echo ERROR: ollama not found in PATH.

    echo Install Ollama, then run this again.

    pause

    exit /b 1

)



if not exist "ml-env\Scripts\python.exe" (

    echo ERROR: ml-env not found in AImodel folder.

    pause

    exit /b 1

)



echo Writing Modelfile from v2_llm_agent\data\ollama_finetune.jsonl ...

"ml-env\Scripts\python.exe" -c "from v2_llm_agent.silent_trainer import run_ollama_build_now; import json; print(json.dumps(run_ollama_build_now(force_create=True), indent=2))"



echo.

echo Done. Use tier=Local in Nova UI, or set OLLAMA_MODEL=nova-v2-learned in .env

pause

