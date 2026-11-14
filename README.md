# 7z File Encryption Tool v1.2.0

A standalone Windows 11 GUI application for creating AES-256 encrypted 7z archives from files, folders, or a mixed selection.

## Download and run

1. Open the repository's **Releases** page and download `7z-encrypt-tool-windows-x64.exe`.
2. Verify its SHA-256 against `SHA256SUMS.txt`.
3. Double-click the EXE. No Python installation, BAT launcher, virtual environment, pip, or administrator rights are required.
4. Add files and/or folders to the queue, then click **Start encryption** and choose an output folder.
5. Wait for compression and integrity verification to finish.

The EXE is a single-file, windowed PyInstaller build. It does not open a persistent console window. The first launch can take a little longer because PyInstaller extracts its bundled runtime to a temporary directory.

## Selecting files and folders

- **Add files** opens the native multi-select file picker; select one or more files at once.
- **Add folder** adds one folder. Click it again to add more folders.
- **Remove selected** removes the highlighted queue entries. **Clear** empties the queue.
- The queue can contain only folders or a mixture of files and folders.
- Selecting a parent folder automatically subsumes any separately selected files or subfolders inside it, preventing duplicate packaging.
- The output folder must be outside every selected source folder. The application blocks an output folder that is the source itself or one of its descendants, avoiding recursive inclusion of the archive being written.

Each selected folder is stored under a top-level archive path and includes its nested directories, files, and empty directories. Conflicting names are disambiguated using parent-folder names or a numeric suffix. The companion TXT identifies each entry as a file or folder and records its exact path inside the archive.

## Password-record design decision

The companion TXT intentionally stores the generated password as plaintext. This is an accepted product requirement, not a defect or an item for routine remediation. Do not remove, encrypt, obscure, relocate, or repeatedly flag this behavior unless the owner explicitly changes the requirement. See [Decision 0001](docs/decisions/0001-plaintext-password-companion-file.md).

## Unsigned releases and SHA-256 verification

The project intentionally does not purchase or use a trusted Authenticode publisher certificate. GitHub Releases therefore contain unsigned Windows EXE files. This avoids a recurring code-signing subscription and its identity-validation and account-maintenance requirements.

Windows may display an unknown-publisher or Microsoft Defender SmartScreen warning when launching the EXE. This is expected for an unsigned release; it does not by itself mean the build or self-tests failed.

Each release includes `SHA256SUMS.txt`, generated from the exact EXE attached to that Release. Compare the downloaded file's SHA-256 with that digest to detect download corruption or differences. A checksum published alongside the executable does not independently prove publisher identity or authenticate the Release page. The build metadata in `BUILD-INFO.txt` explicitly records that Authenticode signing was not performed. See [CODE_SIGNING.md](CODE_SIGNING.md) for the project's code-signing decision.

## Downloading a CI build before a tagged release exists

1. Open the repository's **Actions** tab.
2. Select **Build standalone Windows EXE**.
3. Open the latest successful run.
4. Download the artifact named `7z-encrypt-tool-windows-x64-<commit>`.

CI artifacts are retained for 30 days. Release and CI EXE files are both unsigned; the Release includes the checksum and build provenance files.

## Application behavior

- Creates standard 7z archives with AES-256 encryption and encrypted headers (member names are hidden).
- Generates a random 32-character password and a random 10-character archive name.
- Writes a companion TXT containing the password and original-to-archive path mappings, labeling folders as `[文件夹]`.
- Detects duplicate selections, symbolic-link aliases, and filesystem hard links where file identity is available.
- Preserves nested folders and empty directories and verifies the complete expected archive member set.
- Confirms that member names cannot be read without the password and runs the archive integrity check.
- Does not delete, move, or modify original files.
- Prevents a normal window close while encryption or verification is running.

## Logs

Application logs are written to:

`%LOCALAPPDATA%\7z-Encrypt-Tool\logs\application.log`

If the application reports an error, include this log when reporting the issue. It may contain local file paths; review it before sharing.

## Build from source (maintainers)

The canonical build uses Windows Server 2025 x64, CPython 3.14.10, pip 26.3, and the complete pinned dependency set in `requirements-lock.txt`. The application is packaged with the committed `7z-encrypt-tool.spec` and `pyinstaller_hooks/hook-py7zr.py`.

To reproduce the build locally, install CPython 3.14.10 x64 and run:

```powershell
py -3.14.10 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install --disable-pip-version-check --only-binary=:all: --upgrade "pip==26.3"
.\.venv-build\Scripts\python.exe -m pip install --disable-pip-version-check --only-binary=:all: --no-deps -r requirements-lock.txt
.\.venv-build\Scripts\python.exe -m pip check
.\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-build\Scripts\python.exe -m PyInstaller --clean --noconfirm 7z-encrypt-tool.spec
.\dist\7z-encrypt-tool.exe --self-test --self-test-output .\self-test.json
```

The workflow also pins GitHub Actions by commit SHA, fixes `PYTHONHASHSEED`, sets `SOURCE_DATE_EPOCH` from the source commit, records the runner image and installed dependency list, and computes the published checksum after the self-test. See [BUILD_REPRODUCIBILITY.md](BUILD_REPRODUCIBILITY.md) for the reproducibility boundary and [CODE_SIGNING.md](CODE_SIGNING.md) for the unsigned-release decision.

## Project dependencies

- Runtime direct dependencies: `py7zr==1.1.4` and `pycryptodomex==3.24.2`.
- Build direct dependency: `PyInstaller==6.22.3`.
- The authoritative complete runtime/build dependency set is `requirements-lock.txt`.
