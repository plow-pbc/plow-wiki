import subprocess
from pathlib import Path

import pytest

from plow_wiki.snapshot import history, history_dir, snapshot


def _git(wiki: Path, *args):
    return subprocess.run(
        ["git", "--git-dir", str(history_dir(wiki)), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_first_snapshot_creates_bare_repo_beside_the_wiki(wiki):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    sha = snapshot(wiki, author="calendaring")
    assert sha and history_dir(wiki).is_dir()
    assert not (wiki / ".git").exists()
    assert "calendaring" in _git(wiki, "log", "-1", "--format=%an")


def test_second_identical_snapshot_is_a_noop(wiki):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    snapshot(wiki, author="a")
    assert snapshot(wiki, author="a") is None


def test_snapshot_refuses_a_credential_and_commits_nothing(wiki, capsys):
    (wiki / "people" / "leak.md").write_text(
        "---\ntitle: L\n---\ntoken sk-abcdefghijklmnopqrstuvwxyz\n"
    )
    with pytest.raises(SystemExit) as e:
        snapshot(wiki, author="a")
    assert "people/leak.md" in str(e.value) and "sk-abcdef" not in str(e.value)
    assert _git(wiki, "rev-list", "--all", "--count").strip() == "0"


def test_snapshot_refuses_git_inside_and_undeclared_roots(wiki):
    (wiki / "stray").mkdir()
    with pytest.raises(SystemExit, match="undeclared top-level"):
        snapshot(wiki, author="a")
    (wiki / "stray").rmdir()
    (wiki / ".git").mkdir()
    with pytest.raises(SystemExit, match="must not be a git repo"):
        snapshot(wiki, author="a")


def test_history_lists_commits_touching_a_page(wiki):
    page = wiki / "people" / "jane.md"
    page.write_text("---\ntitle: Jane\n---\n- one\n")
    snapshot(wiki, author="a")
    page.write_text("---\ntitle: Jane\n---\n- two\n")
    snapshot(wiki, author="b")
    lines = history(wiki, "people/jane.md")
    assert sum(ln.endswith((" a", " b")) for ln in lines) == 2


def test_history_without_repo_fails_loudly(wiki):
    with pytest.raises(SystemExit, match="no history repo yet"):
        history(wiki, "people/jane.md")
