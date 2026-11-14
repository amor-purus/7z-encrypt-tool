"""Collect py7zr and its runtime codec dependencies for PyInstaller.

py7zr selects several codecs dynamically. Collecting the complete import packages
also collects their Windows .pyd binaries; distribution metadata is copied
explicitly so importlib.metadata remains usable in the frozen application.
"""
from importlib.metadata import PackageNotFoundError, distribution
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = []

# Import package -> installed distribution name.
REQUIRED_DEPENDENCIES = {
    "Cryptodome": "pycryptodomex",
    "pyppmd": "pyppmd",
    "bcj": "pybcj",
    "inflate64": "inflate64",
    "brotli": "brotli",
    "psutil": "psutil",
    "multivolumefile": "multivolumefile",
    "texttable": "texttable",
}

def collect_package(module_name: str) -> None:
    global datas, binaries, hiddenimports
    if find_spec(module_name) is None:
        raise ImportError(
            f"Required py7zr runtime module {module_name!r} is missing. "
            "Install the project requirements before building."
        )
    package_datas, package_binaries, package_hiddenimports = collect_all(
        module_name,
        on_error="raise",
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


# Main library and all its submodules/data.
collect_package("py7zr")

# Native codec and support packages used directly or through dynamic imports.
for module_name, distribution_name in REQUIRED_DEPENDENCIES.items():
    collect_package(module_name)
    try:
        distribution(distribution_name)
    except PackageNotFoundError as exc:
        raise RuntimeError(
            f"Missing package metadata for {distribution_name!r}; "
            "the build environment is incomplete."
        ) from exc
    datas += copy_metadata(distribution_name)

# py7zr uses stdlib compression.zstd on Python 3.14+ and backports.zstd
# on older interpreters. Keep both branches when present.
OPTIONAL_MODULES = {
    "brotlicffi": "brotlicffi",
    "backports.zstd": "backports-zstd",
    "compression.zstd": None,
}

def module_is_available(module_name: str) -> bool:
    try:
        return find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False

for module_name, distribution_name in OPTIONAL_MODULES.items():
    if not module_is_available(module_name):
        continue
    package_datas, package_binaries, package_hiddenimports = collect_all(
        module_name,
        on_error="warn once",
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports
    if distribution_name:
        try:
            distribution(distribution_name)
        except PackageNotFoundError:
            pass
        else:
            datas += copy_metadata(distribution_name)

# Include py7zr's own distribution metadata and de-duplicate file tuples.
datas += copy_metadata("py7zr")
datas = list(dict.fromkeys(tuple(item) for item in datas))
binaries = list(dict.fromkeys(tuple(item) for item in binaries))
hiddenimports = sorted(set(hiddenimports))
