# 7z File Encryption Tool v1.1.0

A standalone Windows 11 GUI application for creating AES-256 encrypted 7z archives.

## Download and run

1. Open the repository's **Releases** page and download `7z-encrypt-tool-windows-x64.exe`.
2. Optionally verify the SHA-256 checksum against `SHA256SUMS.txt`.
3. Double-click the EXE. No Python installation, BAT launcher, virtual environment, pip, or administrator rights are required.
4. Select the files, choose an output folder, and wait for compression and integrity verification to finish.

The EXE is a single-file, windowed PyInstaller build. It does not open a persistent console window. The first launch can take a little longer because PyInstaller extracts its bundled runtime to a temporary directory.

## Downloading a build before a tagged release exists

Every successful build workflow uploads a downloadable artifact:

1. Open the repository's **Actions** tab.
2. Select **Build standalone Windows EXE**.
3. Open the latest successful run.
4. Download the artifact named `7z-encrypt-tool-windows-x64-<commit>`.

Workflow artifacts are retained for 30 days. Tagged builds (`v*`) are also attached to a GitHub Release automatically.

## Windows SmartScreen

The EXE is currently not code-signed. Windows may show **Microsoft Defender SmartScreen — Windows protected your PC** or an unknown-publisher warning.

Only consider continuing when the file came from this repository's official Actions artifact or Release and its SHA-256 matches the supplied checksum. In the SmartScreen dialog, choose **More info** and then **Run anyway** if Windows offers that option and your organization permits it. Do not turn off SmartScreen or antivirus protection to run an unverified copy. Managed devices may block unsigned applications; in that case, ask the administrator for an approved or signed build.

## Application behavior

- Creates standard 7z archives with AES-256 encryption and encrypted headers (member names are hidden).
- Generates a random 32-character password and a random 10-character archive name.
- Writes a companion TXT file containing the password and original-to-archive filename mapping.
- Detects duplicate selections, symbolic-link aliases, and filesystem hard links where file identity is available.
- Validates that member names cannot be read without the password, compares the complete archive member list, and checks archive integrity.
- Does not delete, move, or modify original files.
- Prevents a normal window close while encryption or verification is running.

The TXT stores the password in plaintext. Keep it separate from the 7z archive. Cloud-synchronized output folders may upload both files.

## Logs

Application logs are written to:

`%LOCALAPPDATA%\7z-Encrypt-Tool\logs\application.log`

If the application reports an error, include this log when reporting the issue. It may contain local file paths; review it before sharing.

## Build from source (maintainers)

The application is built on GitHub Actions using Windows x64, CPython 3.14, PyInstaller, and the committed `7z-encrypt-tool.spec` plus `pyinstaller_hooks/hook-py7zr.py`.

To reproduce the build locally:

```powershell
py -3.14 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-build\Scripts\python.exe -m PyInstaller --clean --noconfirm 7z-encrypt-tool.spec
.\dist\7z-encrypt-tool.exe --self-test --self-test-output .\self-test.json
```

The build workflow also runs the frozen EXE self-test. It checks the bundled imports and distribution metadata, then creates, password-checks, verifies, and extracts a real encrypted 7z archive.

## Project dependencies

- Runtime: `py7zr==1.1.4` and its declared dependencies.
- Build: `PyInstaller==6.22.3`.

The PyInstaller hook collects py7zr submodules and the runtime codec packages, their native Windows extension binaries, and distribution metadata. The final application is built in windowed one-file mode.
