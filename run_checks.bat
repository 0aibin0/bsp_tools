@echo off
REM One-key self check wrapper.
REM Real logic lives in run_checks.py -- this file stays ASCII on purpose:
REM cmd.exe reads .bat in the GBK code page and would mangle Chinese text.
REM
REM   run_checks.bat            offline checks only (fast)
REM   run_checks.bat device     also run the checks that need a device attached

setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" run_checks.py %*
exit /b %errorlevel%
