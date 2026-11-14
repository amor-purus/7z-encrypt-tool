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
APP_VERSION = "1.1.0"
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
        logging.basicConfig(
            level=logging.ERROR,
            format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
            force=True,
        )
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


def make_archive_names(files: list[Path]) -> list[str]:
    """生成相互不冲突的归档路径，并优先保留所有唯一的原始文件名。

    唯一叶子名称先占位；重名文件再逐层补充父目录，最后才使用数字后缀。
    """
    if not files:
        return []

    leaf_keys = [_archive_key(path.name) for path in files]
    counts: dict[tuple[str, ...], int] = {}
    for key in leaf_keys:
        counts[key] = counts.get(key, 0) + 1

    used_files: set[tuple[str, ...]] = set()
    used_dirs: set[tuple[str, ...]] = set()
    result: list[str | None] = [None] * len(files)

    def conflicts(candidate: str) -> bool:
        key = _archive_key(candidate)
        if not key or key in used_files or key in used_dirs:
            return True
        return any(key[:index] in used_files for index in range(1, len(key)))

    def reserve(candidate: str) -> None:
        key = _archive_key(candidate)
        if not key:
            raise ValueError(f"无效的归档文件名：{candidate!r}")
        used_files.add(key)
        for index in range(1, len(key)):
            used_dirs.add(key[:index])

    # 先保护所有唯一叶子名称，避免后续重复项抢占它们。
    for index, path in enumerate(files):
        if counts[leaf_keys[index]] == 1:
            candidate = path.name
            if conflicts(candidate):
                raise RuntimeError(f"唯一文件名发生意外冲突：{candidate}")
            reserve(candidate)
            result[index] = candidate

    for index, path in enumerate(files):
        if result[index] is not None:
            continue

        segments: list[str] = []
        current = path.parent
        candidate: str | None = None
        while current.name:
            segments.insert(0, current.name)
            trial = "/".join(segments + [path.name])
            if not conflicts(trial):
                candidate = trial
                break
            current = current.parent

        # 路径退到盘符根目录时，保留盘符以区分不同卷。
        if candidate is None and path.drive:
            drive_label = path.drive.replace("\\", "/").strip("/").rstrip(":")
            drive_parts = [part for part in drive_label.split("/") if part]
            if drive_parts:
                trial = "/".join(drive_parts + segments + [path.name])
                if not conflicts(trial):
                    candidate = trial

        if candidate is None:
            stem, suffix = path.stem, path.suffix
            number = 2
            while True:
                trial = f"{stem}_{number}{suffix}"
                if not conflicts(trial):
                    candidate = trial
                    break
                number += 1

        reserve(candidate)
        result[index] = candidate

    return [name.replace("\\", "/") for name in result if name is not None]


def deduplicate_files(items: list[str | Path]) -> list[Path]:
    """按解析路径及文件身份去重，覆盖符号链接和可识别的硬链接。"""
    paths: list[Path] = []
    seen_paths: set[str] = set()
    seen_file_ids: set[tuple[int, int]] = set()

    for item in items:
        path = Path(item).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"找不到文件：{path}")

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
        paths.append(path)

    return paths


def _notify_progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        try:
            callback(message)
        except Exception:
            logging.exception("进度通知失败")


