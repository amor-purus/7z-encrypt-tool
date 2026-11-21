# Decision 0002: optional Windows DPAPI password record

- Status: **Adopted for v2.0.0**
- Scope: password-recovery record content, explicit export and user guidance
- Compatibility: existing plaintext TXT and standard encrypted 7z archives remain supported

## Decision

Provide two modes, selected explicitly in the desktop GUI:

1. **Plaintext TXT (compatibility):** a readable separate recovery record with warning.
2. **Windows current-user DPAPI:** a separate TXT holding a unique magic marker and Base64-encoded DPAPI ciphertext, not the plaintext password or filenames. The record remains .txt to preserve existing transaction journal naming and recovery safeguards.

No encryption format changes are made to the 7z archive. User-scoped `CryptProtectData` protects the record; `CryptUnprotectData` decrypts on explicit export.

## Backup and limitations

Windows DPAPI is bound to an accessible user profile and protection keys. A reinstall, deleted user, changed profile or machine loss may make protected records unrecoverable. The GUI therefore provides **explicit plaintext export**, requiring a warning and an unused file destination, for offline or cross-device recovery. Do not treat a same-machine DPAPI record as a complete disaster-recovery backup.

DPAPI cannot defend against malware executing under the same user or against an attacker with access to that user's credentials and protection keys. Keeping archive/password in distinct folders is a usability boundary and does not imply separate access-control domains. A plaintext exported record requires secure storage. Python application memory cannot promise perfect zeroization of immutable strings.

## Recovery and atomicity

The established journal still records only paths, temporary file identities and publication metadata, never the password. Both modes retain the **password-record-first** publication order. Cancellation is allowed between archive members and before publication, but not after publication begins. Startup recovery remains conservative about ambiguous file states.

There is no atomic operation spanning the final archive and the separate password record across arbitrary directories. Hardware-power-loss durability, account-key portability and protection against concurrent hostile filesystem writes are expressly outside guarantees.

## Testing

Windows CI performs DPAPI protection and round trip, explicit export, corruption rejection, cancellation, hard-process-kill recovery, and a frozen-EXE DPAPI round trip. Official 7-Zip independently decodes an archive and compares file contents with SHA-256.

The application does not claim that CRC or unkeyed SHA-256 alone provide malicious-tampering authenticity or source identity.
