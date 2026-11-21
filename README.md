# 7z File Encryption Tool v2.0.0

A standalone Windows 11 GUI application for creating AES-256 encrypted 7z archives from files, folders, or a mixed selection.

## Download and run

1. Open the repository's **Releases** page and download `7z-encrypt-tool-windows-x64.exe`.
2. Verify its SHA-256 against `SHA256SUMS.txt`.
3. Double-click the EXE. No Python installation, BAT launcher, virtual environment, pip, or administrator rights are required.
4. Add files and/or folders to the queue, then click **Start encryption** and choose an output folder.
5. Choose a separate password-record TXT destination and select either plaintext recovery or current-Windows-account DPAPI protection.
6. Wait for compression and integrity verification to finish.

The EXE is a single-file, windowed PyInstaller build. It does not open a persistent console window. The first launch can take a little longer because PyInstaller extracts its bundled runtime to a temporary directory.

## v2.0: interoperability, password options and cancellation

- **Independent compatibility gate:** Windows CI verifies an encrypted archive with the official 7-Zip decoder, checks the wrong-password rejection, and compares extracted file SHA-256 values against the inputs, including Japanese text and an empty directory. The installed app still uses py7zr for its internal checks.
- **Windows DPAPI option:** the password TXT can contain current-user account-bound DPAPI ciphertext instead of plaintext. Use **导出受保护记录** while signed into the original account to create a deliberately confirmed portable plaintext recovery copy. **If your Windows identity or DPAPI keys are lost, protected records may become undecryptable.** Malware running as the same user may also decrypt them. Plaintext mode remains available.
- **Real data progress:** during the packaging stage the UI shows completed input bytes and archive members, then switches to verification and publication status. This is not a percentage of total execution time.
- **Safe cooperative cancel:** the UI supports cancellation between archive members; it does not kill a partially executing write or interrupt final file publication. The existing transaction journal controls cleanup.
- **Testing:** stress scenarios with nested Unicode files, source changes, forced disk errors, and protected-record failures are added to Windows CI.
- **Cryptographic boundary:** 7z AES-256 and header encryption protect confidentiality. CRC/integrity checks and unkeyed SHA-256 do not themselves authenticate files against an adversary able to replace the files or checksum.

## Selecting files and folders

- **Add files** opens the native multi-select file picker; select one or more files at once.
- **Add folder** adds one folder. Click it again to add more folders.
- **Remove selected** removes the highlighted queue entries. **Clear** empties the queue.
- The queue can contain only folders or a mixture of files and folders.
- Selecting a parent folder automatically subsumes any separately selected files or subfolders inside it, preventing duplicate packaging.
- The output folder must be outside every selected source folder. The application blocks an output folder that is the source itself or one of its descendants, avoiding recursive inclusion of the archive being written.

Each selected folder is stored under a top-level archive path and includes its nested directories, files, and empty directories. Conflicting names are disambiguated using parent-folder names or a numeric suffix. The password TXT identifies each entry as a file or folder and records its exact archive path. It must be saved to a separate directory, selected by the user.

## Password-record safety

The application generates a 32-character password using Python's `secrets` module and encrypts 7z data and headers. Select a password-record destination **in a different directory** from the archive. Plaintext mode warns that the TXT contains the password; DPAPI mode warns about account-bound recovery and offers an explicitly confirmed plaintext export.

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

## Crash recovery, password preservation, and power-loss boundaries

**v1.5.0 adds automatic crash recovery.** A metadata-only journal is written and fsynced in the current user's application-data folder **before** archive or password staging appears. It contains destinations, random transaction IDs, and file identities, **never the plaintext password**. The password is written only in the user-selected, separate password directory.

- An operating-system transaction lock prevents another instance from cleaning up an active task. The OS releases it when that process dies.
- At the next launch, the application scans durable journals and reconciles them **before allowing new tasks**. The production API does the same under the lock.
- If no archive was published, unfinished archive and temporary plaintext password files are removed. A published password TXT is rolled back only if its filesystem identity matches the journal.
- When both final files are published, the archive/password pair is preserved, temporary files are cleaned, and the journal is removed.
- If a target directory disappears or changes, or final-file identity cannot be verified, recovery **does not delete ambiguous files**. It warns and blocks new encryption until the problem is resolved.
- Staged archives end in `.incomplete.7z` and plaintext password staging ends in `.incomplete.txt`. Old unjournaled staging from v1.4.0 still requires manual attention.

**Hard process kill vs. power loss:** The recovery protocol is tested by ending a real Windows subprocess with `os._exit()` at three publication boundaries and recovering in a separate process. This demonstrates post-restart recovery from abrupt *process* termination, not from actual electrical power loss. Windows cannot atomically commit two files in independent directories. Filesystems that lose acknowledged writes, inaccessible drives, hostile concurrent writers, or physical storage failure can still create ambiguous states requiring manual intervention. The application prioritizes the only surviving decryption key.

Files are fsynced before publication. Directory metadata is fsynced where portable (POSIX); Windows directory fsync is not generally available. Output and password locations should be private and on stable storage.

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
