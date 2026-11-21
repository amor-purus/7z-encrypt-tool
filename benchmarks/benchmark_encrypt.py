"""Reproducible local performance baseline; never uses the user's files.

Usage:
    python benchmarks/benchmark_encrypt.py --size-mib 16 --small-files 300

Prints safe aggregate timing/throughput metrics; no passwords or local paths.
No universal pass/fail speed threshold is imposed across differing hardware.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


def benchmark(size_mib: int, small_files: int) -> dict:
    if not 1 <= size_mib <= 512 or not 0 <= small_files <= 10000:
        raise ValueError("size-mib must be 1..512 and small-files must be 0..10000")
    with tempfile.TemporaryDirectory(prefix="7z-perf-") as td:
        root = Path(td)
        large = root / "incompressible.bin"
        with large.open("wb") as f:
            for _ in range(size_mib):
                f.write(os.urandom(1024 * 1024))
        items = [large]
        if small_files:
            folder = root / "tiny"
            folder.mkdir()
            for i in range(small_files):
                (folder / f"file_{i:05}.txt").write_bytes(b"reliability" * (1 + i % 10))
            items.append(folder)
        out = root / "out"
        password_dir = root / "keys"
        out.mkdir()
        password_dir.mkdir()
        old_app_data = main.app_data_dir
        main.app_data_dir = lambda: root / "appdata"
        try:
            tracemalloc.start()
            start = time.perf_counter()
            archive, record = main.create_encrypted_bundle(
                items, str(out), password_file=str(password_dir / "record.txt"))
            elapsed = time.perf_counter() - start
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return {
                "version": main.APP_VERSION,
                "large_input_mib": size_mib,
                "small_files": small_files,
                "elapsed_seconds": round(elapsed, 3),
                "throughput_mib_per_second": round(size_mib / elapsed, 3),
                "archive_size_bytes": Path(archive).stat().st_size,
                "python_tracemalloc_peak_bytes": peak,
                "password_record_created": Path(record).is_file(),
                "note": "Python tracemalloc excludes some native allocations; run on comparable hardware."
            }
        finally:
            main.app_data_dir = old_app_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-mib", type=int, default=16)
    parser.add_argument("--small-files", type=int, default=300)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.size_mib, args.small_files),
                     ensure_ascii=False, indent=2))
