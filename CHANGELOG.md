# Changelog

## v2.0.0 — integrated reliability, password safety and user experience

- Added optional Windows DPAPI password records with explicit plaintext export and recovery warnings.
- Added true input-byte progress, package-member counters, and cooperative cancellation before final publication.
- Added official 7-Zip independent extraction and file SHA-256 interoperability validation to the Windows build gate.
- Added stress and fault-injection regression coverage, preserving the established two-path transaction journal.
- Documented the difference between 7z encryption, file consistency checks, and authenticated provenance.
- Kept plaintext TXT and existing 7z archives compatible; no custom encryption format was added.


## v1.5.0 — 2026-11-16

- Added a persistent, metadata-only transaction journal before creation of any stage file.
- Serialized packaging and recovery across processes/threads using an OS-level lock released on process exit.
- On restart, automatically roll back orphaned password records and unfinished files; retain published archive/password pairs and remove completed journals.
- Recovery checks filesystem identities and refuses destructive cleanup when volumes disappear or destinations change.
- Added real Windows subprocess hard-exit tests after password staging, final password publication, and final encrypted archive publication; recovery is tested from a new process.
- No journal contains the generated password. Physical cross-directory atomicity and hardware power-loss durability are explicitly not claimed.

## v1.4.0 — 2026-11-16

- Fixed silent loss of distinct case-sensitive NTFS entries during input deduplication and ancestor checks using filesystem identity rather than case-folded path comparisons.
- Restored GUI controls/close on thread constructor or Thread.start failures; logging fallback is now a non-throwing NullHandler with best-effort diagnostic calls.
- Protected the only password after an asynchronous exception immediately following archive publication; conservative cleanup avoids deleting the key when the archive may already exist.
- Added exclusive staging file creation/handle binding, SHA-256 revalidation immediately before publication, input stat and directory re-inventory checks, and no-clobber publication.
- fsyncs the archive and password staging contents and POSIX directories where supported; documents that cross-directory crash/OS-power-loss atomicity remains impossible.
- Detects incomplete encrypted archive staging and potentially plaintext recovery TXT files at new task setup, warns without deleting evidence.
- Adds Windows NTFS case-sensitive production integration checks, GUI thread-start and closed-stderr fault tests, post-publication interrupt, archive overwrite, source mutation and recovery-file tests.

## v1.3.0 — 2026-11-16

- Preflight validation rejects internal NFC/case-folded archive-name collisions with both source paths; numeric fallback retries are limited.
- Writes validated directory inventory members one-by-one rather than calling py7zr.writeall(), preserving root and empty directory entries when cwd lies inside the source tree.
- Password TXT requires explicit separate destination and user confirmation about plaintext; failure prevents publishing the encrypted archive.
- Failed archive/password publication cleans staging artifacts and attempts rollback, without touching original files.
- Error display no longer creates the log directory; unavailable logs do not mask the task exception, even when a windowed EXE has no stderr stream.
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
