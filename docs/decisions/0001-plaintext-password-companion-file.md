# Decision 0001: explicitly located plaintext password record

- Status: **Amended by owner for v1.3.0 (2026-11-16)**
- Scope: plaintext recovery TXT generated for every successfully published encrypted 7z archive

## Decision

The complete generated password remains readable plaintext in a TXT recovery record, but the user **must explicitly select its destination** outside the archive's output directory. The GUI displays a clear plaintext-password warning and requires confirmation. The application must not silently create a password TXT beside the archive. An existing TXT is never overwritten.

Both products are considered successful only when the encrypted archive is verified, the password record has been durably written and the final archive published. On failure the application cleans up temporary files and rolls back a password record published during that failed attempt where possible. Source files remain untouched.

## Rationale

A plaintext recovery record helps users preserve the decryption key, but automatic colocated storage creates unnecessary exposure. Explicit location selection balances recovery with the owner's updated storage requirement. Version 1.2.0 intentionally co-located password and archive; this decision supersedes that practice.

## Power-loss boundary

Atomic rename applies separately to each file, not as one cross-directory transaction. Password-first publication prevents a published encrypted archive without an already persisted password during ordinary operation; an abnormal process or OS crash can leave a password TXT without its archive. This is the chosen safety direction; it is not a claim of multi-file crash atomicity.
