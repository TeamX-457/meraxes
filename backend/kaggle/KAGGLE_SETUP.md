Setup notes — Kaggle API token stored locally in this project

Files created:
- .kaggle/access_token — contains the token string
- set_kaggle_env.ps1 — PowerShell script to set `KAGGLE_API_TOKEN` and `KAGGLE_CONFIG_DIR` for the current session
- set_kaggle_env.bat — CMD script to set the same for Command Prompt sessions

Usage:
- PowerShell (from `AImodel`):
  .\set_kaggle_env.ps1

- CMD (from `AImodel`):
  .\set_kaggle_env.bat

Notes:
- The Kaggle client looks for credentials in `%USERPROFILE%/.kaggle` by default. These scripts set `KAGGLE_CONFIG_DIR` to use the `AImodel\.kaggle` folder for the session.
- On Windows, file permissions differ from Unix; keep this project folder private if you want to keep the token secure.
- To use the token directly in a shell without scripts, set the `KAGGLE_API_TOKEN` environment variable.
