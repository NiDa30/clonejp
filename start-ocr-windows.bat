@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Hay cai Python 3.11 tro len tu python.org.
  pause
  exit /b 1
)
if not exist .venv-ocr\Scripts\python.exe (
  py -3 -m venv .venv-ocr
  if errorlevel 1 goto :failed
)
.venv-ocr\Scripts\python.exe -m pip install -r scan_tool\requirements.txt
if errorlevel 1 goto :failed
.venv-ocr\Scripts\python.exe -m streamlit run scan_tool\app.py --server.address 127.0.0.1 --server.maxUploadSize 512 --browser.gatherUsageStats false
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Co loi. Hay kiem tra thong bao phia tren.
pause
exit /b 1
