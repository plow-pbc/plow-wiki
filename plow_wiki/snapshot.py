"""History for a wiki that must not be a git repo: a bare repo beside it, written only here."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from plow_wiki import paths

CREDENTIAL = re.compile(
    r"sk-[A-Za-z0-9_-]{16}|gh[pousr]_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{20}"
    r"|xox[abpr]-[A-Za-z0-9-]{10}|(?:AKIA|ASIA)[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|eyJ[A-Za-z0-9_-]{20,}\."
)
# The scan reads `b/<path>` out of diff headers, so no gitconfig may reshape them.
_DIFF = (
    "-c",
    "diff.noprefix=false",
    "-c",
    "diff.mnemonicPrefix=false",
    "-c",
    "diff.srcPrefix=a/",
    "-c",
    "diff.dstPrefix=b/",
)
_HUNK = re.compile(r"^(@{2,}) (?:-\d+(?:,\d+)? )+\+(\d+)(?:,\d+)? @")  # @@, and a merge's @@@
# Top-level folders that are not roots: what a page walk skips, less `.git` (refused outright),
# plus Obsidian's trash and obsidian-wiki's attachments.
HOUSEKEEPING = (paths.SKIP_DIRS | {".trash", "attachments"}) - {".git"}
# obsidian-wiki's vault config, which may carry API keys: never scanned, staged or committed.
ENV = ".env"
# Every page but ENV, shared by `add` and `status` so an untracked .env is never a change.
_PAGES = ("--", ".", f":(exclude){ENV}")


class Snapshot(NamedTuple):
    action: str  # "snapshot" when it committed, "pushed" when it only sent what was already local
    sha: str


def history_dir(wiki: Path) -> Path:
    """Named for the wiki, so a scratch copy beside it (`wiki-e2e`) never shares its history."""
    return wiki.parent / f"{wiki.name}.git"


def _git(wiki: Path, *args: str, check: bool = True, **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "--git-dir", str(history_dir(wiki)), "--work-tree", str(wiki), *_DIFF, *args],
        capture_output=True,
        text=True,
        check=check,
        cwd=wiki,  # git reads pathspecs relative to cwd, not the work tree
        env={**os.environ, **env},
    )


def _ensure_repo(wiki: Path) -> None:
    if history_dir(wiki).is_dir():
        return
    subprocess.run(["git", "init", "-q", "--bare", str(history_dir(wiki))], check=True)
    _git(wiki, "symbolic-ref", "HEAD", "refs/heads/main")


def _refuse_undeclared_roots(wiki: Path) -> None:
    """Folders only: Obsidian's New note lands a file at the root, and a file is just committed."""
    allowed = {root.split("/")[0] for root in paths.load_roots(wiki)} | HOUSEKEEPING
    for entry in wiki.iterdir():
        if entry.is_dir() and entry.name not in allowed:
            sys.exit(
                f"refusing — undeclared top-level folder '{entry.name}' is not in wiki.toml. "
                "Declare it as a root, or move it out of the wiki."
            )


def _refuse(hits: list[str]) -> None:
    if hits:
        sys.exit(
            "refusing — what looks like an API credential is present in:\n"
            + "\n".join(hits)
            + "\ndelete the line or move the source out of the wiki; nothing was committed"
        )


def _scan_worktree(wiki: Path) -> None:
    """Every file `git add -A -f` would stage, read off disk — before git writes an object."""
    hits: list[str] = []
    for path in sorted(wiki.rglob("*")):
        rel = path.relative_to(wiki)
        # git stores a symlink as its target path, never the target's bytes: reading through
        # one would scan a file the wiki does not own and will never commit.
        if path.is_symlink() or not path.is_file() or ".git" in rel.parts or str(rel) == ENV:
            continue
        for n, line in enumerate(path.read_bytes().decode("utf-8", "replace").splitlines(), 1):
            if CREDENTIAL.search(line):
                hits.append(f"{rel} (line {n})")
    _refuse(hits)


