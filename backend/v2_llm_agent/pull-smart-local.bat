@echo off

echo ============================================

echo  Pull smarter LOCAL models for V2 (Ollama)

echo  No OpenAI API needed.

echo ============================================

echo.

echo  Pick based on your RAM (16GB+ recommended for 7b):

echo    qwen2.5:7b     - best balance (general chat)

echo    llama3.1:8b    - strong all-rounder

echo    qwen2.5:14b    - smartest local (needs ~16GB+ RAM, slower on CPU)

echo.

where ollama >nul 2>&1

if errorlevel 1 (

    echo ERROR: Install Ollama from https://ollama.com then run this again.

    pause

    exit /b 1

)

echo Pulling qwen2.5:7b (recommended)...

ollama pull qwen2.5:7b

echo.

echo Pulling llama3.1:8b...

ollama pull llama3.1:8b

echo.

echo Done. Optional smarter model (large download):

echo   ollama pull qwen2.5:14b

echo.

echo Restart V2: start-v2.bat

pause

