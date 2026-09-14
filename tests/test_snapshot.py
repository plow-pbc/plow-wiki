import subprocess
from pathlib import Path

import pytest

from plow_wiki.snapshot import history, history_dir, snapshot


def _git(wiki: Path, *args, cwd: Path | None = None):
    return subprocess.run(
        ["git", "--git-dir", str(history_dir(wiki)), *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
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


def test_snapshot_refuses_a_credential_and_commits_nothing(wiki):
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


def test_history_on_a_commitless_repo_is_empty(wiki):
    (wiki / "people" / "leak.md").write_text(
        "---\ntitle: L\n---\ntoken sk-abcdefghijklmnopqrstuvwxyz\n"
    )
    with pytest.raises(SystemExit):
        snapshot(wiki, author="a")
    assert history_dir(wiki).is_dir()
    assert history(wiki, "people/leak.md") == []


def _origin_head(origin: Path) -> str:
    return subprocess.run(
        ["git", "--git-dir", str(origin), "rev-parse", "--short", "main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_push_requires_origin_then_scans_and_syncs_incrementally(wiki, tmp_path):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    snapshot(wiki, author="a")  # local history exists; no origin configured yet
    before = _git(wiki, "rev-list", "--all", "--count").strip()

    # (a) push with no origin at all refuses before doing any work
    (wiki / "people" / "jane2.md").write_text("---\ntitle: Jane2\n---\n")
    with pytest.raises(SystemExit, match="origin"):
        snapshot(wiki, author="a", push=True)
    assert _git(wiki, "rev-list", "--all", "--count").strip() == before

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _git(wiki, "remote", "add", "origin", str(origin))

    # (b) first push to an empty origin lands the local HEAD on origin's main
    sha = snapshot(wiki, author="a", push=True)
    assert sha == _origin_head(origin)

    # (c) a second push carries the next commit to origin
    (wiki / "people" / "jane3.md").write_text("---\ntitle: Jane3\n---\n")
    sha2 = snapshot(wiki, author="a", push=True)
    assert sha2 == _origin_head(origin) != sha

    # (d) a credential added between pushes is refused; origin does not move
    (wiki / "people" / "leak.md").write_text(
        "---\ntitle: L\n---\ntoken sk-abcdefghijklmnopqrstuvwxyz\n"
    )
    with pytest.raises(SystemExit, match="credential"):
        snapshot(wiki, author="a", push=True)
    assert _origin_head(origin) == sha2


def test_scan_catches_credentials_on_content_lines_that_start_with_plus(wiki):
    (wiki / "people" / "leak.md").write_text(
        "---\ntitle: L\n---\n\n"
        "++ note: sk-abcdefghijklmnopqrstuvwxyz\n"
        "+ token: ghp_abcdefghijklmnopqrst\n"
    )
    with pytest.raises(SystemExit) as e:
        snapshot(wiki, author="a")
    message = str(e.value)
    assert "people/leak.md (line 5)" in message and "people/leak.md (line 6)" in message
    assert "sk-abcdef" not in message and "ghp_abcdef" not in message
    assert "nothing was committed" in message
    assert _git(wiki, "rev-list", "--all", "--count").strip() == "0"


def test_first_push_refuses_a_credential_already_in_history(wiki, tmp_path):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    snapshot(wiki, author="a")

    # A credential committed by hand, the way a snapshot whose scan was bypassed would leave it.
    (wiki / "people" / "leak.md").write_text(
        "---\ntitle: L\n---\n++ sk-abcdefghijklmnopqrstuvwxyz\n"
    )
    hand = ("--work-tree", str(wiki), "-c", "user.name=a", "-c", "user.email=a@plow.local")
    _git(wiki, *hand, "add", "-A", cwd=wiki)
    _git(wiki, *hand, "commit", "-q", "-m", "hand", cwd=wiki)

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _git(wiki, "remote", "add", "origin", str(origin))

    (wiki / "people" / "jane2.md").write_text("---\ntitle: Jane2\n---\n")
    with pytest.raises(SystemExit) as e:
        snapshot(wiki, author="a", push=True)
    assert "people/leak.md (line 4)" in str(e.value)
    assert "sk-abcdef" not in str(e.value)
    assert (
        subprocess.run(
            ["git", "--git-dir", str(origin), "rev-parse", "--verify", "main"],
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        != 0
    ), "origin must not receive the credential"
