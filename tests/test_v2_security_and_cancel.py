"""Windows DPAPI and cooperative cancellation regression tests."""
import os
from pathlib import Path
import tempfile
import threading
import unittest

import main
import password_store


class RecordTests(unittest.TestCase):
    def test_plaintext_and_invalid_records(self):
        self.assertEqual(password_store.encode_record("密码 abc", "plaintext").decode("utf-8-sig"), "密码 abc")
        with self.assertRaises(ValueError):
            password_store.encode_record("secret", "invalid")
        with self.assertRaises(ValueError):
            password_store.decode_record(b"ordinary plaintext")

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_dpapi_encrypted_roundtrip_export_and_corruption(self):
        protected = password_store.encode_record("密码：Sensitive123\n", "dpapi")
        self.assertTrue(protected.startswith(password_store.MAGIC))
        self.assertNotIn(b"Sensitive123", protected)
        self.assertEqual(password_store.decode_record(protected), "密码：Sensitive123\n")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "secure.txt"
            dst = Path(td) / "export.txt"
            src.write_bytes(protected)
            password_store.export_plaintext(str(src), str(dst))
            self.assertIn("Sensitive123", dst.read_text(encoding="utf-8-sig"))
            with self.assertRaises(FileExistsError):
                password_store.export_plaintext(str(src), str(dst))
        with self.assertRaises(ValueError):
            password_store.decode_record(password_store.MAGIC + b"***garbled***")


class CancelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        original = main.app_data_dir
        main.app_data_dir = lambda: self.root / "local"
        self.addCleanup(setattr, main, "app_data_dir", original)
        self.src = self.root / "input.txt"
        self.src.write_text("sample" * 6000)
        self.out = self.root / "output"
        self.keys = self.root / "keys"
        self.out.mkdir()
        self.keys.mkdir()

    def _run(self, **kw):
        return main.create_encrypted_bundle([self.src], str(self.out),
            password_file=str(self.keys / "password.txt"), **kw)

    def test_pre_cancel_no_output(self):
        signal = threading.Event()
        signal.set()
        with self.assertRaises(main.TaskCancelled):
            self._run(cancel_event=signal)
        self.assertFalse(list(self.out.iterdir()))
        self.assertFalse(list(self.keys.iterdir()))

    def test_cancel_during_archive_still_rolls_back(self):
        signal = threading.Event()
        events = []
        def observe(x):
            events.append(x)
            if x.get("stage") == "encrypt" and x.get("completed_entries", 0):
                signal.set()
        with self.assertRaises(main.TaskCancelled):
            self._run(cancel_event=signal, event_callback=observe)
        self.assertTrue(events)
        self.assertFalse(list(self.out.iterdir()))
        self.assertFalse(list(self.keys.iterdir()))
        self.assertEqual(main.recover_interrupted_transactions()[1], [])

    def test_exact_byte_progress_and_stage_sequence(self):
        events = []
        archive, record = self._run(event_callback=events.append)
        self.assertTrue(Path(archive).is_file())
        self.assertTrue(Path(record).is_file())
        frames = [x for x in events if x.get("stage") == "encrypt"]
        self.assertEqual(frames[-1]["completed_bytes"], self.src.stat().st_size)
        self.assertEqual(frames[-1]["total_bytes"], self.src.stat().st_size)
        self.assertEqual([x["stage"] for x in events[-2:]], ["verify", "publish"])

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_dpapi_record_is_usable_after_archive_creation(self):
        archive, record = self._run(password_mode="dpapi")
        content = Path(record).read_bytes()
        self.assertTrue(Path(archive).is_file())
        self.assertTrue(content.startswith(password_store.MAGIC))
        self.assertIn("密码：", password_store.decode_record(content))
        self.assertEqual(main.recover_interrupted_transactions()[1], [])


if __name__ == "__main__":
    unittest.main()
