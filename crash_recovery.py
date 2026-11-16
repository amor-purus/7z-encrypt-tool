"""Crash-recoverable two-location publication journal (metadata only).

A single filesystem cannot atomically rename two unrelated destination files.
We therefore persist intent *before* making any staging file, keep the
password-first publication order, and reconcile interrupted transactions when
the app next starts. No plaintext password is ever written into the journal.

This protocol assumes the recovered filesystem reports completed renames and
file IDs coherently. It does not promise hardware-power-loss durability or
protection against hostile writers with access to the output directories.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import threading
from typing import Any, Iterator

_LOCAL_LOCK = threading.RLock()
_JOURNAL_VERSION = 1


def transactions_dir(app_directory: Path) -> Path:
    folder = app_directory / "transactions"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def exclusive_transaction_access(directory: Path) -> Iterator[None]:
    """Serialize recovery and publication across threads AND processes.

    Windows msvcrt.locking and POSIX flock are released by the OS if the
    process is killed. Keep the one-byte lock file for subsequent launches.
    """
    directory.mkdir(parents=True, exist_ok=True)
    with _LOCAL_LOCK:
        lock_path = directory / ".transaction.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        acquired = False
        try:
            if not os.fstat(fd).st_size:
                os.write(fd, b"\0")
                os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
            acquired = True
            yield
        finally:
            if acquired:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _file_id(path: Path) -> list[int] | None:
    st = path.stat()
    return [int(st.st_dev), int(st.st_ino)] if st.st_ino else None


def _actual_file(path: Path, identity: list[int] | None) -> str:
    """Return 'absent', 'ours' or 'unverified'; do not follow symlinks."""
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return "absent"
    if not path.is_file() or path.is_symlink() or identity is None:
        return "unverified"
    if stat.st_ino and [int(stat.st_dev), int(stat.st_ino)] == identity:
        return "ours"
    return "unverified"


def _directory_ok(path: Path, original_id: list[int] | None) -> bool:
    try:
        return path.is_dir() and (original_id is None or _file_id(path) == original_id)
    except OSError:
        return False


def begin_transaction(
    directory: Path, archive: Path, record: Path, base: str
) -> tuple[Path, dict[str, Any]]:
    """Write/fsync a complete intent record BEFORE staging is created."""
    txid = secrets.token_hex(16)
    archive_directory_id = _file_id(archive.parent)
    record_directory_id = _file_id(record.parent)
    if archive_directory_id is None or record_directory_id is None:
        raise OSError("目标文件系统不提供可靠的文件身份，无法执行安全自动恢复。")
    payload: dict[str, Any] = {
        "version": _JOURNAL_VERSION,
        "id": txid,
        "archive": str(archive),
        "record": str(record),
        "archive_directory_id": archive_directory_id,
        "record_directory_id": record_directory_id,
        "archive_prefix": f".7z-archive-{base}-{txid}-",
        "record_prefix": f".7z-password-PLAINTEXT-{base}-{txid}-",
        "archive_id": None,
        "record_id": None,
        "ready": False,
    }
    destination = directory / f".transaction-{txid}.json"
    with destination.open("x", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    _sync_directory(directory)
    return destination, payload


def mark_ready(path: Path, payload: dict[str, Any], staged_archive: Path,
               staged_record: Path) -> None:
    """Persist identities and READY before either of the final renames."""
    payload = dict(payload)
    archive_id = _file_id(staged_archive)
    record_id = _file_id(staged_record)
    if archive_id is None or record_id is None:
        raise OSError("目标文件系统不提供可靠的文件 ID，拒绝发布无法安全恢复的成品。")
    payload["archive_id"] = archive_id
    payload["record_id"] = record_id
    payload["ready"] = True
    # The record is metadata only; never includes password or source contents.
    replacement = path.with_suffix(".update")
    with replacement.open("x", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(replacement, path)
    _sync_directory(path.parent)


def _validated_journal(path: Path, payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("journal is not a JSON object")
    txid = payload.get("id")
    if (not isinstance(txid, str) or len(txid) != 32
            or any(c not in "0123456789abcdef" for c in txid)
            or path.name != f".transaction-{txid}.json"
            or payload.get("version") != _JOURNAL_VERSION):
        raise ValueError("journal ID or version is invalid")
    a = payload.get("archive")
    r = payload.get("record")
    ap = payload.get("archive_prefix")
    rp = payload.get("record_prefix")
    if (not all(isinstance(x, str) and x for x in (a, r, ap, rp))
            or not Path(a).is_absolute() or not Path(r).is_absolute()
            or txid not in ap or txid not in rp
            or not ap.startswith(".7z-archive-")
            or not rp.startswith(".7z-password-PLAINTEXT-")
            or not ap.endswith("-") or not rp.endswith("-")
            or Path(a).suffix != ".7z"
            or Path(r).suffix.lower() != ".txt"):
        raise ValueError("journal paths do not satisfy transaction naming contract")
    for key in ("archive_id", "record_id", "archive_directory_id", "record_directory_id"):
        value = payload.get(key)
        if value is not None and (
            not isinstance(value, list) or len(value) != 2
            or not all(isinstance(item, int) for item in value)
        ):
            raise ValueError(f"malformed {key}")
    return payload


def _staging_files(folder: Path, prefix: str, suffix: str) -> list[Path]:
    return list(folder.glob(prefix + "*" + suffix))


def _remove_staging(folder: Path, prefix: str, suffix: str) -> None:
    for file in _staging_files(folder, prefix, suffix):
        if file.is_symlink() or not file.is_file():
            raise OSError(f"Unexpected staging entry: {file}")
        file.unlink()
    _sync_directory(folder)


def _recover_one(path: Path, p: dict[str, Any]) -> str:
    archive = Path(p["archive"])
    record = Path(p["record"])
    if not _directory_ok(archive.parent, p["archive_directory_id"]):
        raise OSError(f"Archive directory is unavailable or changed: {archive.parent}")
    if not _directory_ok(record.parent, p["record_directory_id"]):
        raise OSError(f"Password directory is unavailable or changed: {record.parent}")

    archive_state = _actual_file(archive, p["archive_id"])
    record_state = _actual_file(record, p["record_id"])

    if archive_state == "unverified" or record_state == "unverified":
        raise OSError(f"Final file identity cannot be verified: {archive} / {record}")

    if archive_state == "ours":
        if record_state != "ours":
            raise OSError(f"Encrypted archive may have no password: {archive}; "
                          f"check the password record at {record}")
        status = "保留完整的归档及密码记录"
    else:
        # Archive is conclusively absent. Roll back only the record whose
        # inode matches the pre-publication journal (never an unrelated TXT).
        if record_state == "ours":
            record.unlink()
            _sync_directory(record.parent)
        status = "清理未完成的加密任务"

    _remove_staging(archive.parent, p["archive_prefix"], ".incomplete.7z")
    _remove_staging(record.parent, p["record_prefix"], ".incomplete.txt")
    path.unlink()
    _sync_directory(path.parent)
    return status


def recover_transactions_locked(directory: Path) -> tuple[int, list[str]]:
    """Reconcile all transactions. Caller MUST hold exclusive_transaction_access.

    Returns (recovered_count, unresolved_warnings). Ambiguous results are
    retained for human inspection and retry, never destructively guessed.
    """
    count = 0
    warnings: list[str] = []
    # A killed journal update can leave .json (old authoritative state)
    # and .update (new uncommitted state). Remove updates *first*, so
    # reconciliation cannot later strand the update after deleting .json.
    for update in directory.glob(".transaction-*.update"):
        if (directory / (update.stem + ".json")).exists():
            try:
                update.unlink()
            except OSError as exc:
                warnings.append(f"{update}: {exc}")
    for journal in sorted(directory.glob(".transaction-*.json")):
        try:
            payload = _validated_journal(
                journal, json.loads(journal.read_text(encoding="utf-8"))
            )
            _recover_one(journal, payload)
            count += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            warnings.append(f"{journal}: {exc}")
    # An update without its authoritative .json should not be guessed.
    for update in directory.glob(".transaction-*.update"):
        warnings.append(f"Orphaned update journal requiring inspection: {update}")
    return count, warnings