def _scan(diff: str) -> None:
    """Refuse every credential-shaped added line of already-committed history, never the value."""
    hits: list[str] = []
    current, line, marks = None, 0, 0  # marks: a hunk line's prefix columns, one per parent
    for raw in diff.splitlines():
        hunk = _HUNK.match(raw)
        if raw.startswith("diff "):  # a new file section: only its own header may name it
            current, marks = None, 0
        elif hunk:
            line, marks = int(hunk.group(2)), len(hunk.group(1)) - 1
        elif not marks:  # a header or log line — never content, never counted
            if raw.startswith("+++ b/"):
                current = raw[6:]
        # A `-` in any column: gone from the result (a merge's ` -` too). `\`: "No newline" note.
        elif "-" not in raw[:marks] and not raw.startswith("\\"):
            if "+" in raw[:marks] and CREDENTIAL.search(raw[marks:]):  # content, whatever it spells
                hits.append(f"{current} (line {line})")
            line += 1
    _refuse(hits)


def _has_origin(wiki: Path) -> bool:
    return (
        history_dir(wiki).is_dir()
        and _git(wiki, "remote", "get-url", "origin", check=False).returncode == 0
    )


def _scan_before_push(wiki: Path) -> bool:
    """Fail closed: scan everything about to leave the machine. False when origin already has it."""
    ref = _git(wiki, "ls-remote", "--exit-code", "origin", "main", check=False)
    if ref.returncode == 2:  # origin has no main yet: first push, scan all local history
        _scan(
            _git(
                wiki,
                "log",
                "-p",
                "--cc",
                "--no-ext-diff",
                "--no-color",
                "--text",
                "HEAD",
                check=False,
            ).stdout
        )
        return True
    if ref.returncode != 0 or _git(wiki, "fetch", "-q", "origin", "main", check=False).returncode:
        sys.exit("--push: cannot reach origin/main; nothing was committed")
    log = _git(
        wiki,
        "log",
        "-p",
        "--cc",
        "--no-ext-diff",
        "--no-color",
        "--text",
        "FETCH_HEAD..HEAD",
        check=False,
    )
    if log.returncode != 0:
        sys.exit("--push: cannot reach origin/main; nothing was committed")
    _scan(log.stdout)
    return ref.stdout.split()[0] != _git(wiki, "rev-parse", "HEAD").stdout.strip()


def _push(wiki: Path) -> str:
    if _git(wiki, "push", "-q", "origin", "HEAD:main", check=False).returncode != 0:
        sys.exit(
            "--push: push to origin was rejected; run "
            f"`git --git-dir {history_dir(wiki)} push origin HEAD:main` by hand to see why"
        )
    return _git(wiki, "rev-parse", "--short", "HEAD").stdout.strip()


def snapshot(wiki: Path, author: str, push: bool = False) -> Snapshot | None:
    paths.refuse_git_inside(wiki)
    _refuse_undeclared_roots(wiki)
    if push and not _has_origin(wiki):
        sys.exit(f"--push: {history_dir(wiki)} has no 'origin' remote")
    _ensure_repo(wiki)
    _scan_worktree(wiki)  # a refused credential must never reach the object database
    # -f: no in-wiki .gitignore may hide a page from history, so only a pathspec leaves .env out
    _git(wiki, "add", "-A", "-f", *_PAGES)
    has_head = _git(wiki, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    if not _git(wiki, "status", "--porcelain", *_PAGES).stdout.strip():
        # A night whose push failed leaves commits behind origin — send them, never no-op.
        if not (push and has_head and _scan_before_push(wiki)):
            return None
        return Snapshot("pushed", _push(wiki))
    if push:
        _scan_before_push(wiki)
    identity = {
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": f"{author}@plow.local",
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": f"{author}@plow.local",
    }
    _git(
        wiki,
        "commit",
        "-q",
        "-m",
        f"wiki snapshot {datetime.now(UTC).date().isoformat()}",
        **identity,
    )
    if push:
        return Snapshot("snapshot", _push(wiki))
    return Snapshot("snapshot", _git(wiki, "rev-parse", "--short", "HEAD").stdout.strip())


def history(wiki: Path, page: str) -> list[str]:
    if not history_dir(wiki).is_dir():
        sys.exit("no history repo yet — run wiki snapshot first")
    # check=True throughout: a repo git cannot read breaks loudly, never reads as "no commits".
    if _git(wiki, "rev-list", "--all", "--count").stdout.strip() == "0":
        return [f"no commits touch {page}"]  # the repo exists, nothing is committed in it yet
    result = _git(wiki, "log", "--format=%h %ad %an", "--date=short", "--stat", "--", page)
    return [ln for ln in result.stdout.splitlines() if ln.strip()] or [f"no commits touch {page}"]
