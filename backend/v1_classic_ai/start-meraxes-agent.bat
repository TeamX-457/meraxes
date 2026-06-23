@ECHO OFF
title Meraxes Agent Optimizer (Track 2) - port 8030
cd /d "%~dp0"
call ..\ml-env\Scripts\activate.bat 2>nul
uvicorn meraxes_agent.main:app --host 0.0.0.0 --port 8030 --reload
