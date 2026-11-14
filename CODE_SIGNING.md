# Code-signing decision

## Project decision

The project owner has decided **not to purchase or use a trusted Authenticode code-signing certificate**. Official GitHub Releases are intentionally published with unsigned Windows executables.

This is a deliberate cost and maintenance decision, not an unfinished release prerequisite. Do not add a paid signing service, Azure Artifact Signing account, certificate profile, GitHub OIDC federation, signer role, or a required signing job unless the owner explicitly revises this decision.

No self-signed certificate is used as a substitute. The release pipeline must remain able to publish after the Windows build and tests succeed, without any code-signing account, credentials, environment, or paid certificate.

## What users should expect

- Windows may show an unknown-publisher or Microsoft Defender SmartScreen warning when launching the EXE. This is expected for an unsigned release.
- `BUILD-INFO.txt` explicitly reports `Authenticode: not signed (project decision)`.
- `SHA256SUMS.txt` records the SHA-256 digest of the exact EXE attached to the Release. It can detect differences between a downloaded file and the published digest, but it does not establish publisher identity or independently authenticate the Release page.
- The v1.2.0 release artifact was also unsigned. Future releases remain unsigned under this decision.

## Reconsidering this decision

Only revisit trusted code signing when the owner explicitly requests it and accepts the associated subscription cost, eligibility requirements, identity validation, and ongoing configuration. Any future signing implementation must remain a deliberate project change rather than an implicit release blocker.

For the unsigned build and release process, see [BUILD_REPRODUCIBILITY.md](BUILD_REPRODUCIBILITY.md).
