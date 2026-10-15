@echo off
rem Pulls the stratagem card zips for every faction into scripts\input.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The tool isn't set up yet. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -I scripts\pull_datacards.py scripts\input --all
set "RESULT=%ERRORLEVEL%"

echo.
if "%RESULT%"=="0" (
    echo Done. The zips are in scripts\input
) else (
    echo Finished with problems. Read the messages above.
)
pause
exit /b %RESULT%
