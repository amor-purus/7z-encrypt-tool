"""Independent regressions for review F1-F4 and publication/race boundaries."""
from __future__ import annotations

import io
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import py7zr

import main
from main import EncryptApp, create_encrypted_bundle, deduplicate_items
from test_workflow_integration import (
    DummyControl, DummyRoot, DummyStatus, password_from_record,
)


class ReviewProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="review-v140-")
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "output"
        self.keys = self.root / "passwords"
        self.output.mkdir()
        self.keys.mkdir()
        self.appdata = self.root / "appdata"
        self.appdata.mkdir()
        self.patch_appdata = mock.patch("main.app_data_dir", return_value=self.appdata)
        self.patch_appdata.start()
        self.addCleanup(self.patch_appdata.stop)

    def tearDown(self):
        self.temp.cleanup()

    def _case_sensitive(self, folder: Path) -> None:
        folder.mkdir()
        if os.name == "nt":
            try:
                cmd = subprocess.run(
                    ["fsutil.exe", "file", "setCaseSensitiveInfo", str(folder), "enable"],
                    capture_output=True, timeout=15, text=True,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.skipTest(f"Cannot enable case-sensitive NTFS folder: {exc}")
            if cmd.returncode != 0:
                self.skipTest("Windows runner does not permit per-directory NTFS case sensitivity: "
                              + cmd.stderr.strip())

    def _create(self, items, record_name="key.txt"):
        record = self.keys / record_name
        archive, saved = create_encrypted_bundle(
            items, str(self.output), password_file=str(record)
        )
        self.assertEqual(Path(saved).resolve(), record.resolve())
        return Path(archive), record, password_from_record(record)

    def _extract(self, archive, password):
        target = self.root / "extract"
        target.mkdir()
        with py7zr.SevenZipFile(archive, "r", password=password) as reader:
            names = reader.getnames()
            self.assertIsNone(reader.testzip())
        with py7zr.SevenZipFile(archive, "r", password=password) as reader:
            reader.extractall(path=target)
        return names, target

    def test_case_sensitive_ntfs_distinct_file_names_not_lost(self):
        folder = self.root / "sensitive"
        self._case_sensitive(folder)
        lower = folder / "a.txt"
        upper = folder / "A.txt"
        lower.write_bytes(b"lower")
        upper.write_bytes(b"UPPER")
        if len(list(folder.iterdir())) != 2:
            self.skipTest("Filesystem cannot represent case-sensitive siblings")
        self.assertEqual(len(deduplicate_items([lower, upper])), 2)
        archive, _, pwd = self._create([lower, upper])
        names, target = self._extract(archive, pwd)
        self.assertEqual(len(names), 2)
        self.assertEqual(
            sorted(p.read_bytes() for p in target.rglob("*.txt")),
            sorted([b"lower", b"UPPER"])
        )
        self.assertEqual(lower.read_bytes(), b"lower")
        self.assertEqual(upper.read_bytes(), b"UPPER")

    def test_case_sensitive_ntfs_parent_containment_not_assumed(self):
        folder = self.root / "sensitive"
        self._case_sensitive(folder)
        top = folder / "Top"
        other = folder / "top"
        top.mkdir()
        other.mkdir()
        (top / "inside.txt").write_bytes(b"inside")
        target = other / "target.txt"
        target.write_bytes(b"target")
        if len([p for p in folder.iterdir() if p.is_dir()]) != 2:
            self.skipTest("Filesystem cannot represent Top/top siblings")
        self.assertEqual(len(deduplicate_items([top, target])), 2)
        archive, _, pwd = self._create([top, target])
        names, result = self._extract(archive, pwd)
        self.assertEqual(len(names), 3)
        self.assertEqual(
            sorted(p.read_bytes() for p in result.rglob("*.txt")),
            sorted([b"inside", b"target"])
        )

    def test_precise_interrupt_after_archive_publish_does_not_erase_key(self):
        payload = self.root / "file.txt"
        payload.write_bytes(b"must always be recoverable")
        actual_publish = main._publish_without_overwrite

        def interrupt_after_actual_publish(src, dst):
            actual_publish(src, dst)
            if dst.suffix == ".7z":
                raise KeyboardInterrupt("injected after successful archive publication")

        with mock.patch.object(main, "_publish_without_overwrite",
                               side_effect=interrupt_after_actual_publish):
            with self.assertRaises(KeyboardInterrupt):
                self._create([payload])

        records = list(self.keys.glob("*.txt"))
        archives = list(self.output.glob("*.7z"))
        self.assertEqual(len(records), 1)
        self.assertEqual(len(archives), 1)
        password = password_from_record(records[0])
        _, out = self._extract(archives[0], password)
        self.assertEqual((out / "file.txt").read_bytes(), payload.read_bytes())

    def test_archive_publish_error_rolls_back_password(self):
        payload = self.root / "original.txt"
        payload.write_bytes(b"never modify")
        real_publish = main._publish_without_overwrite

        def fail_archive_publish(src, dst):
            if dst.suffix == ".7z":
                raise OSError("archive rename denied")
            return real_publish(src, dst)

        with mock.patch.object(main, "_publish_without_overwrite",
                               side_effect=fail_archive_publish):
            with self.assertRaisesRegex(OSError, "archive rename denied"):
                self._create([payload])
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.keys.iterdir()), [])
        self.assertEqual(payload.read_bytes(), b"never modify")

    def test_interrupt_after_password_publish_before_archive_cleans_pair(self):
        payload = self.root / "original.txt"
        payload.write_bytes(b"stable")
        actual_publish = main._publish_without_overwrite

        def interrupt_after_password(src, dst):
            actual_publish(src, dst)
            if dst.name == "key.txt":
                raise KeyboardInterrupt("injected immediately after password rename")

        with mock.patch.object(main, "_publish_without_overwrite",
                               side_effect=interrupt_after_password):
            with self.assertRaises(KeyboardInterrupt):
                self._create([payload])
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.keys.iterdir()), [])

    def test_archive_target_race_never_overwrites_existing_file(self):
        payload = self.root / "original.txt"
        payload.write_bytes(b"stable")
        conflict = self.output / "racing-name.7z"
        actual_publish = main._publish_without_overwrite

        def create_competitor_before_archive(src, dst):
            if dst == conflict:
                conflict.write_bytes(b"competing archive must not be overwritten")
            return actual_publish(src, dst)

        with (mock.patch.object(main, "make_archive_base", return_value="racing-name"),
              mock.patch.object(main, "_publish_without_overwrite",
                                side_effect=create_competitor_before_archive)):
            with self.assertRaises(FileExistsError):
                self._create([payload])
        self.assertEqual(conflict.read_bytes(), b"competing archive must not be overwritten")
        self.assertEqual(list(self.keys.iterdir()), [])
        self.assertEqual(list(self.output.iterdir()), [conflict])

    def test_rollback_failure_explicitly_identifies_residual_password(self):
        payload = self.root / "original.txt"
        payload.write_bytes(b"stable")
        target = self.keys / "key.txt"
        actual_publish = main._publish_without_overwrite
        actual_unlink = Path.unlink

        def fail_archive(src, dst):
            if dst.suffix == ".7z":
                raise OSError("publish failed")
            return actual_publish(src, dst)

        def block_password_removal(path, *args, **kwargs):
            if str(path) == str(target):
                raise PermissionError("rollback denied")
            return actual_unlink(path, *args, **kwargs)

        with (mock.patch.object(main, "_publish_without_overwrite", side_effect=fail_archive),
              mock.patch.object(Path, "unlink", block_password_removal)):
            with self.assertRaisesRegex(RuntimeError, "明文密码仍可能保留在") as raised:
                self._create([payload])
        self.assertIn(str(target), str(raised.exception))
        self.assertTrue(target.exists())
        self.assertEqual(list(self.output.iterdir()), [])


    def test_archive_rewrite_after_verification_is_detected(self):
        payload = self.root / "original.txt"
        payload.write_bytes(b"original")
        original_mkstemp = tempfile.mkstemp

        def replace_after_verification(*args, **kwargs):
            if str(kwargs.get("prefix", "")).startswith(".7z-password-PLAINTEXT-"):
                temporary_archive = next(self.output.glob("*.incomplete.7z"))
                temporary_archive.write_bytes(b"attacker replaced verified archive")
            return original_mkstemp(*args, **kwargs)

        with mock.patch("main.tempfile.mkstemp", side_effect=replace_after_verification):
            with self.assertRaisesRegex(RuntimeError, "暂存归档发生变化"):
                self._create([payload])
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.keys.iterdir()), [])

    def test_source_replaced_during_write_is_detected(self):
        payload = self.root / "replace-me.txt"
        payload.write_bytes(b"original")
        original_write = py7zr.SevenZipFile.write

        def write_then_mutate(archive, filename, arcname=None):
            result = original_write(archive, filename, arcname=arcname)
            payload.write_bytes(b"changed")
            return result

        with mock.patch.object(py7zr.SevenZipFile, "write", write_then_mutate):
            with self.assertRaisesRegex(RuntimeError, "源文件已被修改"):
                self._create([payload])
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.keys.iterdir()), [])

    def test_incomplete_password_artifact_discovery_never_deletes(self):
        source = self.output / ".7z-archive-demo-rand.incomplete.7z"
        secret = self.keys / ".7z-password-PLAINTEXT-demo-rand.incomplete.txt"
        source.write_bytes(b"encrypted staging")
        secret.write_text("potential plaintext")
        found = main.find_interrupted_artifacts(self.output, self.keys)
        self.assertEqual(set(found), {source, secret})
        self.assertTrue(source.exists())
        self.assertTrue(secret.exists())


