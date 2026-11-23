"""The vendored platform adapter is exactly what its provenance record says (platform ADR 0012, decision 9)."""

from __future__ import annotations

import hashlib
import json
import unittest
import zipfile
from pathlib import Path

import platform_context

BACKEND = Path(__file__).resolve().parents[1]
DIRECTORY = BACKEND / "vendor" / "platform-context"


class VendoredAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provenance = json.loads((DIRECTORY / "PROVENANCE.json").read_text())

    def test_the_record_names_a_full_platform_commit_and_the_wheel_matches_its_hash(self) -> None:
        self.assertRegex(self.provenance["platformCommit"], r"^[0-9a-f]{40}$")
        wheel = DIRECTORY / self.provenance["file"]
        self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), self.provenance["sha256"])

    def test_every_source_file_in_the_wheel_matches_the_recorded_hash(self) -> None:
        wheel = zipfile.ZipFile(DIRECTORY / self.provenance["file"])
        sources = {n: hashlib.sha256(wheel.read(n)).hexdigest() for n in wheel.namelist()
                   if n.startswith("platform_context/") and n.endswith(".py")}
        self.assertEqual(sources, self.provenance["sourceSha256"])

    def test_the_installed_adapter_is_the_vendored_one(self) -> None:
        installed = Path(platform_context.__file__).parent
        for name, digest in self.provenance["sourceSha256"].items():
            path = installed / Path(name).name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, name)

    def test_the_vendored_adapter_carries_the_hardening_this_app_relies_on(self) -> None:
        # The application depends on a replay cache that refuses at capacity and a loopback-literal key set.
        self.assertTrue(hasattr(platform_context, "ReplayCacheFull"))
        from platform_context.fastapi import PlatformContextDenied, install_exception_handler  # noqa: F401
        from platform_context.verifier import _require_loopback_url
        for url in ("http://localhost:9190/k", "https://evil.test/k", "http://user:pw@127.0.0.1/k"):
            with self.assertRaises(Exception, msg=url):
                _require_loopback_url(url)
        _require_loopback_url("http://127.0.0.1:9190/k")

    def test_the_pre_install_check_passes_and_catches_a_changed_wheel(self) -> None:
        import subprocess, sys, tempfile, shutil
        script = BACKEND / "vendor" / "verify_vendored.py"
        self.assertEqual(subprocess.run([sys.executable, str(script)], capture_output=True).returncode, 0)
        with tempfile.TemporaryDirectory() as copy:
            shutil.copytree(BACKEND / "vendor", Path(copy) / "vendor")
            wheel = Path(copy) / "vendor" / "platform-context" / self.provenance["file"]
            wheel.write_bytes(wheel.read_bytes() + b"tampered")
            result = subprocess.run([sys.executable, str(Path(copy) / "vendor" / "verify_vendored.py")], capture_output=True)
            self.assertEqual(result.returncode, 1)

    def test_the_lock_and_the_requirements_install_the_vendored_wheel_by_path(self) -> None:
        line = f"./vendor/platform-context/{self.provenance['file']}"
        for name in ("requirements.lock", "requirements.txt"):
            self.assertIn(line, (BACKEND / name).read_text().splitlines(), name)


if __name__ == "__main__":
    unittest.main()
