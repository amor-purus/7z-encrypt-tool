@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM Use the exact per-user path shown by the Python 3.14 installer.
set "BASE_PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
set "VENV=%~dp0.venv314"
set "PYTHON_EXE=%VENV%\Scripts\python.exe"

echo ============================================================
echo 7z File Encryption Tool v1.0.2
echo ============================================================
echo.
echo Required base interpreter:
echo %BASE_PY%
echo.

if not exist "%BASE_PY%" (
    echo [ERROR] Python 3.14 was not found at the installer's default path:
    echo %BASE_PY%
    echo Please confirm Python 3.14.10 was installed to the default location.
    echo Then run this file again.
    pause
    exit /b 1
)

REM Verify the exact executable before creating any environment.
"%BASE_PY%" -c "import sys,struct; print('Base runtime:',sys.version); print('Executable:',sys.executable); print('Architecture:',struct.calcsize('P')*8,'bit'); sys.exit(0 if sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo.
    echo [ERROR] The executable above is not 64-bit CPython 3.14.
    pause
    exit /b 1
)

echo.
REM Dedicated .venv314 keeps any old .venv created by earlier versions unused.
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 else 1)" >nul 2>nul
    if errorlevel 1 (
        echo Removing incompatible .venv314...
        rmdir /s /q "%VENV%"
    )
)

if not exist "%PYTHON_EXE%" (
    echo Creating a clean Python 3.14 virtual environment...
    "%BASE_PY%" -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Could not create the private environment.
        pause
        exit /b 1
    )
)

echo.
echo Verifying the private runtime:
"%PYTHON_EXE%" -c "import sys,struct; print('Private runtime:',sys.version); print('Executable:',sys.executable); print('Architecture:',struct.calcsize('P')*8,'bit'); sys.exit(0 if sys.version_info[:2] == (3,14) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo [ERROR] Private runtime verification failed. No installation was attempted.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -c "import py7zr, Cryptodome" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Installing prebuilt Python 3.14 wheels only.
    echo Source builds and C++ compilation are disabled.
    "%PYTHON_EXE%" -m pip install --disable-pip-version-check --upgrade pip
    if errorlevel 1 (
        echo [ERROR] Could not update pip. Check the internet connection.
        pause
        exit /b 1
    )
    "%PYTHON_EXE%" -m pip install --disable-pip-version-check --only-binary=:all: "py7zr==1.1.4" pycryptodomex
    if errorlevel 1 (
        echo.
        echo [ERROR] A prebuilt wheel could not be installed for this exact runtime.
        echo The log above should show cp314 wheel tags, never cp315.
        pause
        exit /b 1
    )
)

"%PYTHON_EXE%" -c "import sys,py7zr,Cryptodome; print('READY:',sys.version.split()[0], 'py7zr',py7zr.__version__, 'at',sys.executable)"
if errorlevel 1 (
    echo [ERROR] Encryption component import check failed.
    pause
    exit /b 1
)

echo.
echo Starting the application...
"%PYTHON_EXE%" "%~dp0main.py"
if errorlevel 1 (
    echo The application exited with an error. Please capture this window.
    pause
)
endlocal
