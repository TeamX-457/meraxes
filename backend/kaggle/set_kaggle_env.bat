@echo off
REM Run this in CMD to set Kaggle token and config dir for the session
set KAGGLE_API_TOKEN=KGAT_8efa1f5d6fda5a8ad7fc0e76e705ad0b
nset KAGGLE_CONFIG_DIR=%~dp0\.kaggle
echo Set KAGGLE_API_TOKEN and KAGGLE_CONFIG_DIR=%KAGGLE_CONFIG_DIR% for this session.
