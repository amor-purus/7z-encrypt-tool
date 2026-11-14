@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "BASE_PY="
set "VENV=%~dp0.venv314"
set "PYTHON_EXE=%VENV%\Scripts\python.exe"
set "PYTHONW_EXE=%VENV%\Scripts\pythonw.exe"

REM Support the traditional installer, Python Install Manager, and common all-user paths.
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "BASE_PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined BASE_PY if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "BASE_PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined BASE_PY if exist "%ProgramFiles%\Python314\python.exe" set "BASE_PY=%ProgramFiles%\Python314\python.exe"
if not defined BASE_PY if exist "%ProgramFiles%\Python 3.14\python.exe" set "BASE_PY=%ProgramFiles%\Python 3.14\python.exe"

echo ============================================================
echo 7z File Encryption Tool v1.0.3
echo ============================================================
echo.

if not defined BASE_PY (
    echo [ERROR] A 64-bit CPython 3.14 installation was not found.
    echo Supported locations include:
    echo   %%LOCALAPPDATA%%\Programs\Python\Python314
    echo   %%LOCALAPPDATA%%\Python\pythoncore-3.14-64
    echo   %%ProgramFiles%%\Python314
    echo Install 64-bit CPython 3.14, then run this file again.
    pause
    exit /b 1
)

echo Base interpreter:
echo %BASE_PY%
echo.

REM Verify CPython, the required minor version, and 64-bit architecture.
"%BASE_PY%" -c "import sys,struct; print('Base runtime:',sys.version); print('Executable:',sys.executable); print('Architecture:',struct.calcsize('P')*8,'bit'); sys.exit(0 if sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo.
    echo [ERROR] The selected interpreter is not 64-bit CPython 3.14.
    pause
    exit /b 1
)

for /f "delims=" %%P in ('"%BASE_PY%" -c "import sys; print(sys.base_prefix)"') do set "BASE_PREFIX=%%P"
if not defined BASE_PREFIX (
    echo [ERROR] Could not determine the base Python installation directory.
    pause
    exit /b 1
)

REM Rebuild a stale or partial virtual environment instead of mixing runtimes.
set "REBUILD_VENV=0"
if exist "%VENV%\" (
    if not exist "%PYTHON_EXE%" set "REBUILD_VENV=1"
    if "%REBUILD_VENV%"=="0" (
        "%PYTHON_EXE%" -c "import pathlib,sys,struct; base=pathlib.Path(sys.argv[1]).resolve(); env=pathlib.Path(sys.argv[2]).resolve(); ok=sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 and sys.prefix != sys.base_prefix and pathlib.Path(sys.prefix).resolve() == env and pathlib.Path(sys.base_prefix).resolve() == base; sys.exit(0 if ok else 1)" "%BASE_PREFIX%" "%VENV%" >nul 2>nul
        if errorlevel 1 set "REBUILD_VENV=1"
    )
)

if "%REBUILD_VENV%"=="1" (
    echo Removing an incompatible or incomplete .venv314...
    rmdir /s /q "%VENV%"
    if exist "%VENV%\" (
        echo [ERROR] Could not remove the old .venv314 directory.
        echo Close any running Python processes using this folder, then retry.
        pause
        exit /b 1
    )
)

if not exist "%PYTHON_EXE%" (
    echo Creating a private Python 3.14 virtual environment...
    "%BASE_PY%" -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Could not create the private environment.
        pause
        exit /b 1
    )
)

echo.
echo Verifying the private runtime:
"%PYTHON_EXE%" -c "import pathlib,sys,struct; base=pathlib.Path(sys.argv[1]).resolve(); env=pathlib.Path(sys.argv[2]).resolve(); print('Private runtime:',sys.version); print('Executable:',sys.executable); print('Architecture:',struct.calcsize('P')*8,'bit'); ok=sys.implementation.name == 'cpython' and sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 and sys.prefix != sys.base_prefix and pathlib.Path(sys.prefix).resolve() == env and pathlib.Path(sys.base_prefix).resolve() == base; sys.exit(0 if ok else 1)" "%BASE_PREFIX%" "%VENV%"
if errorlevel 1 (
    echo [ERROR] Private runtime verification failed. No dependency installation was attempted.
    pause
    exit /b 1
)

REM Check the exact py7zr release, not merely whether the module can be imported.
"%PYTHON_EXE%" -c "import sys,py7zr; from Cryptodome.Cipher import AES; sys.exit(0 if py7zr.__version__ == '1.1.4' else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Installing compatible prebuilt wheels only.
    echo Source builds and local C++ compilation are disabled.
    "%PYTHON_EXE%" -m pip install --disable-pip-version-check --only-binary=:all: --upgrade pip
    if errorlevel 1 (
        echo [ERROR] Could not update pip. Check the internet connection.
        pause
        exit /b 1
    )
    "%PYTHON_EXE%" -m pip install --disable-pip-version-check --only-binary=:all: --upgrade --force-reinstall "py7zr==1.1.4" pycryptodomex
    if errorlevel 1 (
        echo.
        echo [ERROR] A required prebuilt wheel could not be installed.
        echo The log above should show cp314-compatible wheels, never cp315.
        pause
        exit /b 1
    )
)

echo.
echo Final dependency check:
"%PYTHON_EXE%" -c "import sys,py7zr; from Cryptodome.Cipher import AES; print('READY:',sys.version.split()[0],'py7zr',py7zr.__version__,'at',sys.executable); sys.exit(0 if py7zr.__version__ == '1.1.4' else 1)"
if errorlevel 1 (
    echo [ERROR] The required encryption components are not ready.
    pause
    exit /b 1
)

if not exist "%PYTHONW_EXE%" (
    echo [ERROR] pythonw.exe is missing from the private environment.
    pause
    exit /b 1
)

echo.
echo Launching the GUI without a persistent console window...
start "" "%PYTHONW_EXE%" "%~dp0main.py"
if errorlevel 1 (
    echo [ERROR] Could not launch the GUI.
    pause
    exit /b 1
)
endlocal
exit /b 0
