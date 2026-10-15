@echo off
rem Builds a new release from the zips in scripts\input into 11e-stratagems\<version>\
rem and adds it to 11e-stratagems\versions.json. It asks for the version number as it goes.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The tool isn't set up yet. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -I scripts\build_release.py
set "RESULT=%ERRORLEVEL%"

echo.
if not "%RESULT%"=="0" echo Nothing new was published. Read the messages above.
pause
exit /b %RESULT%
