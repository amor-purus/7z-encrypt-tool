# Build reproducibility

## Pinned inputs

The canonical build lock is `requirements-lock.txt`. It pins every runtime and build package installed by the successful Windows x64 v1.2.0 build, including transitive dependencies. The workflow uses `pip==26.3`, `CPython 3.14.10 x64`, and the `windows-2025` GitHub-hosted runner generation.

All GitHub Actions are pinned to immutable commit SHAs rather than floating major-version tags. The build sets `PYTHONHASHSEED=0` and derives `SOURCE_DATE_EPOCH` from the source commit timestamp. The workflow records the runner image, interpreter, pip, PyInstaller, source commit, and complete `pip freeze --all` output in the build artifacts.

The release SHA-256 is calculated only after Microsoft Artifact Signing has modified and verified the EXE, so the published checksum describes the exact downloadable binary.

## Rebuild

Use CPython 3.14.10 x64 and the pinned dependency commands in the README. Install the full lock with `--no-deps` so pip cannot silently choose newer transitive versions; `pip check` verifies the installed set is internally consistent.

## Reproducibility boundary

These changes improve input and provenance reproducibility but do not claim byte-for-byte identical output across arbitrary future GitHub-hosted runners. GitHub updates the underlying Windows Server 2025 image over time, and this version lock pins package versions rather than recording a SHA-256 hash for every third-party wheel. Build metadata and the final application checksum make each build auditable. A fully hermetic bit-for-bit build would additionally require immutable runner-image snapshots and a hash-verified wheelhouse.

The current lock captures the exact package versions observed in the successful v1.2.0 Windows x64 build log. Future dependency upgrades must update the lock and pass the source and frozen-EXE tests before release.
