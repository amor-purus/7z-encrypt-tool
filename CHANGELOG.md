# Changelog

## v1.2.0 — 2026-11-14

- Added a queued GUI workflow for adding multiple files and repeatedly adding folders.
- Added parent/child selection deduplication and output-folder containment protection.
- Added recursive folder packaging, including nested files and empty directories.
- Made archive-path allocation aware of folder contents, duplicate folders, extensionless file/folder collisions, and mixed selections.
- Expanded archive verification to compare every expected directory and file member while retaining encrypted-header and CRC checks.
- Updated password records, README, and Chinese usage instructions.
- Added regression coverage for folder-only, nested empty-folder, duplicate-folder, mixed-selection, extensionless-name collision, single-file compatibility, parent-folder deduplication, and output-path rejection.
