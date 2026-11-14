# 7z File Encryption Tool v1.0.3

## Windows startup
1. Install 64-bit CPython 3.14.
2. Extract the project into a folder you can write to.
3. Double-click `start.bat`.
4. The launcher verifies CPython 3.14, 64-bit architecture, the virtual environment's base interpreter, and the exact `py7zr==1.1.4` version.
5. On first launch, the launcher installs compatible prebuilt wheels only. Source builds and local C++ compilation are disabled.
6. The GUI starts without leaving a command window open.

The launcher supports the regular per-user installer path, the Python Install Manager runtime path, and common all-user installation paths. It does not use `py -3` or a PATH-resolved interpreter.

## App behavior
- Select one or multiple files; the output-folder picker appears next.
- Creates a 7z archive using AES-256 and encrypted headers (file and folder names are hidden).
- Generates a random 32-character password and a random 10-character archive name.
- Writes a matching TXT password record.
- The TXT records both each original filename and its path inside the archive.
- Duplicate selections, symbolic-link aliases, and detectable hard links are deduplicated.
- Archive member paths are checked case-insensitively to avoid duplicate names and file/directory collisions.
- The password TXT is published before the archive, so a completed visible archive is not intentionally published without its password record.
- The GUI refuses a normal close request while compression or verification is running.
- Original files are not deleted, moved, or modified.

## Security note
The TXT contains the password in plaintext. Keep it separate from the 7z archive. If the output folder is synchronized to a cloud service, both files may be uploaded automatically.

## Optional tests
Run the standard-library tests from the project folder:

```bat
.venv314\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover Windows-style archive-name conflicts, preservation of unique filenames, symbolic-link aliases, and hard-link deduplication where supported.

## Verification boundary
The repository includes automated tests for archive naming and file deduplication. Real 7z encryption, decryption with an independent 7-Zip client, GUI behavior, and launcher behavior still need an end-to-end test on Windows using non-sensitive sample files.
