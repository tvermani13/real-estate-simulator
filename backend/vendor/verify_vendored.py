"""Verify the vendored platform adapter BEFORE it is installed (platform ADR 0012, decision 9).

Standard library only, so it runs before pip. It checks the wheel's SHA-256 against PROVENANCE.json and
every packaged source file against the recorded per-file hashes, and fails the build otherwise:

    python vendor/verify_vendored.py        (from backend/, or from /app in the image)
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent / "platform-context"


def main() -> int:
    record = json.loads((DIRECTORY / "PROVENANCE.json").read_text())
    wheel = DIRECTORY / record["file"]
    problems: list[str] = []
    if len(record.get("platformCommit", "")) != 40:
        problems.append("PROVENANCE.json needs the full 40-character platform commit")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != record["sha256"]:
        problems.append(f"{wheel.name}: sha256 {digest} does not match PROVENANCE.json {record['sha256']}")
    with zipfile.ZipFile(wheel) as archive:
        sources = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in sorted(archive.namelist())
                   if name.startswith("platform_context/") and name.endswith(".py")}
    if sources != record["sourceSha256"]:
        problems.append("the wheel's source files do not match the recorded per-file hashes")
    if problems:
        print("Vendored adapter check failed:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1
    print(f"Vendored platform-context {record['version']} verified (platform {record['platformCommit'][:12]}, sha256 {digest[:12]}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
