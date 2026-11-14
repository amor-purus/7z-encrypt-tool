from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import py7zr

from main import create_encrypted_bundle, deduplicate_items


class DirectoryBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="7z-bundle-tests-")
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.output.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_bundle(self, items: list[Path]) -> tuple[Path, Path, str, set[str]]:
        archive_name, txt_name = create_encrypted_bundle(
            [str(item) for item in items], str(self.output)
        )
        archive_path = Path(archive_name)
        txt_path = Path(txt_name)
        text = txt_path.read_text(encoding="utf-8-sig")
        password_line = next(line for line in text.splitlines() if line.startswith("密码："))
        password = password_line.split("：", 1)[1]
        with self.assertRaises(py7zr.PasswordRequired):
            with py7zr.SevenZipFile(str(archive_path), mode="r", password=None) as archive:
                archive.getnames()
        with py7zr.SevenZipFile(str(archive_path), mode="r", password=password) as archive:
            names = {name.rstrip("/") for name in archive.getnames()}
            self.assertIsNone(archive.testzip())
        return archive_path, txt_path, password, names

    def test_single_folder_preserves_nested_and_empty_directories(self) -> None:
        folder = self.root / "project"
        empty = folder / "nested" / "empty"
        payload = folder / "nested" / "deep" / "payload.txt"
        empty.mkdir(parents=True)
        payload.parent.mkdir(parents=True)
        payload.write_text("nested data", encoding="utf-8")

        archive_path, txt_path, password, names = self._create_bundle([folder])

        self.assertEqual(
            names,
            {
                "project",
                "project/nested",
                "project/nested/empty",
                "project/nested/deep",
                "project/nested/deep/payload.txt",
            },
        )
        record = txt_path.read_text(encoding="utf-8-sig")
        self.assertIn("- [文件夹] project -> project", record)

        extract_to = self.root / "extract"
        extract_to.mkdir()
        with py7zr.SevenZipFile(str(archive_path), mode="r", password=password) as archive:
            archive.extractall(path=extract_to)
        self.assertEqual(
            (extract_to / "project" / "nested" / "deep" / "payload.txt").read_text(
                encoding="utf-8"
            ),
            "nested data",
        )
        self.assertTrue((extract_to / "project" / "nested" / "empty").is_dir())

    def test_duplicate_folder_names_are_disambiguated(self) -> None:
        first = self.root / "Client A" / "Photos"
        second = self.root / "Client B" / "Photos"
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        (first / "one.txt").write_text("first", encoding="utf-8")
        (second / "two.txt").write_text("second", encoding="utf-8")

        archive_path, txt_path, _password, names = self._create_bundle([first, second])

        record = txt_path.read_text(encoding="utf-8-sig")
        self.assertIn("[文件夹] Photos -> Client A/Photos", record)
        self.assertIn("[文件夹] Photos -> Client B/Photos", record)
        self.assertIn("Client A/Photos/one.txt", names)
        self.assertIn("Client B/Photos/two.txt", names)
        self.assertTrue(archive_path.is_file())

    def test_mixed_file_and_folder_avoids_internal_member_collision(self) -> None:
        folder = self.root / "source-folder"
        internal = folder / "shared.txt"
        internal.parent.mkdir()
        internal.write_text("inside", encoding="utf-8")

        standalone = self.root / "outside" / "source-folder" / "shared.txt"
        standalone.parent.mkdir(parents=True)
        standalone.write_text("outside", encoding="utf-8")

        other = self.root / "other" / "shared.txt"
        other.parent.mkdir(parents=True)
        other.write_text("other", encoding="utf-8")

        archive_path, txt_path, _password, names = self._create_bundle(
            [folder, standalone, other]
        )

        self.assertIn("source-folder/shared.txt", names)
        self.assertIn("outside/source-folder/shared.txt", names)
        self.assertIn("other/shared.txt", names)
        record = txt_path.read_text(encoding="utf-8-sig")
        self.assertIn("[文件夹] source-folder -> source-folder", record)
        self.assertIn("[文件] shared.txt -> outside/source-folder/shared.txt", record)
        self.assertTrue(archive_path.is_file())

    def test_folder_and_extensionless_file_name_conflict(self) -> None:
        folder = self.root / "Archive"
        folder.mkdir()
        (folder / "contents.txt").write_text("folder", encoding="utf-8")

        standalone = self.root / "Loose" / "Archive"
        standalone.parent.mkdir()
        standalone.write_text("file", encoding="utf-8")

        _archive, txt_path, _password, names = self._create_bundle([folder, standalone])

        record = txt_path.read_text(encoding="utf-8-sig")
        self.assertIn("[文件夹] Archive -> ", record)
        self.assertIn("[文件] Archive -> Loose/Archive", record)
        self.assertIn("/Archive", record)
        self.assertEqual(len(names), len({name.casefold() for name in names}))

    def test_single_file_still_works(self) -> None:
        source = self.root / "standalone.txt"
        source.write_text("original file", encoding="utf-8")

        _archive, txt_path, _password, names = self._create_bundle([source])

        self.assertEqual(names, {"standalone.txt"})
        self.assertIn("- [文件] standalone.txt -> standalone.txt", txt_path.read_text(encoding="utf-8-sig"))

    def test_parent_folder_selection_subsumes_selected_children(self) -> None:
        folder = self.root / "parent"
        child_folder = folder / "child"
        child_folder.mkdir(parents=True)
        child_file = child_folder / "file.txt"
        child_file.write_text("data", encoding="utf-8")

        normalized = deduplicate_items([child_file, child_folder, folder])
        self.assertEqual(normalized, [folder.resolve()])

    def test_output_inside_source_folder_is_rejected_before_temp_archive(self) -> None:
        source = self.root / "source"
        nested_output = source / "output"
        nested_output.mkdir(parents=True)
        (source / "original.txt").write_text("must not be archived", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "输出文件夹位于待加密文件夹内部"):
            create_encrypted_bundle([str(source)], str(nested_output))

        self.assertEqual(list(nested_output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
