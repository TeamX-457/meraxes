# Run this in PowerShell to set Kaggle token and config dir for the session
$env:KAGGLE_API_TOKEN = 'KGAT_8efa1f5d6fda5a8ad7fc0e76e705ad0b'
$env:KAGGLE_CONFIG_DIR = Join-Path $PSScriptRoot '.kaggle'
Write-Output "Set KAGGLE_API_TOKEN and KAGGLE_CONFIG_DIR=$env:KAGGLE_CONFIG_DIR for this session."
