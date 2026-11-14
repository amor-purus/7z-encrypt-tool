# -*- coding: utf-8 -*-
"""7z 文件加密工具（Windows 11）。

由 start.bat 创建独立虚拟环境；只对源文件进行读取，不修改或删除源文件。
"""
from __future__ import annotations

import logging
import os
import secrets
import string
import threading
import unicodedata
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "文件加密工具"
PASSWORD_LENGTH = 32
ARCHIVE_NAME_LENGTH = 10


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

    先为唯一叶子名称预留根目录位置，再为重名文件逐层补充父目录；
    这样前面的重名文件不会抢占后面唯一文件的名称。
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
        # 不能把已经存在的文件当作目录使用。
        return any(key[:index] in used_files for index in range(1, len(key)))

    def reserve(candidate: str) -> None:
        key = _archive_key(candidate)
        if not key:
            raise ValueError(f"无效的归档文件名：{candidate!r}")
        used_files.add(key)
        for index in range(1, len(key)):
            used_dirs.add(key[:index])

    # 唯一文件名先占位，避免稍后的重名文件把它用作目录或数字后缀。
    for index, path in enumerate(files):
        if counts[leaf_keys[index]] == 1:
            candidate = path.name
            if conflicts(candidate):
                raise RuntimeError(f"唯一文件名发生意外冲突：{candidate}")
            reserve(candidate)
            result[index] = candidate

    # 重名文件从最近父目录开始逐层补充路径。
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

        # 盘符根目录没有父目录名称；把盘符作为普通首级目录保留下来。
        if candidate is None and path.drive:
            drive_label = path.drive.replace("\\", "/").strip("/").rstrip(":")
            drive_parts = [part for part in drive_label.split("/") if part]
            if drive_parts:
                trial = "/".join(drive_parts + segments + [path.name])
                if not conflicts(trial):
                    candidate = trial

        # 极端情况下父路径仍不能唯一化，使用未被预留的数字后缀。
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
    """按解析路径及文件身份去重，覆盖符号链接和硬链接等常见情况。"""
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
        raise RuntimeError(
            "缺少加密组件。请关闭工具后，双击 start.bat，并确保电脑已连接互联网，"
            "让启动器自动安装所需组件。"
        ) from exc

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
        _notify_progress(progress_callback, "正在压缩文件，请不要关闭工具……")
        # 7z AES-256；加密头部会隐藏文件名、目录名和相关头部信息。
        with py7zr.SevenZipFile(str(temp_archive), mode="w", password=password) as archive:
            archive.set_encrypted_header(True)
            for source, archive_name in zip(paths, archive_names):
                archive.write(str(source), arcname=archive_name)

        if not temp_archive.exists() or temp_archive.stat().st_size == 0:
            raise RuntimeError("压缩组件没有生成有效的 7z 文件。")

        _notify_progress(progress_callback, "正在验证密码保护和压缩包完整性……")
        # 无密码时必须无法读取归档头；否则说明文件名加密没有生效。
        try:
            with py7zr.SevenZipFile(str(temp_archive), mode="r", password=None) as no_password:
                no_password.getnames()
        except py7zr.PasswordRequired:
            pass
        else:
            raise RuntimeError("安全校验失败：压缩包文件名没有成功加密。")

        # 使用正确密码重新读取；逐项核对成员名并执行 CRC 完整性检查。
        with py7zr.SevenZipFile(str(temp_archive), mode="r", password=password) as check:
            names = check.getnames()
            if len(names) != len(archive_names) or sorted(names) != sorted(archive_names):
                raise RuntimeError("压缩包内文件列表与预期不一致。")
            bad_member = check.testzip()
            if bad_member is not None:
                raise RuntimeError(f"压缩包完整性检查失败：{bad_member}")

        # TXT 记录原始文件名与归档内路径的对应关系，便于之后找回文件。
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

        # 先发布密码记录，再发布压缩包。这样不会出现已发布的 7z 没有密码 TXT。
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
        # 清理失败不能覆盖压缩、校验或发布阶段的原始异常。
        for temporary_path in (temp_archive, temp_txt):
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logging.warning("无法清理临时文件：%s", temporary_path, exc_info=True)


class EncryptApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.is_busy = False
        root.title(APP_TITLE)
        root.geometry("580x330")
        root.minsize(520, 300)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self.report_callback_exception

        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="文件加密打包", font=("", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="选择一个或多个文件，再选择输出文件夹。工具会生成加密压缩包和密码记录。",
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(12, 20))

        self.choose_button = ttk.Button(frame, text="选择要加密的文件", command=self.choose_files)
        self.choose_button.pack(anchor="w", ipadx=12, ipady=7)

        self.status_var = tk.StringVar(value="尚未选择文件")
        ttk.Label(frame, textvariable=self.status_var, wraplength=500).pack(anchor="w", pady=(18, 8))

        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=500)
        self.progress.pack(anchor="w", pady=(4, 12), fill="x")

        ttk.Label(
            frame,
            text="密码会写入输出文件夹中的 TXT。请妥善保管，不要与压缩包一起发送给不该知道密码的人。",
            wraplength=500,
            foreground="#555555",
            justify="left",
        ).pack(anchor="w", side="bottom")

    def report_callback_exception(self, exc_type, exc_value, traceback) -> None:
        logging.error(
            "Tkinter 回调异常",
            exc_info=(exc_type, exc_value, traceback),
        )
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

        # 非守护线程避免 GUI 的主循环异常退出时悄悄中断文件处理。
        threading.Thread(target=worker, daemon=False).start()

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
        messagebox.showerror("处理失败", detail, parent=self.root)

    def on_close(self) -> None:
        if self.is_busy:
            messagebox.showwarning(
                "正在处理",
                "文件正在压缩或校验，请等待当前任务完成后再关闭窗口。",
                parent=self.root,
            )
            return
        self.root.destroy()


def main() -> None:
    try:
        root = tk.Tk()
        try:
            ttk.Style(root).theme_use("vista")
        except tk.TclError:
            pass
        EncryptApp(root)
        root.mainloop()
    except Exception as exc:
        logging.exception("应用程序启动失败")
        detail = str(exc) or type(exc).__name__
        try:
            messagebox.showerror("程序启动失败", detail)
        except Exception:
            logging.exception("无法显示启动错误")


if __name__ == "__main__":
    main()
