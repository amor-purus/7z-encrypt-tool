# -*- coding: utf-8 -*-
"""7z 文件加密工具。

发布版通过 PyInstaller 制作为 Windows 独立 GUI EXE。
普通用户无需安装 Python、pip、虚拟环境或命令行启动器。
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import secrets
import string
import sys
import tempfile
import threading
import traceback
import unicodedata
from importlib import metadata
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "文件加密工具"
APP_VERSION = "1.3.0"
PASSWORD_LENGTH = 32
ARCHIVE_NAME_LENGTH = 10


def app_data_dir() -> Path:
    """返回当前用户可写的应用数据目录。"""
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    path = base / "7z-Encrypt-Tool"
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_logging() -> Path | None:
    """GUI 版没有控制台，所有异常写入用户日志目录。"""
    try:
        log_dir = app_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "application.log"
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
            encoding="utf-8",
            force=True,
        )
        logging.info("Application started: version=%s frozen=%s", APP_VERSION, bool(getattr(sys, "frozen", False)))
        return log_file
    except OSError:
        # PyInstaller --windowed may set sys.stderr to None.  A default
        # StreamHandler would then raise while reporting the logging failure.
        # Keep the original task exception displayable even without any stream.
        stderr = getattr(sys, "stderr", None)
        handler = logging.StreamHandler(stderr) if stderr is not None else logging.NullHandler()
        logging.basicConfig(
            handlers=[handler],
            level=logging.ERROR,
            format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
            force=True,
        )
        if stderr is not None:
            logging.exception("Could not initialize the application log file")
        return None


def enable_windows_dpi_awareness() -> None:
    """尽可能启用 Windows Per-Monitor V2 DPI 感知，失败时回退且不阻止启动。"""
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        logging.exception("Could not enable Windows DPI awareness")


def make_password(length: int = PASSWORD_LENGTH) -> str:
    """生成包含大小写字母、数字和符号的高强度随机密码。"""
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*_-+="]
    if length < len(groups):
        raise ValueError("密码长度不足。")
    chars = [secrets.choice(group) for group in groups]
    alphabet = "".join(groups)
    chars.extend(secrets.choice(alphabet) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def make_archive_base(output_dir: Path) -> str:
    """生成不会覆盖现有成品或上次中断任务临时文件的归档基名。"""
    alphabet = string.ascii_lowercase + string.digits
    for _ in range(200):
        candidate = "".join(secrets.choice(alphabet) for _ in range(ARCHIVE_NAME_LENGTH))
        names = (
            output_dir / f"{candidate}.7z",
            output_dir / f"{candidate}.txt",
            output_dir / f".{candidate}.working.7z",
            output_dir / f".{candidate}.working.txt",
        )
        if not any(path.exists() for path in names):
            return candidate
    raise RuntimeError("无法生成不重复的随机文件名，请更换输出文件夹。")


def _archive_key(name: str) -> tuple[str, ...]:
    """按 Windows 常见的不区分大小写规则规范化归档路径。"""
    normalized = unicodedata.normalize("NFC", name.replace("\\", "/"))
    return tuple(part.rstrip(" .").casefold() for part in normalized.split("/") if part)


def _directory_layout(source: Path) -> list[tuple[str, bool]]:
    """返回 writeall 会写入的目录树成员；布尔值表示目录项。"""
    layout: list[tuple[str, bool]] = [("", True)]

    def raise_walk_error(error: OSError) -> None:
        raise error

    for current, dirnames, filenames in os.walk(
        source, topdown=True, followlinks=False, onerror=raise_walk_error
    ):
        current_path = Path(current)
        relative_root = current_path.relative_to(source).as_posix()
        normal_directories: list[str] = []

        for dirname in sorted(dirnames):
            child = current_path / dirname
            relative_name = (
                f"{relative_root}/{dirname}" if relative_root != "." else dirname
            )
            if getattr(child, "is_junction", lambda: False)():
                raise ValueError(
                    f"文件夹中包含目录联接，无法安全递归打包：{child}"
                )
            if child.is_symlink():
                # py7zr 默认不解引用符号链接；将其作为一个叶子成员处理。
                layout.append((relative_name, False))
            else:
                layout.append((relative_name, True))
                normal_directories.append(dirname)

        dirnames[:] = normal_directories

        for filename in sorted(filenames):
            child = current_path / filename
            if getattr(child, "is_junction", lambda: False)():
                raise ValueError(
                    f"文件夹中包含目录联接，无法安全递归打包：{child}"
                )
            relative_name = (
                f"{relative_root}/{filename}" if relative_root != "." else filename
            )
            layout.append((relative_name, False))

    # A common archive prefix cannot resolve collisions inside one source tree.
    # Validate the original, unmodified names before trying alternative roots.
    seen: dict[tuple[str, ...], str] = {}
    for relative, _is_directory in layout:
        key = _archive_key(relative)
        if not key:
            continue
        previous = seen.get(key)
        if previous is not None:
            raise ValueError(
                "源目录内部存在无法通过更换归档根目录解决的路径冲突：\n"
                f"{source / previous}\n{source / relative}\n"
                "请先重命名其中一个源文件或文件夹。"
            )
        seen[key] = relative
    return layout


def _candidate_archive_names(source: Path) -> list[str]:
    """依次生成叶子名称、逐层父目录限定名称。"""
    leaf = source.name
    if not leaf:
        leaf = source.drive.rstrip("\\\\/:") or "root"

    segments = [leaf]
    candidates = [leaf]
    current = source.parent
    while current.name:
        segments.insert(0, current.name)
        candidates.append("/".join(segments))
        current = current.parent

    if source.drive:
        drive_label = source.drive.replace("\\", "/").strip("/").rstrip(":")
        drive_parts = [part for part in drive_label.split("/") if part]
        if drive_parts:
            drive_candidate = "/".join(drive_parts + segments)
            if drive_candidate not in candidates:
                candidates.append(drive_candidate)

    return candidates


def make_archive_names(items: list[Path]) -> list[str]:
    """为文件和文件夹分配无冲突的归档路径。

    文件夹会把根目录、子目录和子文件视为一个整体参与冲突检测；
    因而独立文件不能覆盖某个文件夹内部的成员路径。
    """
    if not items:
        return []

    layouts = [
        _directory_layout(path)
        if isinstance(path, Path) and path.is_dir()
        else None
        for path in items
    ]
    leaf_keys = [_archive_key(path.name or path.drive or "root") for path in items]
    leaf_counts: dict[tuple[str, ...], int] = {}
    for key in leaf_keys:
        leaf_counts[key] = leaf_counts.get(key, 0) + 1

    # namespace 同时记录显式成员和隐式父目录。True=目录，False=文件。
    namespace: dict[tuple[str, ...], bool] = {}
    explicit_members: set[tuple[str, ...]] = set()
    result: list[str | None] = [None] * len(items)

    def entries_for(index: int, candidate: str) -> list[tuple[str, bool]]:
        layout = layouts[index]
        if layout is None:
            return [(candidate, False)]
        return [
            (candidate if not relative else f"{candidate}/{relative}", is_directory)
            for relative, is_directory in layout
        ]

    def can_reserve(index: int, candidate: str) -> bool:
        proposed: dict[tuple[str, ...], bool] = {}
        for member, is_directory in entries_for(index, candidate):
            key = _archive_key(member)
            if not key or key in proposed:
                return False
            proposed[key] = is_directory

        for key, is_directory in proposed.items():
            if key in explicit_members:
                return False

            existing = namespace.get(key)
            if existing is not None:
                # 允许把先前仅作为父路径出现的隐式目录升级为显式目录。
                if not (is_directory and existing and key not in explicit_members):
                    return False

            for depth in range(1, len(key)):
                parent = key[:depth]
                if namespace.get(parent) is False:
                    return False
                if proposed.get(parent) is False:
                    return False

        return True

    def reserve(index: int, candidate: str) -> None:
        for member, is_directory in entries_for(index, candidate):
            key = _archive_key(member)
            for depth in range(1, len(key)):
                namespace.setdefault(key[:depth], True)
            namespace[key] = is_directory
            explicit_members.add(key)

    # 先为唯一名称保留原始叶子名，避免重复项抢占唯一名称。
    allocation_order = [
        index for index in range(len(items)) if leaf_counts[leaf_keys[index]] == 1
    ] + [
        index for index in range(len(items)) if leaf_counts[leaf_keys[index]] > 1
    ]

    for index in allocation_order:
        source = items[index]
        candidates = _candidate_archive_names(source)
        if leaf_counts[leaf_keys[index]] > 1:
            # 重名项优先补充父目录，不让第一个项目独占原始叶子名。
            candidates = candidates[1:]

        selected: str | None = None
        for candidate in candidates:
            if can_reserve(index, candidate):
                selected = candidate
                break

        if selected is None:
            if source.is_dir():
                stem, suffix = source.name or "folder", ""
            else:
                stem, suffix = source.stem, source.suffix
            for number in range(2, 1002):
                candidate = f"{stem}_{number}{suffix}"
                if can_reserve(index, candidate):
                    selected = candidate
                    break
            if selected is None:
                raise RuntimeError(
                    f"归档名称重试已达到上限（1000 次）：{source}"
                )

        reserve(index, selected)
        result[index] = selected

    return [name.replace("\\", "/") for name in result if name is not None]


def deduplicate_items(items: list[str | Path]) -> list[Path]:
    """解析路径、按文件身份去重，并自动移除已被父文件夹包含的条目。"""
    resolved: list[Path] = []
    seen_paths: set[str] = set()
    seen_file_ids: set[tuple[int, int]] = set()

    for item in items:
        path = Path(item).resolve()
        if not path.is_file() and not path.is_dir():
            raise FileNotFoundError(f"找不到文件或文件夹：{path}")

        path_key = os.path.normcase(str(path))
        if path_key in seen_paths:
            continue

        stat = path.stat()
        file_id = (stat.st_dev, stat.st_ino)
        if stat.st_ino and file_id in seen_file_ids:
            continue

        seen_paths.add(path_key)
        if stat.st_ino:
            seen_file_ids.add(file_id)
        resolved.append(path)

    # 不论父文件夹是在队列中先添加还是后添加，都只保留父文件夹。
    return [
        path
        for path in resolved
        if not any(
            parent != path
            and parent.is_dir()
            and path.is_relative_to(parent)
            for parent in resolved
        )
    ]


def deduplicate_files(items: list[str | Path]) -> list[Path]:
    """保留旧接口：仅接受文件的调用仍可使用此包装函数。"""
    paths = deduplicate_items(items)
    if any(not path.is_file() for path in paths):
        raise FileNotFoundError("该操作只接受文件。")
    return paths

def _notify_progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        try:
            callback(message)
        except Exception:
            logging.exception("进度通知失败")


def _archive_inventory(
    paths: list[Path], archive_names: list[str]
) -> list[tuple[Path, str]]:
    """按已检查的清单构建单一写入计划，包含根目录和空目录。"""
    inventory: list[tuple[Path, str]] = []
    keys: dict[tuple[str, ...], Path] = {}
    for source, archive_name in zip(paths, archive_names):
        layout = _directory_layout(source) if source.is_dir() else [("", False)]
        for relative, _is_directory in layout:
            actual_path = source / relative if relative else source
            member_name = archive_name if not relative else f"{archive_name}/{relative}"
            key = _archive_key(member_name.rstrip("/"))
            if not key:
                raise ValueError(f"无效归档路径：{actual_path}")
            if key in keys:
                raise ValueError(
                    f"归档成员路径冲突：\n{keys[key]}\n{actual_path}"
                )
            keys[key] = actual_path
            inventory.append((actual_path, member_name))
    return inventory


def _expected_archive_members(paths: list[Path], archive_names: list[str]) -> list[str]:
    return [name for _, name in _archive_inventory(paths, archive_names)]


def create_encrypted_bundle(
    items: list[str | Path],
    output_folder: str,
    progress_callback: Callable[[str], None] | None = None,
    *,
    password_file: str | None = None,
) -> tuple[str, str]:
    """全部验证通过后才发布归档与单独指定的明文密码记录。

    密码记录必须在另一个目录；两个文件分别原子重命名，失败则回滚。
    """
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError("加密组件缺失，请重新下载完整的官方 EXE 版本。") from exc

    paths = deduplicate_items(items)
    if not paths:
        raise ValueError("没有选择文件或文件夹。")

    out_dir = Path(output_folder).resolve()
    if not out_dir.is_dir():
        raise NotADirectoryError("输出位置无效。")
    if not password_file:
        raise ValueError("必须单独选择明文密码 TXT 的保存位置。")

    record = Path(password_file).resolve()
    if not record.parent.is_dir() or record.parent == out_dir:
        raise ValueError("密码 TXT 必须保存到存在的、不同于压缩包输出目录的文件夹。")
    if os.path.lexists(record):
        raise FileExistsError(f"密码记录目标已存在，拒绝覆盖：{record}")

    # No source modification, including accidental plaintext password creation.
    for source in paths:
        if source.is_dir():
            if out_dir == source or out_dir.is_relative_to(source):
                raise ValueError(
                    f"输出文件夹位于待加密文件夹内部：{source}\n"
                    "请将输出位置更换到该源文件夹之外。"
                )
            if record.is_relative_to(source):
                raise ValueError(f"密码记录不能写入待加密源文件夹：{source}")
        elif record == source:
            raise ValueError(f"密码记录不能覆盖待加密源文件：{source}")

    archive_names = make_archive_names(paths)
    inventory = _archive_inventory(paths, archive_names)
    expected_members = [name for _, name in inventory]
    base = make_archive_base(out_dir)
    final_archive = out_dir / f"{base}.7z"
    temp_archive = out_dir / f".{base}.working.7z"
    password = make_password()
    temp_record: Path | None = None
    record_published = False
    archive_published = False

    try:
        _notify_progress(progress_callback, "正在加密打包，请不要关闭工具……")
        with py7zr.SevenZipFile(str(temp_archive), mode="w", password=password) as archive:
            archive.set_encrypted_header(True)
            # writeall() skips the current working directory itself in py7zr.
            # write() preserves every explicitly inventoried entry, even cwd.
            for actual_path, member_name in inventory:
                archive.write(str(actual_path), arcname=member_name)

        if not temp_archive.exists() or temp_archive.stat().st_size == 0:
            raise RuntimeError("压缩组件没有生成有效的 7z 文件。")

        _notify_progress(progress_callback, "正在校验文件头加密和压缩包完整性……")
        try:
            with py7zr.SevenZipFile(str(temp_archive), mode="r", password=None) as no_password:
                no_password.getnames()
        except py7zr.PasswordRequired:
            pass
        else:
            raise RuntimeError("安全校验失败：压缩包文件名没有成功加密。")

        with py7zr.SevenZipFile(str(temp_archive), mode="r", password=password) as check:
            names = check.getnames()
            actual_keys = [_archive_key(name.rstrip("/")) for name in names]
            expected_keys = [_archive_key(name.rstrip("/")) for name in expected_members]
            if (
                len(actual_keys) != len(set(actual_keys))
                or set(actual_keys) != set(expected_keys)
            ):
                missing = sorted(set(expected_keys) - set(actual_keys))
                extra = sorted(set(actual_keys) - set(expected_keys))
                raise RuntimeError(
                    "压缩包成员与预期目录树不一致。"
                    f"缺失：{missing!r}；多出：{extra!r}"
                )
            bad_member = check.testzip()
            if bad_member is not None:
                raise RuntimeError(f"压缩包完整性检查失败：{bad_member}")

        mappings = "\n".join(
            f"- [{'文件夹' if source.is_dir() else '文件'}] {source.name} -> {archive_name}"
            for source, archive_name in zip(paths, archive_names)
        )
        txt_content = (
            f"被加密条目及归档内路径：\n{mappings}\n"
            f"加密后的文件名：{base}.7z\n"
            f"密码：{password}\n"
            f"是否已加密文件名：是\n"
            "警告：此 TXT 包含完整明文密码，须与压缩包分开安全保管。\n"
        )

        # Create and sync the record in its *own* directory, not next to .7z.
        fd, temporary_name = tempfile.mkstemp(
            prefix=".7z-password-", suffix=".working", dir=record.parent
        )
        temp_record = Path(temporary_name)
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="\r\n") as stream:
            stream.write(txt_content)
            stream.flush()
            os.fsync(stream.fileno())

        if os.path.lexists(record) or os.path.lexists(final_archive):
            raise FileExistsError("目标文件已存在，拒绝覆盖，请重新选择位置。")

        # Publish secret first. Never publish a usable archive without a
        # successfully persisted password; roll the secret back if .7z fails.
        os.rename(temp_record, record)
        record_published = True
        os.rename(temp_archive, final_archive)
        archive_published = True
        return str(final_archive), str(record)
    except BaseException:
        if not archive_published and record_published:
            try:
                record.unlink(missing_ok=True)
            except OSError:
                logging.exception("发布失败后无法回滚密码记录：%s", record)
        raise
    finally:
        for temporary_path in (temp_archive, temp_record):
            if temporary_path is None:
                continue
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logging.warning("无法清理临时文件：%s", temporary_path, exc_info=True)


def run_packaged_self_test(report_path: str | None = None) -> int:
    """由 CI 直接运行打包后的 EXE，检查依赖和真实文件夹加密往返。"""
    report: dict[str, object] = {
        "app_version": APP_VERSION,
        "python_version": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
    }

    try:
        import py7zr
        import bcj
        import brotli
        import inflate64
        import multivolumefile
        import psutil
        import pyppmd
        import texttable
        from Cryptodome.Cipher import AES

        modules = {
            "py7zr": py7zr,
            "pybcj": bcj,
            "brotli": brotli,
            "inflate64": inflate64,
            "multivolumefile": multivolumefile,
            "psutil": psutil,
            "pyppmd": pyppmd,
            "texttable": texttable,
            "pycryptodomex": AES,
        }
        package_names = (
            "py7zr",
            "pycryptodomex",
            "pyppmd",
            "pybcj",
            "brotli",
            "inflate64",
            "multivolumefile",
            "psutil",
            "texttable",
        )
        versions = {name: metadata.version(name) for name in package_names}

        with tempfile.TemporaryDirectory(prefix="7z-encrypt-selftest-") as temp:
            root = Path(temp)
            source_dir = root / "smoke-test-folder"
            empty_dir = source_dir / "nested" / "empty"
            payload = source_dir / "nested" / "payload.txt"
            output_dir = root / "archives"
            secret_dir = root / "private-passwords"
            record_path = secret_dir / "record.txt"
            extract_dir = root / "extracted"
            empty_dir.mkdir(parents=True)
            output_dir.mkdir()
            secret_dir.mkdir()
            payload.write_bytes(b"7z folder encryption tool packaged self-test\n")

            # Exercise the production function from inside the source directory.
            old_cwd = Path.cwd()
            try:
                os.chdir(source_dir)
                produced_archive, produced_record = create_encrypted_bundle(
                    [source_dir], str(output_dir), password_file=str(record_path)
                )
            finally:
                os.chdir(old_cwd)
            archive_path = Path(produced_archive)
            if Path(produced_record).resolve() != record_path.resolve() or not record_path.exists():
                raise RuntimeError("业务流程未生成单独保存的密码记录。")
            record_text = record_path.read_text(encoding="utf-8-sig")
            password = next(
                line.partition("：")[2] for line in record_text.splitlines()
                if line.startswith("密码：")
            )
            if len(password) != PASSWORD_LENGTH:
                raise RuntimeError("业务流程生成的密码长度错误。")

            try:
                with py7zr.SevenZipFile(str(archive_path), mode="r", password=None) as archive:
                    archive.getnames()
            except py7zr.PasswordRequired:
                header_encryption_verified = True
            else:
                raise RuntimeError("无密码仍能读取归档文件名，文件头加密自检失败。")

            expected_names = {
                "smoke-test-folder",
                "smoke-test-folder/nested",
                "smoke-test-folder/nested/empty",
                "smoke-test-folder/nested/payload.txt",
            }
            with py7zr.SevenZipFile(str(archive_path), mode="r", password=password) as archive:
                names = set(name.rstrip("/") for name in archive.getnames())
                if names != expected_names:
                    raise RuntimeError(f"文件夹归档成员异常：{names!r}")
                bad_member = archive.testzip()
                if bad_member is not None:
                    raise RuntimeError(f"归档完整性自检失败：{bad_member}")

            # Reopen after testzip(): it can consume the reader's worker.
            extract_dir.mkdir()
            with py7zr.SevenZipFile(str(archive_path), mode="r", password=password) as archive:
                archive.extractall(path=extract_dir)

            extracted_payload = extract_dir / "smoke-test-folder" / "nested" / "payload.txt"
            extracted_empty = extract_dir / "smoke-test-folder" / "nested" / "empty"
            if (
                not extracted_payload.is_file()
                or extracted_payload.read_bytes() != payload.read_bytes()
                or not extracted_empty.is_dir()
                or any(extracted_empty.iterdir())
            ):
                raise RuntimeError("文件夹归档解压后与原始目录树不一致。")

        report.update(
            {
                "ok": True,
                "dependencies": versions,
                "hidden_imports": sorted(modules),
                "encrypted_header": header_encryption_verified,
                "archive_round_trip": True,
                "business_flow": True,
                "directory_archive": True,
                "empty_directory_preserved": True,
            }
        )
        exit_code = 0
    except Exception as exc:
        report.update(
            {
                "ok": False,
                "error": str(exc) or type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
        )
        logging.exception("Packaged self-test failed")
        exit_code = 1

    if report_path:
        try:
            target = Path(report_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logging.exception("Could not write packaged self-test report")
            return 1
    return exit_code

class EncryptApp:
    def __init__(self, root: tk.Tk, log_file: Path | None = None):
        self.root = root
        self.log_file = log_file
        self.is_busy = False
        self.queue_items: list[Path] = []

        root.title(f"{APP_TITLE} v{APP_VERSION}")
        root.geometry("780x520")
        root.minsize(640, 440)
        root.resizable(True, True)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self.report_callback_exception

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame, text="文件加密打包", font=("", 18, "bold")
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            frame,
            text=(
                "添加一个或多个文件，也可以多次添加文件夹。"
                "点击“开始加密”后再选择输出位置。"
            ),
            wraplength=720,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 14))

        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        self.add_files_button = ttk.Button(
            actions, text="添加文件", command=self.choose_files
        )
        self.add_files_button.pack(side="left", padx=(0, 8))

        self.add_folder_button = ttk.Button(
            actions, text="添加文件夹", command=self.choose_folder
        )
        self.add_folder_button.pack(side="left", padx=(0, 8))

        self.remove_button = ttk.Button(
            actions, text="移除选中", command=self.remove_selected
        )
        self.remove_button.pack(side="left", padx=(0, 8))

        self.clear_button = ttk.Button(
            actions, text="清空", command=self.clear_queue
        )
        self.clear_button.pack(side="left")

        ttk.Label(frame, text="待加密条目").grid(
            row=3, column=0, sticky="nw", pady=(4, 4)
        )

        queue_frame = ttk.Frame(frame)
        queue_frame.grid(row=4, column=0, sticky="nsew")
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)

        self.queue_tree = ttk.Treeview(
            queue_frame,
            columns=("kind", "path"),
            show="headings",
            selectmode="extended",
            height=10,
        )
        self.queue_tree.heading("kind", text="类型")
        self.queue_tree.heading("path", text="路径")
        self.queue_tree.column("kind", width=92, minwidth=82, stretch=False, anchor="center")
        self.queue_tree.column("path", width=560, minwidth=220, stretch=True, anchor="w")
        self.queue_tree.grid(row=0, column=0, sticky="nsew")

        vertical = ttk.Scrollbar(
            queue_frame, orient="vertical", command=self.queue_tree.yview
        )
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(
            queue_frame, orient="horizontal", command=self.queue_tree.xview
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        self.queue_tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )

        footer = ttk.Frame(frame)
        footer.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="待加密条目：0 项")
        ttk.Label(
            footer, textvariable=self.status_var, wraplength=540
        ).grid(row=0, column=0, sticky="w")

        self.start_button = ttk.Button(
            footer, text="开始加密", command=self.start_encryption
        )
        self.start_button.grid(
            row=0, column=1, sticky="e", padx=(12, 0), ipadx=12, ipady=5
        )

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=6, column=0, sticky="ew", pady=(10, 8))

        ttk.Label(
            frame,
            text=(
                "密码 TXT 须单独选择保存目录，且包含完整明文密码。"
                "请与压缩包分开安全保管；加密期间请勿强制结束程序。"
            ),
            wraplength=720,
            foreground="#555555",
            justify="left",
        ).grid(row=7, column=0, sticky="w")

        self.control_buttons = (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
            self.start_button,
        )

    def report_callback_exception(self, exc_type, exc_value, trace) -> None:
        logging.error("Tkinter 回调异常", exc_info=(exc_type, exc_value, trace))
        detail = str(exc_value) or exc_type.__name__
        messagebox.showerror("程序错误", detail, parent=self.root)

    def _refresh_queue(self) -> None:
        for item_id in self.queue_tree.get_children():
            self.queue_tree.delete(item_id)

        for index, source in enumerate(self.queue_items):
            kind = "文件夹" if source.is_dir() else "文件"
            self.queue_tree.insert(
                "", "end", iid=str(index), values=(kind, str(source))
            )

        self.status_var.set(f"待加密条目：{len(self.queue_items)} 项")

    def add_items(self, selected: list[str | Path]) -> None:
        if self.is_busy or not selected:
            return

        combined = [*self.queue_items, *selected]
        try:
            normalized = deduplicate_items(combined)
        except Exception as exc:
            messagebox.showerror(
                "无法添加条目", str(exc) or type(exc).__name__, parent=self.root
            )
            return

        removed_count = len(combined) - len(normalized)
        self.queue_items = normalized
        self._refresh_queue()
        if removed_count:
            self.status_var.set(
                f"已自动去重或移除被父文件夹包含的条目；待加密：{len(normalized)} 项"
            )

    def choose_files(self) -> None:
        if self.is_busy:
            return
        selected = filedialog.askopenfilenames(
            title="选择要加密的文件", parent=self.root
        )
        if selected:
            self.add_items(list(selected))

    def choose_folder(self) -> None:
        if self.is_busy:
            return
        selected = filedialog.askdirectory(
            title="选择要加密的文件夹",
            mustexist=True,
            parent=self.root,
        )
        if selected:
            self.add_items([selected])

    def remove_selected(self) -> None:
        if self.is_busy:
            return
        selected_ids = self.queue_tree.selection()
        if not selected_ids:
            return
        selected_indices = {int(item_id) for item_id in selected_ids}
        self.queue_items = [
            item for index, item in enumerate(self.queue_items)
            if index not in selected_indices
        ]
        self._refresh_queue()

    def clear_queue(self) -> None:
        if self.is_busy:
            return
        self.queue_items.clear()
        self._refresh_queue()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for button in self.control_buttons:
            button.state(["!disabled"] if enabled else ["disabled"])

    def start_encryption(self) -> None:
        if self.is_busy:
            return
        if not self.queue_items:
            messagebox.showwarning(
                "待加密列表为空",
                "请先点击“添加文件”或“添加文件夹”。",
                parent=self.root,
            )
            return

        output_folder = filedialog.askdirectory(
            title="选择加密文件的输出位置",
            mustexist=True,
            parent=self.root,
        )
        if not output_folder:
            self.status_var.set("已取消输出位置选择，未生成文件。")
            return

        output_path = Path(output_folder).resolve()
        for source in self.queue_items:
            if source.is_dir() and (
                output_path == source or output_path.is_relative_to(source)
            ):
                messagebox.showerror(
                    "输出位置无效",
                    "输出文件夹不能位于待加密文件夹本身或其子文件夹中。\n"
                    f"源文件夹：{source}\n"
                    "请重新选择源文件夹之外的输出位置。",
                    parent=self.root,
                )
                return

        record_file = filedialog.asksaveasfilename(
            title="单独选择明文密码 TXT 的保存位置（不可与压缩包同目录）",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
            initialdir=str(Path.home()),
            initialfile="7z-password.txt",
            parent=self.root,
        )
        if not record_file:
            self.status_var.set("已取消密码记录位置选择，未生成文件。")
            return
        record_path = Path(record_file).resolve()
        if record_path.parent == output_path:
            messagebox.showerror(
                "密码位置无效",
                "密码 TXT 不能与加密压缩包保存在同一个文件夹，请重新选择。",
                parent=self.root,
            )
            return
        if os.path.lexists(record_path):
            messagebox.showerror(
                "密码位置无效",
                "所选密码记录文件已存在。为避免覆盖，请选择新文件名。",
                parent=self.root,
            )
            return
        if not messagebox.askokcancel(
            "明文密码安全提示",
            f"即将把完整解密密码写入以下明文 TXT：\n{record_path}\n\n"
            "任何能读取该 TXT 的人都能解密压缩包。"
            "请与压缩包分开安全保管。是否继续？",
            parent=self.root,
        ):
            self.status_var.set("已取消明文密码保存，未生成文件。")
            return

        selected = list(self.queue_items)
        self.is_busy = True
        self._set_controls_enabled(False)
        self.status_var.set(f"已选择 {len(selected)} 个条目，正在准备……")
        self.progress.start(12)

        def report_status(message: str) -> None:
            try:
                self.root.after(0, self.status_var.set, message)
            except tk.TclError:
                logging.warning("窗口已关闭，无法更新处理状态")

        def worker() -> None:
            try:
                result = create_encrypted_bundle(
                    selected, str(output_path), report_status,
                    password_file=str(record_path),
                )
                self.root.after(
                    0, lambda: self.finish_success(result, len(selected))
                )
            except Exception as exc:
                detail = str(exc) or type(exc).__name__
                logging.exception("加密任务失败")
                try:
                    self.root.after(
                        0, lambda: self.finish_error(detail)
                    )
                except tk.TclError:
                    logging.exception("无法向窗口报告加密失败")

        threading.Thread(
            target=worker, daemon=False, name="archive-worker"
        ).start()

    def _finish_task(self) -> None:
        self.is_busy = False
        self.progress.stop()
        self._set_controls_enabled(True)

    def finish_success(self, result: tuple[str, str], count: int) -> None:
        self._finish_task()
        archive_path, txt_path = result
        self.status_var.set(f"完成：已处理 {count} 个条目。")
        messagebox.showinfo(
            "处理完成",
            f"加密文件已生成。\n\n压缩包：{Path(archive_path).name}\n"
            f"密码记录：{Path(txt_path).name}\n\n保存位置：{Path(archive_path).parent}",
            parent=self.root,
        )

    def finish_error(self, detail: str) -> None:
        self._finish_task()
        self.status_var.set("处理失败，原文件未被修改。")
        log_hint = f"\n\n详细日志：{self.log_file}" if self.log_file and self.log_file.is_file() else ""
        messagebox.showerror("处理失败", detail + log_hint, parent=self.root)

    def on_close(self) -> None:
        if self.is_busy:
            messagebox.showwarning(
                "正在处理",
                "文件或文件夹正在加密打包或校验完整性，请等待当前任务完成后再关闭窗口。",
                parent=self.root,
            )
            return
        self.root.destroy()

def main() -> int:
    log_file = configure_logging()

    if "--version" in sys.argv:
        print(APP_VERSION)
        return 0

    if "--self-test" in sys.argv:
        report_path: str | None = None
        if "--self-test-output" in sys.argv:
            try:
                index = sys.argv.index("--self-test-output")
                report_path = sys.argv[index + 1]
            except (ValueError, IndexError):
                return 2
        return run_packaged_self_test(report_path)

    try:
        enable_windows_dpi_awareness()
        root = tk.Tk()
        try:
            ttk.Style(root).theme_use("vista")
        except tk.TclError:
            pass
        EncryptApp(root, log_file=log_file)
        root.mainloop()
        return 0
    except Exception as exc:
        logging.exception("应用程序启动失败")
        detail = str(exc) or type(exc).__name__
        log_hint = f"\n\n详细日志：{log_file}" if log_file else ""
        try:
            messagebox.showerror("程序启动失败", detail + log_hint)
        except Exception:
            logging.exception("无法显示启动错误")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
