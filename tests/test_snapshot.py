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


def _objects(wiki: Path) -> tuple[str, str]:
    """(loose objects, packs) in the bare repo — what a refused snapshot must leave untouched."""
    counts = dict(ln.split(": ") for ln in _git(wiki, "count-objects", "-v").splitlines())
    return counts["count"], counts["packs"]


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
    assert "people/leak.md (line 4)" in str(e.value) and "sk-abcdef" not in str(e.value)
    assert _git(wiki, "rev-list", "--all", "--count").strip() == "0"
    assert _objects(wiki) == ("0", "0"), "the credential never reached the object database"


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


def test_history_on_a_commitless_repo_says_so(wiki):
    (wiki / "people" / "leak.md").write_text(
        "---\ntitle: L\n---\ntoken sk-abcdefghijklmnopqrstuvwxyz\n"
    )
    with pytest.raises(SystemExit):
        snapshot(wiki, author="a")
    assert history_dir(wiki).is_dir()
    assert history(wiki, "people/leak.md") == ["no commits touch people/leak.md"]


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
    sha = snapshot(wiki, author="a", push=True).sha
    assert sha == _origin_head(origin)

    # (c) a second push carries the next commit to origin
    (wiki / "people" / "jane3.md").write_text("---\ntitle: Jane3\n---\n")
    sha2 = snapshot(wiki, author="a", push=True).sha
    assert sha2 == _origin_head(origin) != sha

    # (d) a credential added between pushes is refused; origin does not move
    (wiki / "people" / "leak.md").write_text(
        "---\ntitle: L\n---\ntoken sk-abcdefghijklmnopqrstuvwxyz\n"
    )
    with pytest.raises(SystemExit, match="credential"):
        snapshot(wiki, author="a", push=True)
    assert _origin_head(origin) == sha2


@pytest.mark.parametrize(
    "seed, page, lines",
    [
        pytest.param(
            None,
            "---\ntitle: L\n---\n\n"
            "++ note: sk-abcdefghijklmnopqrstuvwxyz\n"
            "+ token: ghp_abcdefghijklmnopqrst\n",
            ("line 5", "line 6"),
            id="lines that spell diff punctuation",
        ),
        pytest.param(
            "---\ntitle: L\n---\n-- em dash line\n",
            "---\ntitle: L\n---\n++ b/leak sk-abcdefghijklmnopqrstuvwxyz\n",
            ("line 4",),
            id="a rewrite over existing history",
        ),
    ],
)
def test_the_scan_reads_page_lines_whatever_they_spell(wiki, seed, page, lines):
    leak = wiki / "people" / "leak.md"
    if seed:
        leak.write_text(seed)
        snapshot(wiki, author="a")
    committed = _git(wiki, "rev-list", "--all", "--count").strip() if seed else "0"
    objects = _objects(wiki) if seed else ("0", "0")

    leak.write_text(page)
    with pytest.raises(SystemExit) as e:
        snapshot(wiki, author="a")
    message = str(e.value)
    assert all(f"people/leak.md ({ln})" in message for ln in lines), message
    assert "sk-abcdef" not in message and "ghp_abcdef" not in message
    assert "nothing was committed" in message
    assert _git(wiki, "rev-list", "--all", "--count").strip() == committed
    assert _objects(wiki) == objects, "the credential never reached the object database"


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
    (wiki / "people" / "leak.md").unlink()  # gone from the worktree; only history still holds it

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


def test_snapshot_commits_a_page_an_in_wiki_gitignore_would_hide(wiki):
    (wiki / "people" / ".gitignore").write_text("*.md\n")
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    assert snapshot(wiki, author="a")
    assert "people/jane.md" in _git(wiki, "ls-tree", "-r", "--name-only", "HEAD")


def test_history_finds_a_page_when_run_from_inside_the_wiki(wiki, monkeypatch):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n- one\n")
    snapshot(wiki, author="a")
    monkeypatch.chdir(wiki / "people")
    assert sum(ln.endswith(" a") for ln in history(wiki, "people/jane.md")) == 1


@pytest.mark.parametrize("name", [".trash", "_archived", ".obsidian"])
def test_housekeeping_folders_do_not_count_as_undeclared_roots(wiki, name):
    (wiki / name).mkdir()
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    assert snapshot(wiki, author="a")


def _head(wiki: Path) -> str:
    return _git(wiki, "rev-parse", "--short", "HEAD").strip()


def test_push_on_a_clean_tree_sends_the_commits_origin_does_not_have(wiki, tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    snapshot(wiki, author="a")  # the night origin was unreachable: committed, never pushed
    _git(wiki, "remote", "add", "origin", str(origin))

    # (a) origin has no main at all — a clean tree still sends every local commit
    caught_up = snapshot(wiki, author="a", push=True)
    assert caught_up == ("pushed", _head(wiki))
    assert _origin_head(origin) == caught_up.sha

    # (b) origin already has it: neither a commit nor a push
    assert snapshot(wiki, author="a", push=True) is None

    # (c) origin is behind by a commit made while it was unreachable
    (wiki / "people" / "jane2.md").write_text("---\ntitle: Jane2\n---\n")
    committed = snapshot(wiki, author="a")
    assert committed == ("snapshot", _head(wiki))
    assert snapshot(wiki, author="a", push=True) == ("pushed", committed.sha)
    assert _origin_head(origin) == committed.sha
