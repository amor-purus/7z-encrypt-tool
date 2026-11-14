import os
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

from main import deduplicate_files, make_archive_names


class ArchiveNameTests(unittest.TestCase):
    def assert_no_file_directory_conflicts(self, names: list[str]) -> None:
        keys = [tuple(part.rstrip(" .").casefold() for part in name.split("/")) for name in names]
        for index, first in enumerate(keys):
            for other_index, second in enumerate(keys):
                if index == other_index:
                    continue
                self.assertFalse(
                    first == second or first == second[: len(first)] or second == first[: len(second)],
                    msg=f"归档路径发生重名或文件/目录冲突：{names[index]!r}, {names[other_index]!r}",
                )

    def test_later_unique_leaf_name_is_reserved(self) -> None:
        paths = [
            PureWindowsPath(r"C:\sub\a.txt"),
            PureWindowsPath(r"D:\sub\a.txt"),
            PureWindowsPath(r"E:\a_2.txt"),
        ]
        names = make_archive_names(paths)
        self.assertEqual(names[2], "a_2.txt")
        self.assert_no_file_directory_conflicts(names)

    def test_unique_leaf_is_not_used_as_an_ancestor_directory(self) -> None:
        paths = [
            PureWindowsPath(r"C:\x\b.txt"),
            PureWindowsPath(r"D:\x\b.txt"),
            PureWindowsPath(r"E:\y\x"),
        ]
        names = make_archive_names(paths)
        self.assertEqual(names[2], "x")
        self.assert_no_file_directory_conflicts(names)

    def test_file_name_cannot_also_be_a_directory(self) -> None:
        paths = [
            PureWindowsPath(r"C:\x\docs"),
            PureWindowsPath(r"C:\docs\b.txt"),
            PureWindowsPath(r"D:\docs\b.txt"),
        ]
        names = make_archive_names(paths)
        self.assertEqual(names[0], "docs")
        self.assert_no_file_directory_conflicts(names)

    def test_case_insensitive_collisions_are_avoided(self) -> None:
        paths = [
            PureWindowsPath(r"C:\one\Report.PDF"),
            PureWindowsPath(r"D:\two\report.pdf"),
            PureWindowsPath(r"E:\three\REPORT.PDF"),
            PureWindowsPath(r"F:\report_2.pdf"),
        ]
        names = make_archive_names(paths)
        self.assertEqual(names[3], "report_2.pdf")
        self.assert_no_file_directory_conflicts(names)

    def test_empty_input(self) -> None:
        self.assertEqual(make_archive_names([]), [])


class FileDeduplicationTests(unittest.TestCase):
    def test_duplicate_paths_and_symlinks_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.txt"
            alias = Path(folder) / "alias.txt"
            source.write_text("sample", encoding="utf-8")
            try:
                alias.symlink_to(source)
            except (OSError, NotImplementedError):
                self.skipTest("当前环境不允许创建符号链接")

            result = deduplicate_files([source, source, alias])
            self.assertEqual(result, [source.resolve()])

    def test_hard_links_are_removed_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.txt"
            hard_link = Path(folder) / "hard-link.txt"
            source.write_text("sample", encoding="utf-8")
            try:
                os.link(source, hard_link)
            except (OSError, NotImplementedError):
                self.skipTest("当前文件系统不支持创建硬链接")

            result = deduplicate_files([source, hard_link])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], source.resolve())


if __name__ == "__main__":
    unittest.main()
