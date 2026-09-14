import subprocess
import sys
from pathlib import Path

import pytest


def run_wiki(*args: str, cwd: Path | None = None, env: dict | None = None):
    return subprocess.run(
        [sys.executable, "-m", "plow_wiki.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    path = tmp_path / "wiki"
    result = run_wiki("init", str(path))
    assert result.returncode == 0, result.stderr
    return path