def create_encrypted_bundle(
    files: list[str],
    output_folder: str,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[str, str]:
    """创建加密 7z 和配套 TXT；成功前不碰原文件，失败时清理临时产物。"""
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError("加密组件缺失，请重新下载完整的官方 EXE 版本。") from exc

    paths = deduplicate_files(files)
    if not paths:
        raise ValueError("没有选择文件。")

    out_dir = Path(output_folder).resolve()
    if not out_dir.is_dir():
        raise NotADirectoryError("输出位置无效。")

    archive_names = make_archive_names(paths)
    base = make_archive_base(out_dir)
    final_archive = out_dir / f"{base}.7z"
    final_txt = out_dir / f"{base}.txt"
    temp_archive = out_dir / f".{base}.working.7z"
    temp_txt = out_dir / f".{base}.working.txt"
    password = make_password()

    try:
        _notify_progress(progress_callback, "正在加密打包，请不要关闭工具……")
        with py7zr.SevenZipFile(str(temp_archive), mode="w", password=password) as archive:
            archive.set_encrypted_header(True)
            for source, archive_name in zip(paths, archive_names):
                archive.write(str(source), arcname=archive_name)

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
            if len(names) != len(archive_names) or sorted(names) != sorted(archive_names):
                raise RuntimeError("压缩包内文件列表与预期不一致。")
            bad_member = check.testzip()
            if bad_member is not None:
                raise RuntimeError(f"压缩包完整性检查失败：{bad_member}")

        mappings = "\n".join(
            f"- {source.name} -> {archive_name}"
            for source, archive_name in zip(paths, archive_names)
        )
        txt_content = (
            f"被加密文件名及归档内路径：\n{mappings}\n"
            f"加密后的文件名：{base}.7z\n"
            f"密码：{password}\n"
            f"是否已加密文件名：是\n"
        )
        with open(temp_txt, "w", encoding="utf-8-sig", newline="\r\n") as stream:
            stream.write(txt_content)
            stream.flush()
            os.fsync(stream.fileno())

        if final_archive.exists() or final_txt.exists():
            raise FileExistsError("输出目录中出现同名文件，请重新执行。")

        # 先发布 TXT，再发布 7z；失败时回滚 TXT，避免孤立的正式加密包。
        os.rename(temp_txt, final_txt)
        try:
            os.rename(temp_archive, final_archive)
        except BaseException:
            try:
                final_txt.unlink(missing_ok=True)
            except OSError:
                logging.exception("压缩包发布失败后，无法回滚密码记录：%s", final_txt)
            raise

        return str(final_archive), str(final_txt)
    finally:
        for temporary_path in (temp_archive, temp_txt):
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logging.warning("无法清理临时文件：%s", temporary_path, exc_info=True)


def run_packaged_self_test(report_path: str | None = None) -> int:
    """由 CI 直接运行打包后的 EXE，检查隐藏导入、元数据和真实加密往返。"""
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
            source = root / "smoke-test.txt"
            archive_path = root / "smoke-test.7z"
            extract_dir = root / "extracted"
            source.write_bytes(b"7z encryption tool packaged self-test\n")
            password = "SelfTest-" + secrets.token_urlsafe(24)

            with py7zr.SevenZipFile(str(archive_path), mode="w", password=password) as archive:
                archive.set_encrypted_header(True)
                archive.write(str(source), arcname="smoke-test/smoke-test.txt")

            try:
                with py7zr.SevenZipFile(str(archive_path), mode="r", password=None) as archive:
                    archive.getnames()
            except py7zr.PasswordRequired:
                header_encryption_verified = True
            else:
                raise RuntimeError("无密码仍能读取归档文件名，文件头加密自检失败。")

            with py7zr.SevenZipFile(str(archive_path), mode="r", password=password) as archive:
                names = archive.getnames()
                if names != ["smoke-test/smoke-test.txt"]:
                    raise RuntimeError(f"归档成员名称异常：{names!r}")
                bad_member = archive.testzip()
                if bad_member is not None:
                    raise RuntimeError(f"归档完整性自检失败：{bad_member}")
                extract_dir.mkdir()
                archive.extractall(path=extract_dir)

            extracted = extract_dir / "smoke-test" / "smoke-test.txt"
            if not extracted.is_file() or extracted.read_bytes() != source.read_bytes():
                raise RuntimeError("加密归档解压后的内容与原文件不一致。")

        report.update(
            {
                "ok": True,
                "dependencies": versions,
                "hidden_imports": sorted(modules),
                "encrypted_header": header_encryption_verified,
                "archive_round_trip": True,
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
    def __init__(self, root: tk.Tk):
        self.root = root
        self.is_busy = False
        root.title(f"{APP_TITLE} v{APP_VERSION}")
        root.geometry("600x360")
        root.minsize(540, 320)
        root.resizable(True, True)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self.report_callback_exception

        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="文件加密打包", font=("", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="选择一个或多个文件，再选择输出文件夹。工具会生成加密压缩包和密码记录。",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(12, 20))

        self.choose_button = ttk.Button(frame, text="选择要加密的文件", command=self.choose_files)
        self.choose_button.pack(anchor="w", ipadx=12, ipady=7)

        self.status_var = tk.StringVar(value="尚未选择文件")
        ttk.Label(frame, textvariable=self.status_var, wraplength=520).pack(anchor="w", pady=(18, 8))

        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=520)
        self.progress.pack(anchor="w", pady=(4, 12), fill="x")

        ttk.Label(
            frame,
            text="密码会写入输出文件夹中的 TXT。请妥善保管，不要与压缩包一起发送给不该知道密码的人。",
            wraplength=520,
            foreground="#555555",
            justify="left",
        ).pack(anchor="w", side="bottom")

    def report_callback_exception(self, exc_type, exc_value, trace) -> None:
        logging.error("Tkinter 回调异常", exc_info=(exc_type, exc_value, trace))
        detail = str(exc_value) or exc_type.__name__
        messagebox.showerror("程序错误", detail, parent=self.root)

    def choose_files(self) -> None:
        if self.is_busy:
            return

        selected = filedialog.askopenfilenames(title="选择要加密的文件", parent=self.root)
        if not selected:
            return

        output_folder = filedialog.askdirectory(
            title="选择加密文件的输出位置",
            mustexist=True,
            parent=self.root,
        )
        if not output_folder:
            self.status_var.set("已取消输出位置选择，未生成文件。")
            return

        self.is_busy = True
        self.choose_button.state(["disabled"])
        self.status_var.set(f"已选择 {len(selected)} 个文件，正在准备……")
        self.progress.start(12)

        def report_status(message: str) -> None:
            try:
                self.root.after(0, self.status_var.set, message)
            except tk.TclError:
                logging.warning("窗口已关闭，无法更新处理状态")

        def worker() -> None:
            try:
                result = create_encrypted_bundle(list(selected), output_folder, report_status)
                self.root.after(0, lambda: self.finish_success(result, len(selected)))
            except Exception as exc:
                detail = str(exc) or type(exc).__name__
                logging.exception("加密任务失败")
                try:
                    self.root.after(0, lambda detail=detail: self.finish_error(detail))
                except tk.TclError:
                    logging.exception("无法向窗口报告加密失败")

        threading.Thread(target=worker, daemon=False, name="archive-worker").start()

    def _finish_task(self) -> None:
        self.is_busy = False
        self.progress.stop()
        self.choose_button.state(["!disabled"])

    def finish_success(self, result: tuple[str, str], count: int) -> None:
        self._finish_task()
        archive_path, txt_path = result
        self.status_var.set(f"完成：已处理 {count} 个文件。")
        messagebox.showinfo(
            "处理完成",
            f"加密文件已生成。\n\n压缩包：{Path(archive_path).name}\n"
            f"密码记录：{Path(txt_path).name}\n\n保存位置：{Path(archive_path).parent}",
            parent=self.root,
        )

    def finish_error(self, detail: str) -> None:
        self._finish_task()
        self.status_var.set("处理失败，原文件未被修改。")
        log_hint = f"\n\n详细日志：{app_data_dir() / 'logs' / 'application.log'}"
        messagebox.showerror("处理失败", detail + log_hint, parent=self.root)

    def on_close(self) -> None:
        if self.is_busy:
            messagebox.showwarning(
                "正在处理",
                "文件正在加密打包或校验完整性，请等待当前任务完成后再关闭窗口。",
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
        EncryptApp(root)
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
