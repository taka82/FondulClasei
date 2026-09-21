@echo off
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
echo Fondul clasei - http://127.0.0.1:5000
.venv\Scripts\python.exe app.py
