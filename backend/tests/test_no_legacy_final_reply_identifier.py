from __future__ import annotations

import subprocess
from pathlib import Path


def test_tracked_project_files_do_not_reintroduce_legacy_public_response_identifier() -> None:
    legacy_identifier = "final" + "_reply"
    repo_root = Path(__file__).resolve().parents[2]
    tracked_files = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    offenders: list[str] = []
    for relative_path in tracked_files:
        path = repo_root / relative_path
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if legacy_identifier in content:
            offenders.append(relative_path)

    assert offenders == []
