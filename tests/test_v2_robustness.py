"""Robustness tests for scale, source mutation and disk failure."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import main


class StressTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        old = main.app_data_dir
        main.app_data_dir = lambda: self.root / "local"
        self.addCleanup(setattr, main, "app_data_dir", old)
        self.src, self.out, self.keys = (self.root / n for n in ("src", "out", "keys"))
        for path in (self.src, self.out, self.keys):
            path.mkdir()

    def _run(self, **kw):
        return main.create_encrypted_bundle([self.src], str(self.out),
            password_file=str(self.keys / "password.txt"), **kw)

    def test_150_nested_unicode_files_and_empty_directory(self):
        for i in range(150):
            folder = self.src / ("日文" if i % 2 else "中文") / str(i // 10)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"file_{i:03}.dat").write_bytes(bytes([i % 256]) * (i + 1))
        (self.src / "empty").mkdir()
        archive, record = self._run()
        self.assertGreater(Path(archive).stat().st_size, 0)
        self.assertTrue(Path(record).is_file())

    def test_injected_fsync_error_aborts_without_final_archive(self):
        (self.src / "test.txt").write_text("test")
        original = main.os.fsync
        seen = 0
        def fail_on_third(fd):
            nonlocal seen
            seen += 1
            if seen == 3:
                raise OSError("synthetic disk error")
            return original(fd)
        with mock.patch.object(main.os, "fsync", side_effect=fail_on_third):
            with self.assertRaises(OSError):
                self._run()
        self.assertFalse(list(self.out.glob("*.7z")))

    def test_modified_input_prevents_publishing(self):
        data = self.src / "data.txt"
        data.write_bytes(b"X" * 5000)
        changed = False
        def mutate(frame):
            nonlocal changed
            if frame.get("stage") == "encrypt" and frame.get("completed_entries", 0) and not changed:
                changed = True
                data.write_bytes(b"Y" * 5000)
        with self.assertRaises(RuntimeError):
            self._run(event_callback=mutate)
        self.assertFalse(list(self.out.glob("*.7z")))


if __name__ == "__main__":
    unittest.main()
