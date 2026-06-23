@ECHO OFF
title Meraxes v1 Platform - port 8005
cd /d "%~dp0"
call ..\ml-env\Scripts\activate.bat 2>nul
uvicorn main:app --host 0.0.0.0 --port 8005 --reload
