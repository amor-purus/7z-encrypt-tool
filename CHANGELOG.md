# Changelog

## v1.3.0 — 2026-11-16

- Preflight validation rejects internal NFC/case-folded archive-name collisions with both source paths; numeric fallback retries are limited.
- Writes validated directory inventory members one-by-one rather than calling py7zr.writeall(), preserving root and empty directory entries when cwd lies inside the source tree.
- Password TXT requires explicit separate destination and user confirmation about plaintext; failure prevents publishing the encrypted archive.
- Failed archive/password publication cleans staging artifacts and attempts rollback, without touching original files.
- Error display no longer creates the log directory; unavailable logs do not mask the task exception.
- Expanded real-business-flow regression coverage and frozen-EXE self-test through create_encrypted_bundle.

# Changelog

## Unreleased — build integrity and maintenance

- Recorded plaintext companion-password storage as an accepted product design decision; routine reviews must not reopen it.
- Recorded the owner's decision not to purchase trusted code signing; GitHub Releases intentionally publish unsigned EXE files without a paid signing dependency.
- Removed the Azure Artifact Signing/OIDC release gate; release publication now follows successful build, regression tests, frozen-EXE self-test, and SHA-256 generation.
- Pinned GitHub Actions by commit SHA, the Windows runner generation, CPython patch version, pip, and all runtime/build dependency versions.
- Added deterministic Python hash/timestamp inputs and build/dependency provenance; the final SHA-256 is generated after the frozen-EXE self-test.

## v1.2.0 — 2026-11-14

- Added a queued GUI workflow for adding multiple files and repeatedly adding folders.
- Added parent/child selection deduplication and output-folder containment protection.
- Added recursive folder packaging, including nested files and empty directories.
- Made archive-path allocation aware of folder contents, duplicate folders, extensionless file/folder collisions, and mixed selections.
- Expanded archive verification to compare every expected directory and file member while retaining encrypted-header and CRC checks.
- Updated password records, README, and Chinese usage instructions.
- Added regression coverage for folder-only, nested empty-folder, duplicate-folder, mixed-selection, extensionless-name collision, single-file compatibility, parent-folder deduplication, and output-path rejection.
