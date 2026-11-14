# Release code signing

## Signing design

Official Release artifacts are signed after the Windows build and frozen-EXE self-test, using Microsoft's managed Artifact Signing service. GitHub Actions authenticates with OpenID Connect (OIDC); no code-signing private key or PFX file is stored in the repository.

The signing job runs in the GitHub Environment named `release-signing`. It verifies the Authenticode signature before generating `SHA256SUMS.txt`. The Release job consumes only the signed-and-verified artifact. If signing is unavailable or verification fails, publication fails closed.

Pull-request, `main`, and `maintenance/*` builds are CI artifacts and remain unsigned.

## One-time Azure setup

1. Create an Azure Artifact Signing account, complete public-trust identity validation, and create a certificate profile for Authenticode code signing. For an account created in Japan East, use the matching endpoint `https://jpe.codesigning.azure.net/`.
2. Create an Azure app registration/service principal for the GitHub workflow.
3. Add a federated identity credential to the app registration:
   - Issuer: `https://token.actions.githubusercontent.com`
   - Audience: `api://AzureADTokenExchange`
   - Subject: `repo:yanchengz685-bot/7z-encrypt-tool:environment:release-signing`
4. Assign the **Artifact Signing Certificate Profile Signer** role to that app registration at the certificate-profile scope (or the narrowest supported scope).
5. In GitHub, create the `release-signing` Environment. Restrict deployment branches/tags to release refs (for example, `release/*` and `v*`). Add an approval gate only if release signing should require manual approval.
6. Add these repository Actions **Variables**. They are configuration identifiers, not private keys:

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | App registration client/application ID |
| `AZURE_TENANT_ID` | Azure tenant/directory ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_SIGNING_ENDPOINT` | Region endpoint matching the signing account, e.g. `https://jpe.codesigning.azure.net/` |
| `AZURE_SIGNING_ACCOUNT` | Artifact Signing account name |
| `AZURE_CERTIFICATE_PROFILE` | Certificate profile name |

The workflow uses the Azure CLI session established by `azure/login` with GitHub OIDC; no client secret is required.

## Eligibility and SmartScreen

Microsoft's current public-trust eligibility rules list Japan as available to organizations. Individual developers must be located in the United States or Canada. Confirm the applicant's legal category before creating the account. If the owner is not eligible, use a trusted code-signing provider that supports the owner's jurisdiction and a managed/HSM-backed signing workflow; do not substitute a self-signed certificate.

A valid Authenticode signature proves signer identity and file integrity. It does not guarantee that SmartScreen will immediately stop warning on a new publisher or binary; reputation is assessed separately.

## Release procedure

1. Configure the Azure account, certificate profile, role, GitHub OIDC federation, GitHub Environment, and six Actions Variables above.
2. Push a release branch (for example, `release/v1.2.1`) or a `v*` tag.
3. Confirm the `Sign and verify Windows x64 EXE` job succeeds and the release asset's `BUILD-INFO.txt` reports a valid Authenticode signature.
4. Verify the published digest using `SHA256SUMS.txt`.

Do not upload a PFX/private signing key to GitHub Actions. Microsoft's service keeps the code-signing key in its managed signing infrastructure.

Official setup: [Microsoft Artifact Signing quickstart](https://learn.microsoft.com/azure/artifact-signing/quickstart) · [Azure Artifact Signing GitHub Action](https://github.com/Azure/artifact-signing-action)
