# 7z File Encryption Tool v1.2.0

A standalone Windows 11 GUI application for creating AES-256 encrypted 7z archives from files, folders, or a mixed selection.

## Download and run

1. Open the repository's **Releases** page and download \`7z-encrypt-tool-windows-x64.exe\`.
2. Optionally verify the SHA-256 checksum against \`SHA256SUMS.txt\`.
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

## Downloading a build before a tagged release exists

Every successful build workflow uploads a downloadable artifact:

1. Open the repository's **Actions** tab.
2. Select **Build standalone Windows EXE**.
3. Open the latest successful run.
4. Download the artifact named \`7z-encrypt-tool-windows-x64-<commit>\`.

Workflow artifacts are retained for 30 days. Tagged builds (\`v*\`) are also attached to a GitHub Release automatically.

## Signed releases and CI artifacts

Official tagged and `release/*` builds are published only after the Windows EXE has been signed with Microsoft Artifact Signing, its Authenticode signature has been verified, and the final SHA-256 checksum has been generated. Pull-request, `main`, and maintenance-branch Actions artifacts are CI-only builds and are not publisher-signed. The release-signing workflow uses GitHub OIDC and an Azure-managed signing key; it does not store a PFX or private key in GitHub.

A valid signature identifies the publisher and protects the EXE against undetected modification. A new publisher or binary can still receive a Microsoft Defender SmartScreen reputation warning while reputation accumulates. See [CODE_SIGNING.md](CODE_SIGNING.md) for the one-time Azure/GitHub configuration.

## Application behavior

- Creates standard 7z archives with AES-256 encryption and encrypted headers (member names are hidden).
- Generates a random 32-character password and a random 10-character archive name.
- Writes a companion TXT containing the password and original-to-archive path mappings, labeling folders as \`[文件夹]\`.
- Detects duplicate selections, symbolic-link aliases, and filesystem hard links where file identity is available.
- Preserves nested folders and empty directories and verifies the complete expected archive member set.
- Confirms that member names cannot be read without the password and runs the archive integrity check.
- Does not delete, move, or modify original files.
- Prevents a normal window close while encryption or verification is running.

## Password-record design decision

The companion TXT intentionally stores the generated password as plaintext. This is an accepted product requirement, not a defect or an item for routine remediation. Do not remove, encrypt, obscure, relocate, or repeatedly flag this behavior unless the owner explicitly changes the requirement. See [Decision 0001](docs/decisions/0001-plaintext-password-companion-file.md).

## Logs

Application logs are written to:

\`%LOCALAPPDATA%\\7z-Encrypt-Tool\\logs\\application.log\`

If the application reports an error, include this log when reporting the issue. It may contain local file paths; review it before sharing.

## Build from source (maintainers)

The application is built on GitHub Actions using Windows x64, CPython 3.14, PyInstaller, and the committed \`7z-encrypt-tool.spec\` plus \`pyinstaller_hooks/hook-py7zr.py\`.

To reproduce the build locally:

\`\`\`powershell
py -3.14 -m venv .venv-build
.\\.venv-build\\Scripts\\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\\.venv-build\\Scripts\\python.exe -m unittest discover -s tests -v
.\\.venv-build\\Scripts\\python.exe -m PyInstaller --clean --noconfirm 7z-encrypt-tool.spec
.\\dist\\7z-encrypt-tool.exe --self-test --self-test-output .\\self-test.json
\`\`\`

The build workflow runs the source regression tests and a frozen-EXE self-test that creates, password-checks, verifies, and extracts an encrypted archive containing nested and empty folders. The complete dependency lock, immutable Action references, fixed Python patch version, build provenance, and reproducibility limits are documented in [BUILD_REPRODUCIBILITY.md](BUILD_REPRODUCIBILITY.md).

## Project dependencies

- Runtime: \`py7zr==1.1.4\` and its declared dependencies.
- Build: \`PyInstaller==6.22.3\`.
