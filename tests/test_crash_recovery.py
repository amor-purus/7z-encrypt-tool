"""Real process-kill recovery regressions using the actual encrypted bundle writer.

The child executes os._exit() at deterministic publication boundaries; no
Python finally block or ordinary exception cleanup can run. Recovery is
performed by an independent Python process, just like a fresh app launch.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import py7zr

import main
from test_workflow_integration import password_from_record


CHILD_SCRIPT = r"""
import os, sys
from pathlib import Path
import main

source, output, record, phase = map(str, sys.argv[1:])
if phase == "after_staged_password":
    original = main._verify_inventory_unchanged
    calls = [0]
    def interrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        calls[0] += 1
        if calls[0] == 2:
            os._exit(81)
        return result
    main._verify_inventory_unchanged = interrupted
elif phase in ("after_published_password", "after_published_archive"):
    original = main._publish_without_overwrite
    def interrupted(src, destination):
        original(src, destination)
        if phase == "after_published_password" and Path(destination) == Path(record):
            os._exit(82)
        if phase == "after_published_archive" and Path(destination).suffix == ".7z":
            os._exit(83)
    main._publish_without_overwrite = interrupted
else:
    raise ValueError(phase)

main.create_encrypted_bundle([source], output, password_file=record)
raise RuntimeError("The hard-kill hook did not fire")
"""


class CrashRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="7z-hardkill-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.localappdata = self.root / "localappdata"
        self.localappdata.mkdir()
        self.output = self.root / "encrypted"
        self.passwords = self.root / "passwords"
        self.output.mkdir()
        self.passwords.mkdir()
        self.source = self.root / "input.txt"
        self.source.write_bytes(b"source must remain unchanged")
        self.record = self.passwords / "recovery-key.txt"
        self.journals = self.localappdata / "7z-Encrypt-Tool" / "transactions"
        self.env = dict(os.environ)
        self.env["LOCALAPPDATA"] = str(self.localappdata)
        self.env["PYTHONUTF8"] = "1"
        self.cwd = str(Path(main.__file__).resolve().parent)

    def _run(self, script, *args, timeout=90):
        return subprocess.run(
            [sys.executable, "-B", "-c", script, *(str(arg) for arg in args)],
            cwd=self.cwd, env=self.env, capture_output=True, text=True,
            timeout=timeout, check=False,
        )

    def _crash(self, phase, code):
        result = self._run(
            CHILD_SCRIPT, self.source, self.output, self.record, phase
        )
        self.assertEqual(
            result.returncode, code,
            f"{phase} did not terminate at the requested boundary:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
        self.assertEqual(self.source.read_bytes(), b"source must remain unchanged")
        self.assertEqual(
            len(list(self.journals.glob(".transaction-*.json"))), 1,
            "A durable intent journal must already exist when the process dies",
        )

    def _restart_and_recover(self):
        result = self._run(
            "import json, main; print(json.dumps(main.recover_interrupted_transactions()))",
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        recovered, problems = json.loads(result.stdout.strip())
        self.assertEqual(problems, [])
        self.assertGreaterEqual(recovered, 1)
        self.assertEqual(list(self.journals.glob(".transaction-*.json")), [])
        self.assertEqual(list(self.journals.glob(".transaction-*.update")), [])
        self.assertEqual(list(self.output.glob("*.incomplete.7z")), [])
        self.assertEqual(list(self.passwords.glob("*.incomplete.txt")), [])

    def test_kill_after_password_staging_discards_both_incomplete_files(self):
        self._crash("after_staged_password", 81)
        self.assertGreaterEqual(len(list(self.output.glob("*.incomplete.7z"))), 1)
        self.assertGreaterEqual(len(list(self.passwords.glob("*.incomplete.txt"))), 1)
        self.assertFalse(self.record.exists())
        self._restart_and_recover()
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.passwords.iterdir()), [])

    def test_kill_after_password_publication_rolls_back_orphan_password(self):
        self._crash("after_published_password", 82)
        self.assertTrue(self.record.exists())
        self.assertEqual(list(self.output.glob("[!.]*.7z")), [])
        self._restart_and_recover()
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.passwords.iterdir()), [])

    def test_kill_after_archive_publication_preserves_both_complete_outputs(self):
        self._crash("after_published_archive", 83)
        archives = list(self.output.glob("[!.]*.7z"))
        self.assertEqual(len(archives), 1)
        self.assertTrue(self.record.exists())
        self._restart_and_recover()
        self.assertTrue(self.record.exists())
        self.assertEqual(list(self.output.iterdir()), archives)
        password = password_from_record(self.record)
        with py7zr.SevenZipFile(archives[0], mode="r", password=password) as reader:
            self.assertEqual(reader.getnames(), ["input.txt"])
            self.assertIsNone(reader.testzip())
        with py7zr.SevenZipFile(archives[0], mode="r", password=password) as reader:
            reader.extractall(path=self.root / "unpacked")
        self.assertEqual(
            (self.root / "unpacked" / "input.txt").read_bytes(),
            self.source.read_bytes(),
        )

    def test_untrusted_replacement_password_is_never_deleted(self):
        self._crash("after_published_password", 82)
        password = password_from_record(self.record)
        self.assertNotIn(
            password,
            next(self.journals.glob(".transaction-*.json")).read_text(encoding="utf-8"),
            "The crash-recovery journal must never store plaintext keys",
        )
        moved = self.passwords / "moved-original.txt"
        self.record.rename(moved)
        self.record.write_text("unrelated owner data", encoding="utf-8")
        result = self._run(
            "import json, main; print(json.dumps(main.recover_interrupted_transactions()))"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        recovered, problems = json.loads(result.stdout.strip())
        self.assertEqual(recovered, 0)
        self.assertTrue(problems, "Refuse destructive recovery if the TXT identity changed")
        self.assertEqual(self.record.read_text(encoding="utf-8"), "unrelated owner data")
        self.assertEqual(password_from_record(moved), password)
        self.assertEqual(len(list(self.journals.glob(".transaction-*.json"))), 1)

    def test_unmounted_archive_directory_never_destroys_password(self):
        self._crash("after_published_password", 82)
        temporarily_unavailable = self.root / "encrypted-unmounted"
        self.output.rename(temporarily_unavailable)
        result = self._run(
            "import json, main; print(json.dumps(main.recover_interrupted_transactions()))"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        recovered, problems = json.loads(result.stdout.strip())
        self.assertEqual(recovered, 0)
        self.assertTrue(problems)
        self.assertTrue(self.record.exists(), "Never delete the only password while destination volume is unavailable")
        temporarily_unavailable.rename(self.output)
        self._restart_and_recover()
        self.assertFalse(self.record.exists())


if __name__ == "__main__":
    unittest.main()
