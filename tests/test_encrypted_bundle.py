import tempfile
import unittest
from pathlib import Path

import py7zr

from main import create_encrypted_bundle


class EncryptedBundleTests(unittest.TestCase):
    def test_encrypted_bundle_round_trip_and_password_record(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_2025 = root / "2025"
            source_2026 = root / "2026"
            output = root / "output"
            source_2025.mkdir()
            source_2026.mkdir()
            output.mkdir()
            password_dir = root / "private-passwords"
            password_dir.mkdir()

            file_2025 = source_2025 / "report.pdf"
            file_2026 = source_2026 / "report.pdf"
            unique_file = root / "summary.txt"
            file_2025.write_bytes(b"report from 2025")
            file_2026.write_bytes(b"report from 2026")
            unique_file.write_text("summary", encoding="utf-8")

            archive_path, password_path = create_encrypted_bundle(
                [str(file_2025), str(file_2026), str(unique_file), str(file_2025)],
                str(output),
                password_file=str(password_dir / "password.txt"),
            )

            archive = Path(archive_path)
            password_record = Path(password_path)
            self.assertTrue(archive.is_file())
            self.assertTrue(password_record.is_file())

            text = password_record.read_text(encoding="utf-8-sig")
            password_line = next(line for line in text.splitlines() if line.startswith("密码："))
            password = password_line.split("：", 1)[1]
            self.assertEqual(len(password), 32)
            self.assertIn("report.pdf -> 2025/report.pdf", text)
            self.assertIn("report.pdf -> 2026/report.pdf", text)
            self.assertIn("summary.txt -> summary.txt", text)

            with py7zr.SevenZipFile(archive, mode="r", password=password) as encrypted:
                names = encrypted.getnames()
                self.assertEqual(set(names), {"2025/report.pdf", "2026/report.pdf", "summary.txt"})
                self.assertIsNone(encrypted.testzip())

            extracted = root / "extracted"
            extracted.mkdir()
            with py7zr.SevenZipFile(archive, mode="r", password=password) as encrypted:
                encrypted.extractall(path=extracted)

            self.assertEqual((extracted / "2025" / "report.pdf").read_bytes(), b"report from 2025")
            self.assertEqual((extracted / "2026" / "report.pdf").read_bytes(), b"report from 2026")
            self.assertEqual((extracted / "summary.txt").read_text(encoding="utf-8"), "summary")
            self.assertEqual(file_2025.read_bytes(), b"report from 2025")
            self.assertEqual(file_2026.read_bytes(), b"report from 2026")


if __name__ == "__main__":
    unittest.main()
