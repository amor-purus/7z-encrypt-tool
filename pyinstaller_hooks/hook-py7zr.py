"""Collect py7zr and its runtime codec dependencies for PyInstaller.

py7zr selects several codecs dynamically. Package dependencies are collected
recursively; standalone extension modules are listed as hidden imports so
PyInstaller's module graph collects their Windows .pyd binaries directly.
Distribution metadata is copied explicitly for importlib.metadata.
"""
from importlib.metadata import PackageNotFoundError, distribution
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = []


def collect_module(module_name: str, *, required: bool = True) -> bool:
    """Collect a package recursively, or register a standalone module as hidden."""
    global datas, binaries, hiddenimports

    try:
        module_spec = find_spec(module_name)
    except (ImportError, ModuleNotFoundError, ValueError):
        module_spec = None

    if module_spec is None:
        if required:
            raise ImportError(
                f"Required py7zr runtime module {module_name!r} is missing. "
                "Install the project requirements before building."
            )
        return False

    if module_spec.submodule_search_locations is not None:
        package_datas, package_binaries, package_hiddenimports = collect_all(
            module_name,
            on_error="warn once",
        )
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hiddenimports
    else:
        # Cython/C-extension wheels (e.g. bcj and inflate64) are often
        # standalone modules rather than Python packages.
        hiddenimports.append(module_name)

    return True


# Main library and all its submodules/data.
collect_module("py7zr")

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

# Native codec and support packages used directly or through dynamic imports.
for module_name, distribution_name in REQUIRED_DEPENDENCIES.items():
    collect_module(module_name)
    try:
        distribution(distribution_name)
    except PackageNotFoundError as exc:
        raise RuntimeError(
            f"Missing package metadata for {distribution_name!r}; "
            "the build environment is incomplete."
        ) from exc
    datas += copy_metadata(distribution_name)

# py7zr uses stdlib compression.zstd on Python 3.14+ and backports.zstd
# on older interpreters. These optional modules are collected when present.
OPTIONAL_MODULES = {
    "brotlicffi": "brotlicffi",
    "backports.zstd": "backports-zstd",
    "compression.zstd": None,
}
for module_name, distribution_name in OPTIONAL_MODULES.items():
    if not collect_module(module_name, required=False):
        continue
    if distribution_name:
        try:
            distribution(distribution_name)
        except PackageNotFoundError:
            pass
        else:
            datas += copy_metadata(distribution_name)

# Keep py7zr's own metadata and de-duplicate collection entries.
datas += copy_metadata("py7zr")
datas = list(dict.fromkeys(tuple(item) for item in datas))
binaries = list(dict.fromkeys(tuple(item) for item in binaries))
hiddenimports = sorted(set(hiddenimports))
