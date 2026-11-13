@echo off
rem Double-click: installs what the widget needs, makes it start when you sign in, and starts it (Windows).
setlocal
cd /d "%~dp0"

set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD where python >nul 2>nul && set "PYCMD=python"
if not defined PYCMD goto :nopython

echo ==^> Creating the virtual environment (.venv)
%PYCMD% -m venv .venv || goto :fail
echo ==^> Installing what it needs (a few minutes the first time)
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || goto :fail

echo ==^> Making it start when you sign in
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup') + '\Parcel Widget.lnk'); $s.TargetPath = '%CD%\.venv\Scripts\pythonw.exe'; $s.Arguments = '\"%CD%\app.py\" --autostart'; $s.WorkingDirectory = '%CD%'; $s.Save()"

echo ==^> Done. She is starting now; look for the parcel icon near the clock (it may be behind the ^^ arrow).
start "" ".venv\Scripts\pythonw.exe" app.py
timeout /t 5 >nul
exit /b 0

:nopython
echo Python 3 was not found.
echo Install it from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH"), then run this again.
pause
exit /b 1

:fail
echo.
echo Something went wrong (see above).
pause
exit /b 1
