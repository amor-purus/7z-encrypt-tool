"""Production-flow regression tests: no mocked archive model or writeall()."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import py7zr

import main
from main import EncryptApp, create_encrypted_bundle, make_archive_names


def password_from_record(record: Path) -> str:
    return next(
        line.partition("：")[2]
        for line in record.read_text(encoding="utf-8-sig").splitlines()
        if line.startswith("密码：")
    )


class ProductionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="7z-flow-")
        self.root = Path(self.temporary.name)
        self.out = self.root / "archives"
        self.secrets = self.root / "separate-passwords"
        self.out.mkdir()
        self.secrets.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def bundle(self, paths: list[Path], *, filename: str = "secret.txt") -> tuple[Path, Path, str]:
        record = self.secrets / filename
        archived, saved = create_encrypted_bundle(
            paths, str(self.out), password_file=str(record)
        )
        self.assertEqual(Path(saved).resolve(), record.resolve())
        return Path(archived), record, password_from_record(record)

    def test_unicode_normalization_collision_is_detected_before_output(self) -> None:
        folder = self.root / "unicode"
        folder.mkdir()
        composed = folder / "\u00e9.txt"
        decomposed = folder / "e\u0301.txt"
        composed.write_bytes(b"one")
        try:
            decomposed.write_bytes(b"two")
        except OSError as exc:
            self.skipTest(f"Filesystem cannot create decomposed filename: {exc}")
        if len(list(folder.iterdir())) != 2:
            self.skipTest("Filesystem normalizes both names to the same entry")
        with self.assertRaises(ValueError) as caught:
            create_encrypted_bundle([folder], str(self.out),
                                    password_file=str(self.secrets / "unicode.txt"))
        self.assertIn(str(composed.resolve()), str(caught.exception))
        self.assertIn(str(decomposed.resolve()), str(caught.exception))
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertEqual(list(self.secrets.iterdir()), [])
        self.assertEqual(composed.read_bytes(), b"one")
        self.assertEqual(decomposed.read_bytes(), b"two")

    def test_same_file_name_in_different_source_directories(self) -> None:
        first = self.root / "甲" / "report.txt"
        second = self.root / "乙" / "report.txt"
        first.parent.mkdir()
        second.parent.mkdir()
        first.write_bytes(b"A")
        second.write_bytes(b"B")
        archive, _, pwd = self.bundle([first, second])
        with py7zr.SevenZipFile(archive, "r", password=pwd) as reader:
            self.assertEqual(set(reader.getnames()), {"甲/report.txt", "乙/report.txt"})
        target = self.root / "unpacked"
        with py7zr.SevenZipFile(archive, "r", password=pwd) as reader:
            reader.extractall(path=target)
        self.assertEqual((target / "甲/report.txt").read_bytes(), b"A")
        self.assertEqual((target / "乙/report.txt").read_bytes(), b"B")

    def test_source_equals_cwd_and_nested_empty_chinese_japanese(self) -> None:
        folder = self.root / "資料-日本語"
        (folder / "中文" / "空目录").mkdir(parents=True)
        (folder / "中文" / "例.txt").write_bytes("你好、日本語".encode("utf-8"))
        original = Path.cwd()
        try:
            os.chdir(folder)
            archive, _, pwd = self.bundle([folder])
        finally:
            os.chdir(original)
        with self.assertRaises(py7zr.PasswordRequired):
            with py7zr.SevenZipFile(archive, "r", password=None) as reader:
                reader.getnames()
        with py7zr.SevenZipFile(archive, "r", password=pwd) as reader:
            self.assertEqual(
                set(name.rstrip("/") for name in reader.getnames()),
                {"資料-日本語", "資料-日本語/中文", "資料-日本語/中文/空目录",
                 "資料-日本語/中文/例.txt"},
            )
            self.assertIsNone(reader.testzip())
        unpacked = self.root / "unpacked"
        with py7zr.SevenZipFile(archive, "r", password=pwd) as reader:
            reader.extractall(path=unpacked)
        self.assertTrue((unpacked / "資料-日本語/中文/空目录").is_dir())
        self.assertEqual((unpacked / "資料-日本語/中文/例.txt").read_bytes(),
                         "你好、日本語".encode("utf-8"))
        self.assertEqual((folder / "中文/例.txt").read_bytes(),
                         "你好、日本語".encode("utf-8"))

    def test_source_contains_cwd(self) -> None:
        folder = self.root / "parent"
        subdir = folder / "child"
        subdir.mkdir(parents=True)
        (subdir / "content.txt").write_bytes(b"unchanged")
        original = Path.cwd()
        try:
            os.chdir(subdir)
            archive, _, pwd = self.bundle([folder])
        finally:
            os.chdir(original)
        with py7zr.SevenZipFile(archive, "r", password=pwd) as reader:
            self.assertEqual(
                set(reader.getnames()), {"parent", "parent/child", "parent/child/content.txt"}
            )
        self.assertEqual((subdir / "content.txt").read_bytes(), b"unchanged")

    def test_password_save_failure_does_not_publish_archive(self) -> None:
        source = self.root / "source.txt"
        source.write_bytes(b"keep me")
        with mock.patch("main.tempfile.mkstemp", side_effect=PermissionError("password denied")):
            with self.assertRaisesRegex(PermissionError, "password denied"):
                self.bundle([source])
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertEqual(list(self.secrets.iterdir()), [])
        self.assertEqual(source.read_bytes(), b"keep me")

    def test_archive_write_failure_cleans_up(self) -> None:
        source = self.root / "source.txt"
        source.write_bytes(b"keep me")
        with mock.patch.object(py7zr.SevenZipFile, "write", side_effect=OSError("disk error")):
            with self.assertRaisesRegex(OSError, "disk error"):
                self.bundle([source])
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertEqual(list(self.secrets.iterdir()), [])
        self.assertEqual(source.read_bytes(), b"keep me")

    def test_password_path_must_be_separate_and_must_not_overwrite(self) -> None:
        source = self.root / "file.txt"
        source.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "不同于压缩包"):
            create_encrypted_bundle([source], str(self.out),
                                    password_file=str(self.out / "secret.txt"))
        record = self.secrets / "occupied.txt"
        record.write_text("original")
        with self.assertRaises(FileExistsError):
            create_encrypted_bundle([source], str(self.out),
                                    password_file=str(record))
        self.assertEqual(record.read_text(), "original")
        self.assertEqual(list(self.out.iterdir()), [])


class DummyControl:
    def __init__(self):
        self.last = None
        self.stopped = False
    def state(self, value):
        self.last = value
    def start(self, *args):
        self.stopped = False
    def stop(self):
        self.stopped = True


class DummyStatus:
    def __init__(self):
        self.value = None
    def set(self, value):
        self.value = value


class DummyRoot:
    def __init__(self):
        self.destroyed = False
    def after(self, delay, callback, *args):
        callback(*args)
    def destroy(self):
        self.destroyed = True


class ImmediateThread:
    def __init__(self, target, **_):
        self.target = target
    def start(self):
        self.target()


class GuiFailureRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="7z-gui-")
        self.rootdir = Path(self.temporary.name)
        self.out = self.rootdir / "output"
        self.secrets = self.rootdir / "keys"
        self.out.mkdir()
        self.secrets.mkdir()
        self.source = self.rootdir / "source.txt"
        self.source.write_bytes(b"keep")
        self.app = object.__new__(EncryptApp)
        self.app.root = DummyRoot()
        self.app.is_busy = False
        self.app.log_file = None
        self.app.queue_items = [self.source]
        self.app.status_var = DummyStatus()
        self.app.progress = DummyControl()
        self.app.control_buttons = [DummyControl() for _ in range(5)]

    def tearDown(self):
        self.temporary.cleanup()

    def _start_and_fail(self, failure):
        with (
            mock.patch("main.filedialog.askdirectory", return_value=str(self.out)),
            mock.patch("main.filedialog.asksaveasfilename",
                       return_value=str(self.secrets / "password.txt")),
            mock.patch("main.messagebox.askokcancel", return_value=True),
            mock.patch("main.messagebox.showerror") as showerror,
            mock.patch("main.threading.Thread", ImmediateThread),
            mock.patch("main.create_encrypted_bundle", side_effect=failure),
        ):
            self.app.start_encryption()
        self.assertFalse(self.app.is_busy)
        self.assertTrue(self.app.progress.stopped)
        self.assertTrue(all(button.last == ["!disabled"] for button in self.app.control_buttons))
        showerror.assert_called_once()
        self.assertIn(str(failure), showerror.call_args.args[1])
        self.assertNotIn("详细日志", showerror.call_args.args[1])
        self.app.on_close()
        self.assertTrue(self.app.root.destroyed)

    def test_password_failure_restores_controls_and_close(self):
        self._start_and_fail(PermissionError("password record failed"))

    def test_archive_failure_restores_controls_and_close(self):
        self._start_and_fail(OSError("archive write failed"))

    def test_log_directory_unavailable_preserves_original_error(self):
        with mock.patch("main.app_data_dir", side_effect=PermissionError("logs blocked")):
            self.assertIsNone(main.configure_logging())
        with mock.patch("main.messagebox.showerror") as showerror:
            self.app.is_busy = True
            self.app.finish_error("original packaging failure")
        self.assertFalse(self.app.is_busy)
        self.assertIn("original packaging failure", showerror.call_args.args[1])
        self.assertNotIn("详细日志", showerror.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
