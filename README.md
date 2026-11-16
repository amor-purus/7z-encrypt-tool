# 7z File Encryption Tool v1.4.0

A standalone Windows 11 GUI application for creating AES-256 encrypted 7z archives from files, folders, or a mixed selection.

## Download and run

1. Open the repository's **Releases** page and download `7z-encrypt-tool-windows-x64.exe`.
2. Verify its SHA-256 against `SHA256SUMS.txt`.
3. Double-click the EXE. No Python installation, BAT launcher, virtual environment, pip, or administrator rights are required.
4. Add files and/or folders to the queue, then click **Start encryption** and choose an output folder.
5. Select a separate destination for the plaintext password TXT. The app warns you before writing a plaintext password.
6. Wait for compression and integrity verification to finish.

The EXE is a single-file, windowed PyInstaller build. It does not open a persistent console window. The first launch can take a little longer because PyInstaller extracts its bundled runtime to a temporary directory.

## Selecting files and folders

- **Add files** opens the native multi-select file picker; select one or more files at once.
- **Add folder** adds one folder. Click it again to add more folders.
- **Remove selected** removes the highlighted queue entries. **Clear** empties the queue.
- The queue can contain only folders or a mixture of files and folders.
- Selecting a parent folder automatically subsumes any separately selected files or subfolders inside it, preventing duplicate packaging.
- The output folder must be outside every selected source folder. The application blocks an output folder that is the source itself or one of its descendants, avoiding recursive inclusion of the archive being written.

Each selected folder is stored under a top-level archive path and includes its nested directories, files, and empty directories. Conflicting names are disambiguated using parent-folder names or a numeric suffix. The password TXT identifies each entry as a file or folder and records its exact archive path. It must be saved to a separate directory, selected by the user.

## Password-record safety

The application generates a 32-character password using Python's `secrets` module and keeps the 7z member names and data encrypted. Before starting encryption, you must select a password TXT destination **in a different directory** from the archive, and confirm a warning that the TXT contains the complete plaintext password.

No password TXT is automatically written next to the archive. Existing password files are never overwritten. If saving the password fails, the verified archive is not published; temporary outputs are cleaned. On ordinary publication failure the password record is rolled back when the archive is demonstrably absent. If archive publication succeeds or its state cannot be confirmed, the password is **retained**, even when an asynchronous exception is raised. A cross-directory two-file transaction and power-loss durability cannot be guaranteed; a terminated process can leave recoverable staging files or an orphan password record. See [Decision 0001](docs/decisions/0001-plaintext-password-companion-file.md).

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
- Saves a plaintext TXT containing the password and original-to-archive path mappings to a separate, explicitly selected location; never silently beside the archive.
- Detects duplicate selections, symbolic-link aliases, and filesystem hard links where file identity is available.
- Preserves nested folders and empty directories and verifies the complete expected archive member set.
- Confirms that member names cannot be read without the password and runs the archive integrity check.
- Does not delete, move, or modify original files.
- Prevents a normal window close while encryption or verification is running, then restores GUI controls on failure.
- Rejects colliding Unicode-normalized folder members before packaging; recognizes distinct files in case-sensitive NTFS directories and writes every inventoried member explicitly (including cwd and empty directories).
- Detects source files or directory layout changed during packaging, preventing a false-success archive from a changed input set.
- Uses exclusive staging and SHA-256 rechecks to detect modification of the encrypted staging file before publication.

## Interrupted-task recovery and durability boundary

If the process is terminated abruptly, its cleanup code cannot run. Before a new task, the app scans the selected archive/password directories for recognizable staging files and warns you. It does **not** automatically delete potentially recoverable plaintext passwords.

- Archive staging names: `.7z-archive-*.incomplete.7z`. They contain encrypted archives but are not automatically considered finished.
- Password staging names: `.7z-password-PLAINTEXT-*.incomplete.txt`. **These may contain the full plaintext password.** Treat them as secrets. Check associated archive/name, recover the key if necessary, then remove abandoned files manually.
- A final password TXT can exist without its archive after a crash. It identifies the expected random 7z archive name.
- Files are flushed to storage before publication; directory metadata is fsynced where supported. Neither this nor two renames on separate directories provides a power-failure-atomic transaction on Windows or other operating systems.

Archive staging uses a random exclusive file handle and SHA-256 post-verification checks. This detects ordinary tampering before publication, but **does not protect files in hostile or shared directories** against a concurrent actor with write permission, nor does it guarantee an immutable snapshot of a source changed by another process. The tool rejects detectable source changes; use a stable source directory and trusted private output/password locations.

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
