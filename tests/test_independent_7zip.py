"""Cross-implementation 7z interoperability and independent content hash verification."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import main


def checksum(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def executable():
    for candidate in (os.environ.get("SEVEN_ZIP_EXE"), shutil.which("7z"),
                      r"C:\Program Files\7-Zip\7z.exe",
                      r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


class Independent7ZipTests(unittest.TestCase):
    def test_official_7zip_extracts_compatible_archive(self):
        exe = executable()
        if not exe:
            if os.environ.get("REQUIRE_EXTERNAL_7Z") == "1":
                self.fail("独立官方7z.exe缺失，不允许发布")
            self.skipTest("官方7z.exe未安装")
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            old = main.app_data_dir
            main.app_data_dir = lambda: tmp / "local"
            try:
                source = tmp / "源文件"
                source.mkdir()
                (source / "日本語.txt").write_text("こんにちは\n" * 100, encoding="utf-8")
                (source / "random.dat").write_bytes(os.urandom(8192))
                (source / "空目录").mkdir()
                out, pwd, extract = (tmp / name for name in ("out", "password", "extracted"))
                for directory in (out, pwd, extract):
                    directory.mkdir()
                archive, record = main.create_encrypted_bundle(
                    [source], str(out), password_file=str(pwd / "key.txt"))
                password = Path(record).read_text(encoding="utf-8-sig").split("密码：", 1)[1].splitlines()[0]
                wrong = subprocess.run([exe, "t", archive, "-pWRONGPASSWORD", "-y"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                self.assertNotEqual(wrong.returncode, 0)
                checked = subprocess.run([exe, "x", archive, "-p" + password, "-y", "-o" + str(extract)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
                self.assertEqual(checked.returncode, 0, "官方7-Zip独立解密失败")
                actual = extract / "源文件"
                self.assertTrue((actual / "空目录").is_dir())
                for filename in ("日本語.txt", "random.dat"):
                    self.assertEqual(checksum(actual / filename), checksum(source / filename))
            finally:
                main.app_data_dir = old


if __name__ == "__main__":
    unittest.main()