class FailingThread:
    def __init__(self, target, **kwargs):
        self.target = target
    def start(self):
        raise RuntimeError("thread start denied")


class ReviewGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="review-gui-")
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "output"
        self.keys = self.root / "keys"
        self.output.mkdir()
        self.keys.mkdir()
        source = self.root / "source.txt"
        source.write_bytes(b"static")
        self.app = object.__new__(EncryptApp)
        self.app.root = DummyRoot()
        self.app.is_busy = False
        self.app.log_file = None
        self.app.queue_items = [source]
        self.app.status_var = DummyStatus()
        self.app.progress = DummyControl()
        self.app.cancel_button = DummyControl()
        self.app.cancel_event = threading.Event()
        self.app.password_mode = DummyStatus()
        self.app.password_mode.value = "plaintext"
        self.app.password_mode.get = lambda: self.app.password_mode.value
        self.app.control_buttons = [DummyControl() for _ in range(5)]

    def tearDown(self):
        self.temp.cleanup()

    def _inputs(self):
        return (
            mock.patch("main.filedialog.askdirectory", return_value=str(self.output)),
            mock.patch("main.filedialog.asksaveasfilename",
                       return_value=str(self.keys / "key.txt")),
            mock.patch("main.messagebox.askokcancel", return_value=True),
        )

    def _assert_recovered(self):
        self.assertFalse(self.app.is_busy)
        self.assertTrue(self.app.progress.stopped)
        self.assertTrue(all(c.last == ["!disabled"] for c in self.app.control_buttons))
        self.app.on_close()
        self.assertTrue(self.app.root.destroyed)

    def test_thread_construction_failure_restores_gui(self):
        a, b, c = self._inputs()
        with (a, b, c, mock.patch("main.messagebox.showerror") as show,
              mock.patch("main.threading.Thread", side_effect=RuntimeError("thread ctor denied"))):
            self.app.start_encryption()
        self._assert_recovered()
        self.assertIn("thread ctor denied", show.call_args.args[1])

    def test_thread_start_failure_restores_gui(self):
        a, b, c = self._inputs()
        with (a, b, c, mock.patch("main.messagebox.showerror") as show,
              mock.patch("main.threading.Thread", FailingThread)):
            self.app.start_encryption()
        self._assert_recovered()
        self.assertIn("thread start denied", show.call_args.args[1])

    def test_closed_stderr_and_real_worker_failure_restores_gui(self):
        broken = io.StringIO()
        broken.close()
        with (mock.patch("main.app_data_dir", side_effect=OSError("logs denied")),
              mock.patch("main.sys.stderr", broken)):
            self.assertIsNone(main.configure_logging())
        completed = threading.Event()

        def report_error(*args, **kwargs):
            completed.set()

        a, b, c = self._inputs()
        with (a, b, c, mock.patch("main.messagebox.showerror", side_effect=report_error) as show,
              mock.patch("main.create_encrypted_bundle", side_effect=OSError("original error"))):
            self.app.start_encryption()
            self.assertTrue(completed.wait(12), "Worker did not schedule UI error recovery")
        self._assert_recovered()
        self.assertIn("original error", show.call_args.args[1])
        self.assertNotIn("详细日志", show.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
