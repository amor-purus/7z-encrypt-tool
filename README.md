# 7z File Encryption Tool v1.0.2

## Windows 11 startup
1. Close any previously opened console windows for this tool.
2. Create a **new, empty folder** (for example, `Desktop\\7z_encrypt_v102`). Do not reuse the old extracted folder.
3. Extract all files from this ZIP into that new folder.
4. Double-click `start.bat`.
5. Confirm that the console reports `Base runtime: 3.14.10` (or another 3.14.x version), `Private runtime: 3.14.x`, and `Architecture: 64 bit`.
6. On first launch, the launcher installs prebuilt Python wheels only. C++ source compilation is disabled.

## Runtime selection
The launcher uses the exact per-user install path shown by the Python 3.14 installer:
`%LOCALAPPDATA%\\Programs\\Python\\Python314\\python.exe`

It does not call `py -3`, `py -3.14`, or a PATH-resolved `python.exe`. It creates a fresh `.venv314` directory, so old `.venv` folders from v1.0/v1.0.1 cannot be reused accidentally. It verifies the interpreter version and architecture before calling pip.

The install command uses `--only-binary=:all:`. If a compatible prebuilt wheel is unavailable, setup stops with an error rather than attempting a local C++ build. For the regular 64-bit CPython 3.14 runtime, PyPI lists Windows x86-64 wheels for inflate64, pybcj, and pyppmd.

## App behavior
- Select one or multiple files; the output-folder picker appears next.
- Creates one 7z archive with encrypted headers (file and folder names hidden).
- Generates a random 32-character password and a random 10-character archive name.
- Writes a matching TXT password record.
- Original files are not deleted, moved, or modified.

## Security note
The TXT contains the password in plaintext. Keep it separate from the 7z archive.

## Verification boundary
The launcher source was statically checked for ASCII/CRLF formatting, explicit Python path selection, version/architecture checks, isolated `.venv314`, and wheel-only installation. The archive app's syntax and simulated workflow checks from v1.0 remain passed. Real 7z encryption and Windows end-to-end behavior still need to be tested locally with non-sensitive sample files.
