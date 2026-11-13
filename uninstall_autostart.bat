@echo off
rem Stop the widget from starting when you sign in.
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Parcel Widget.lnk" 2>nul
echo It no longer starts by itself. Your data stays in %APPDATA%\ParcelWidget
pause
