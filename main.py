# -*- coding: utf-8 -*-
"""7z 文件加密工具（Windows 11）

首次运行由启动 BAT 在本工具目录内建立独立虚拟环境并安装 py7zr / pycryptodomex。
"""
from __future__ import annotations

import os
import secrets
import string
import threading
from pathlib import Path
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
    alphabet = string.ascii_lowercase + string.digits
    for _ in range(200):
        candidate = "".join(secrets.choice(alphabet) for _ in range(ARCHIVE_NAME_LENGTH))
        if not (output_dir / f"{candidate}.7z").exists() and not (output_dir / f"{candidate}.txt").exists():
            return candidate
    raise RuntimeError("无法生成不重复的随机文件名，请更换输出文件夹。")


def make_archive_names(files: list[Path]) -> list[str]:
    """默认只保存文件名；同名文件自动补上父文件夹路径以避免冲突。"""
    raw = [p.name for p in files]
    counts: dict[str, int] = {}
    for name in raw:
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1

    result: list[str] = []
    used: set[str] = set()
    for p in files:
        name = p.name
        if counts[name.casefold()] > 1:
            current = p.parent
            segments: list[str] = []
            # 从最近的父目录开始逐层补充，排除盘符和根目录。
            while current.name:
                segments.insert(0, current.name)
                candidate = "/".join(segments + [p.name])
                if candidate.casefold() not in used:
                    name = candidate
                    break
                current = current.parent
            else:
                stem, suffix = p.stem, p.suffix
                n = 2
                while f"{stem}_{n}{suffix}".casefold() in used:
                    n += 1
                name = f"{stem}_{n}{suffix}"
        # 防止不同来源出现大小写不敏感的重复项。
        if name.casefold() in used:
            stem, suffix = Path(name).stem, Path(name).suffix
            n = 2
            while f"{stem}_{n}{suffix}".casefold() in used:
                n += 1
            name = f"{stem}_{n}{suffix}"
        used.add(name.casefold())
        result.append(name.replace("\\", "/"))
    return result


def create_encrypted_bundle(files: list[str], output_folder: str) -> tuple[str, str]:
    """创建7z和配套TXT。成功前不碰原文件，失败时清理临时产物。"""
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError(
            "缺少加密组件。请关闭工具后，双击‘启动工具.bat’，并确保电脑已连接互联网，"
            "让启动器自动安装所需组件。"
        ) from exc

    paths = [Path(item).resolve() for item in files]
    if not paths:
        raise ValueError("没有选择文件。")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"找不到文件：{path}")

    out_dir = Path(output_folder).resolve()
    if not out_dir.is_dir():
        raise NotADirectoryError("输出位置无效。")

    base = make_archive_base(out_dir)
    final_archive = out_dir / f"{base}.7z"
    final_txt = out_dir / f"{base}.txt"
    temp_archive = out_dir / f".{base}.working.7z"
    temp_txt = out_dir / f".{base}.working.txt"
    password = make_password()
    archive_names = make_archive_names(paths)

    try:
        # 7z AES-256；set_encrypted_header(True) 同时加密文件名/目录名等头部信息。
        with py7zr.SevenZipFile(str(temp_archive), mode="w", password=password) as archive:
            archive.set_encrypted_header(True)
            for source, archive_name in zip(paths, archive_names):
                archive.write(str(source), arcname=archive_name)

        if not temp_archive.exists() or temp_archive.stat().st_size == 0:
            raise RuntimeError("压缩组件没有生成有效的7z文件。")

        # 用同一密码重新打开并测试归档内容，避免只检查文件是否存在。
        with py7zr.SevenZipFile(str(temp_archive), mode="r", password=password) as check:
            names = check.getnames()
            if len(names) != len(paths):
                raise RuntimeError("压缩包内文件数量与所选文件数量不一致。")
            bad_member = check.testzip()
            if bad_member is not None:
                raise RuntimeError(f"压缩包完整性检查失败：{bad_member}")

        # TXT按用户指定字段输出；UTF-8 BOM方便Windows记事本直接阅读。
        original_names = "\n".join(f"- {p.name}" for p in paths)
        txt_content = (
            f"被加密文件名：\n{original_names}\n"
            f"加密后的文件名：{base}.7z\n"
            f"密码：{password}\n"
            f"是否已加密文件名：是\n"
        )
        with open(temp_txt, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(txt_content)

        # 两个最终文件名由高熵随机串生成；输出目录中若已出现同名文件则不覆盖。
        if final_archive.exists() or final_txt.exists():
            raise FileExistsError("输出目录中出现同名文件，请重新执行。")
        os.rename(temp_archive, final_archive)
        try:
            os.rename(temp_txt, final_txt)
        except Exception:
            try:
                final_archive.unlink(missing_ok=True)
            finally:
                raise
        return str(final_archive), str(final_txt)
    finally:
        temp_archive.unlink(missing_ok=True)
        temp_txt.unlink(missing_ok=True)


class EncryptApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("540x300")
        root.minsize(500, 280)
        root.resizable(False, False)

        frame = ttk.Frame(root, padding=26)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="文件加密打包", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="选择一个或多个文件，然后选择输出文件夹。工具会自动生成加密压缩包和密码记录。",
            wraplength=480,
            justify="left",
        ).pack(anchor="w", pady=(12, 22))

        self.choose_button = ttk.Button(frame, text="选择要加密的文件", command=self.choose_files)
        self.choose_button.pack(anchor="w", ipadx=12, ipady=7)

        self.status_var = tk.StringVar(value="尚未选择文件")
        ttk.Label(frame, textvariable=self.status_var, wraplength=480).pack(anchor="w", pady=(20, 8))

        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=480)
        self.progress.pack(anchor="w", pady=(4, 12))

        ttk.Label(
            frame,
            text="提示：密码会写入输出文件夹中的 TXT，请妥善保管，不要与压缩包一起发送给不该知道密码的人。",
            wraplength=480,
            foreground="#555555",
            justify="left",
        ).pack(anchor="w", side="bottom")

    def choose_files(self):
        selected = filedialog.askopenfilenames(title="选择要加密的文件")
        if not selected:
            return

        # 用户选择文件后立即弹出输出位置选择框。
        output_folder = filedialog.askdirectory(title="选择加密文件的输出位置", mustexist=True)
        if not output_folder:
            self.status_var.set("已取消输出位置选择，未生成文件。")
            return

        self.choose_button.state(["disabled"])
        self.status_var.set(f"已选择 {len(selected)} 个文件，正在加密处理……")
        self.progress.start(12)

        def worker():
            try:
                result = create_encrypted_bundle(list(selected), output_folder)
                self.root.after(0, lambda: self.finish_success(result, len(selected)))
            except Exception as exc:
                detail = str(exc)
                self.root.after(0, lambda: self.finish_error(detail))

        threading.Thread(target=worker, daemon=True).start()

    def finish_success(self, result: tuple[str, str], count: int):
        self.progress.stop()
        self.choose_button.state(["!disabled"])
        archive_path, txt_path = result
        self.status_var.set(f"完成：已处理 {count} 个文件。")
        messagebox.showinfo(
            "处理完成",
            f"加密文件已生成。\n\n压缩包：{Path(archive_path).name}\n密码记录：{Path(txt_path).name}\n\n保存位置：{Path(archive_path).parent}",
            parent=self.root,
        )

    def finish_error(self, detail: str):
        self.progress.stop()
        self.choose_button.state(["!disabled"])
        self.status_var.set("处理失败，原文件未被修改。")
        messagebox.showerror("处理失败", detail, parent=self.root)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    EncryptApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
