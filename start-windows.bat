@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Hay cai Python 3.11 hoac moi hon tu python.org, sau do chay lai.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto :failed
.venv\Scripts\python.exe tools\jp101_backup.py
if errorlevel 1 goto :failed
pause
exit /b 0
:failed
echo Co loi. Hay gui thong bao loi, khong gui cookie hoac mat khau.
pause
exit /b 1
