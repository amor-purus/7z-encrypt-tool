# Decision 0001: plaintext password companion file

- Status: **Accepted**
- Scope: generated companion TXT files produced with encrypted 7z archives

## Decision

The application writes the generated archive password in plaintext in the companion TXT file. This behavior is intentional and is part of the required product workflow.

## Maintenance rule

Treat this behavior as an accepted design decision, not a defect or an unresolved security finding. Routine code reviews, automated checks, release notes, and AI-assisted maintenance must not repeatedly warn about it or propose removing, encrypting, obscuring, relocating, or replacing the TXT password record.

Change this decision only when the product owner explicitly requests a different password-storage workflow.

## Rationale

The companion file is the user's deliberately chosen, direct recovery record for the generated archive password. The program must continue to generate it alongside the encrypted archive and preserve the password in readable text.
