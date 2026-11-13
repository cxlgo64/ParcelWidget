@echo off
rem Build "Parcel Widget" for Windows: a folder with Parcel Widget.exe, and a .zip of it.
rem   packaging\build_win.bat   ->  dist\ParcelWidget-<version>-Windows-x64.zip
rem Needs the project venv (install.bat, or: py -3 -m venv .venv ^& .venv\Scripts\pip install -r requirements.txt)
setlocal
cd /d "%~dp0\.."
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo No .venv here: run install.bat first.
  exit /b 1
)
"%PY%" -m pip install -q "pyinstaller>=6" || exit /b 1
"%PY%" packaging\make_icon.py || exit /b 1
if exist build rmdir /s /q build
if exist "dist\Parcel Widget" rmdir /s /q "dist\Parcel Widget"
"%PY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\ParcelWidget-win.spec || exit /b 1

set "VERSION=0"
for /f "tokens=2 delims== " %%v in ('findstr /b "VERSION" packaging\ParcelWidget.spec') do set "VERSION=%%~v"
set "ZIP=dist\ParcelWidget-%VERSION%-Windows-x64.zip"
if exist "%ZIP%" del "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Parcel Widget' -DestinationPath '%ZIP%'" || exit /b 1
echo Built %ZIP%
