@echo off
rem One-time setup: makes a private Python environment in .venv and installs what the tools need.
rem Safe to run again (e.g. after requirements.txt changes).
setlocal
cd /d "%~dp0"

rem Find a real Python. The Microsoft Store "python" shortcut fails this test, which is what we want.
set "PY="
python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    echo.
    echo Python is not installed, or Windows can't find it.
    echo.
    echo Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" on the first screen of the installer.
    echo See "How to use the tool" in README.md for step-by-step help.
    echo Then close this window and run setup.bat again.
    goto :fail
)

%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 (
    echo.
    echo Your Python is too old. Please install the latest version from https://www.python.org/downloads/
    echo See "How to use the tool" in README.md.
    goto :fail
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the .venv folder...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
)

echo Installing Python packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :fail

echo Installing the Chromium browser used by the pull tool (this can take a few minutes)...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :fail

echo.
echo Setup finished. You can now run pull_all.bat.
pause
exit /b 0

:fail
echo.
echo Setup did NOT finish. Read the messages above.
pause
exit /b 1
