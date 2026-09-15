import shutil
import subprocess
from pathlib import Path

import pytest

from plow_wiki.snapshot import history, history_dir, snapshot
from tests.conftest import run_wiki


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


def _hand_commit(wiki: Path, message: str) -> None:
    """A commit this tool's scan never saw — what a snapshot whose scan was bypassed leaves."""
    hand = ("--work-tree", str(wiki), "-c", "user.name=a", "-c", "user.email=a@plow.local")
    _git(wiki, *hand, "add", "-A", cwd=wiki)
    _git(wiki, *hand, "commit", "-q", "-m", message, cwd=wiki)


def test_first_snapshot_creates_bare_repo_beside_the_wiki(wiki):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    sha = snapshot(wiki, author="calendaring")
    assert sha.sha and history_dir(wiki).is_dir()
    assert not (wiki / ".git").exists()
    assert "calendaring" in _git(wiki, "log", "-1", "--format=%an")


def test_a_scratch_wiki_beside_the_real_one_never_snapshots_into_its_history(wiki, tmp_path):
    scratch = tmp_path / "wiki-e2e"
    assert run_wiki("init", str(scratch)).returncode == 0
    (scratch / "people" / "fixture.md").write_text("---\ntitle: Fixture\n---\n")
    snapshot(scratch, author="e2e")
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    snapshot(wiki, author="a")
    assert history_dir(wiki) == tmp_path / "wiki.git"
    touched = _git(wiki, "log", "--all", "--name-only", "--format=").split()
    assert "people/jane.md" in touched and "people/fixture.md" not in touched, touched


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


def test_env_is_never_scanned_or_committed(wiki):
    """obsidian-wiki's .env may carry an API key beside the vault path."""
    env = wiki / ".env"
    env.write_text(env.read_text() + "WIKI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz\n")
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    assert snapshot(wiki, author="a")
    assert ".env" not in _git(wiki, "log", "--all", "--name-only", "--format=")
    assert snapshot(wiki, author="a") is None, "an untracked .env is not a change to commit"


def test_history_lists_commits_touching_a_page(wiki):
    page = wiki / "people" / "jane.md"
    page.write_text("---\ntitle: Jane\n---\n- one\n")
    snapshot(wiki, author="a")
    page.write_text("---\ntitle: Jane\n---\n- two\n")
    snapshot(wiki, author="b")
    lines = history(wiki, "people/jane.md")
    assert sum(ln.endswith((" a", " b")) for ln in lines) == 2
    assert history(wiki, "people/other.md") == ["no commits touch people/other.md"]


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


def test_history_fails_loudly_when_the_history_repo_is_broken(wiki):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    snapshot(wiki, author="a")
    shutil.rmtree(history_dir(wiki) / "objects")  # the commit is referenced but unreadable
    with pytest.raises(subprocess.CalledProcessError):
        history(wiki, "people/jane.md")


def test_the_scan_reads_no_bytes_through_a_symlink_out_of_the_wiki(wiki, tmp_path):
    outside = tmp_path / "secrets.env"
    outside.write_text("token sk-abcdefghijklmnopqrstuvwxyz\n")
    (wiki / "people" / "linked.md").symlink_to(outside)
    assert snapshot(wiki, author="a"), "git stores the link target, so there is nothing to refuse"
    stored = _git(wiki, "cat-file", "-p", "HEAD:people/linked.md")
    assert "sk-abcdef" not in stored and stored == str(outside)


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
        pytest.param(
            None,
            "---\ntitle: L\n---\nguest wrote: \x00 and pasted sk-abcdefghijklmnopqrstuvwxyz\n",
            ("line 4",),
            id="a NUL-bearing page",
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


def _committed(wiki: Path, page: Path, text: str) -> None:
    page.write_text(text)
    _hand_commit(wiki, "hand")


def _merge_resolution(wiki: Path, page: Path, text: str) -> None:
    """`text` only in a hand-resolved merge, in neither parent: the commit plain `log -p` prints
    no patch for, and where a conflict fix after a rejected push lands."""
    ident = ("-c", "user.name=a", "-c", "user.email=a@plow.local")

    def tree(content: str) -> str:
        page.write_text(content)
        _git(wiki, "--work-tree", str(wiki), "add", "-A", cwd=wiki)
        return _git(wiki, "write-tree").strip()

    base = _git(wiki, "rev-parse", "HEAD").strip()
    _committed(wiki, page, "the version main had\n")
    side = _git(wiki, *ident, "commit-tree", tree("the other side's\n"), "-p", base, "-m", "side")
    merge = _git(
        wiki, *ident, "commit-tree", tree(text), "-p", "HEAD", "-p", side.strip(), "-m", "merge"
    )
    _git(wiki, "update-ref", "HEAD", merge.strip())


@pytest.mark.parametrize("plant", [_committed, _merge_resolution])
def test_first_push_refuses_a_credential_already_in_history(wiki, tmp_path, plant):
    (wiki / "people" / "jane.md").write_text("---\ntitle: Jane\n---\n")
    snapshot(wiki, author="a")

    leak = wiki / "people" / "leak.md"
    plant(wiki, leak, "---\ntitle: L\n---\n++ sk-abcdefghijklmnopqrstuvwxyz\n")
    leak.unlink()  # gone from the worktree; only history still holds it

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


@pytest.mark.parametrize(
    "rel, text",
    [
        pytest.param("Untitled.md", "a note Obsidian put at the root\n", id="a top-level file"),
        *(
            pytest.param(rel, "x\n", id=rel)
            for rel in (
                ".trash/old.md",
                ".obsidian/app.json",
                "_archived/old.md",
                "_archives/old.md",
                "_meta/taxonomy.md",
                "_readouts/narration.md",
                "attachments/photo.png",
                "_insights.md",
                ".graph-cache.json",
                ".manifest.lock",
                ".manifest.json.4821.tmp",
            )
        ),
        pytest.param(
            "people/door.md",
            "Front door code 8823. Lockbox 4471#. Wifi password: sunnyvale2024.\n",
            id="door codes are not credentials",
        ),
        pytest.param("people/nul.md", "guest wrote: \x00 and nothing else\n", id="NUL bytes"),
    ],
)
def test_snapshot_commits_what_is_neither_an_undeclared_folder_nor_a_credential(wiki, rel, text):
    (wiki / rel).parent.mkdir(exist_ok=True)
    (wiki / rel).write_text(text)
    assert snapshot(wiki, author="a")
    assert rel in _git(wiki, "ls-tree", "-r", "--name-only", "HEAD").splitlines()


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

    # (d) a quiet night that cannot reach origin fails, never reads as "nothing to snapshot"
    _git(wiki, "remote", "set-url", "origin", str(tmp_path / "unreachable.git"))
    with pytest.raises(SystemExit, match="cannot reach origin"):
        snapshot(wiki, author="a", push=True)
    _git(wiki, "remote", "set-url", "origin", str(origin))

    # (e) a credential in an outstanding commit is caught before the clean-tree catch-up push
    leak = wiki / "people" / "leak.md"
    leak.write_text("---\ntitle: L\n---\n++ sk-abcdefghijklmnopqrstuvwxyz\n")
    _hand_commit(wiki, "hand")
    leak.unlink()
    _hand_commit(wiki, "hand: gone from the worktree, still in history")
    with pytest.raises(SystemExit, match="credential"):
        snapshot(wiki, author="a", push=True)
    assert _origin_head(origin) == committed.sha
