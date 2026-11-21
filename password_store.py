"""Optional account-bound Windows DPAPI password record protection.

The outer filename stays .txt for compatibility with the existing crash journal.
A DPAPI-protected record is ciphertext, not a plaintext TXT.
Protection is bound to the current Windows user account, not portable across PCs.
Malware under the same identity could decrypt it. Export explicitly for recovery.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os

MAGIC = b"7Z-ENCRYPT-TOOL-DPAPI-V1\n"
_FLAGS = 0x1  # CRYPTPROTECT_UI_FORBIDDEN


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    backing = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return _Blob(len(data), ctypes.cast(backing, ctypes.POINTER(ctypes.c_ubyte))), backing


def _dpapi(data: bytes, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise OSError("Windows DPAPI 仅适用于 Windows。")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    param = ctypes.POINTER(_Blob)
    if decrypt:
        call = crypt32.CryptUnprotectData
        call.argtypes = [param, ctypes.c_void_p, param, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, param]
    else:
        call = crypt32.CryptProtectData
        call.argtypes = [param, wintypes.LPCWSTR, param, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, param]
    call.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    input_blob, backing = _blob(data)
    result = _Blob()
    try:
        if decrypt:
            ok = call(ctypes.byref(input_blob), None, None, None, None,
                      _FLAGS, ctypes.byref(result))
        else:
            ok = call(ctypes.byref(input_blob), "7z Encrypt Tool Recovery Record",
                      None, None, None, _FLAGS, ctypes.byref(result))
        if not ok:
            raise OSError(ctypes.get_last_error(), "Windows DPAPI 操作失败")
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        if result.pbData:
            kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def encode_record(content: str, mode: str) -> bytes:
    if mode == "plaintext":
        return content.encode("utf-8-sig")
    if mode == "dpapi":
        return MAGIC + base64.b64encode(_dpapi(content.encode("utf-8"), False)) + b"\n"
    raise ValueError("未知密码记录格式")


def decode_record(data: bytes) -> str:
    if not data.startswith(MAGIC):
        raise ValueError("这不是本工具的 DPAPI 保护密码记录。")
    try:
        blob = base64.b64decode(data[len(MAGIC):].strip(), validate=True)
        if not blob:
            raise ValueError("密码记录为空")
        return _dpapi(blob, True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("密码记录格式无效或内容损坏") from exc


def export_plaintext(source_file: str, destination_file: str) -> None:
    """Exports only at an explicit user request, creating the destination exclusively."""
    with open(source_file, "rb") as source:
        data = source.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("密码记录异常过大，拒绝操作。")
    plaintext = decode_record(data)
    with open(destination_file, "xb") as destination:
        destination.write(plaintext.encode("utf-8-sig"))
        destination.flush()
        os.fsync(destination.fileno())
