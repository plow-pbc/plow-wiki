"""History for a wiki that must not be a git repo: a bare repo beside it, written only here."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from plow_wiki import paths

CREDENTIAL = re.compile(
    r"sk-[A-Za-z0-9_-]{16}|gh[pousr]_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{20}"
    r"|xox[abpr]-[A-Za-z0-9-]{10}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|eyJ[A-Za-z0-9_-]{20,}\."
)
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
HOUSEKEEPING = frozenset(
    {
        "AGENTS.md",
        "wiki.toml",
        "index.md",
        "log.md",
        "hot.md",
        ".manifest.json",
        ".wiki",
        ".obsidian",
        "_raw",
        "_archived",
        "_staging",
        ".DS_Store",
    }
)


def history_dir(wiki: Path) -> Path:
    return wiki.parent / ".wiki-history.git"


def _git(wiki: Path, *args: str, check: bool = True, **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "--git-dir", str(history_dir(wiki)), "--work-tree", str(wiki), *args],
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
    allowed = set(paths.load_roots(wiki)) | HOUSEKEEPING
    for entry in wiki.iterdir():
        if entry.name not in allowed:
            sys.exit(
                f"refusing — undeclared top-level path '{entry.name}' is not in wiki.toml. "
                "Declare it as a root, or move it out of the wiki."
            )


def _scan(diff: str) -> None:
    """Refuse every credential-shaped added line, naming file and line, never the value."""
    hits: list[str] = []
    current, line, previous = None, 0, ""
    for raw in diff.splitlines():
        hunk = _HUNK.match(raw)
        if raw.startswith("+++ b/") and previous.startswith("--- "):
            current = raw[6:]
        elif hunk:
            line = int(hunk.group(1))
        elif raw.startswith("+"):  # every other +line is added content, header or not
            if CREDENTIAL.search(raw[1:]):
                hits.append(f"{current} (line {line})")
            line += 1
        elif raw.startswith(" ") or not raw:
            line += 1
        previous = raw
    if hits:
        sys.exit(
            "refusing — what looks like an API credential was added in:\n"
            + "\n".join(hits)
            + "\ndelete the line or move the source out of the wiki; nothing was committed"
        )


def _has_origin(wiki: Path) -> bool:
    return (
        history_dir(wiki).is_dir()
        and _git(wiki, "remote", "get-url", "origin", check=False).returncode == 0
    )


def _scan_before_push(wiki: Path) -> None:
    """Fail closed: scan everything about to leave the machine, never a silent no-op."""
    ref = _git(wiki, "ls-remote", "--exit-code", "origin", "main", check=False)
    if ref.returncode == 2:  # origin has no main yet: first push, scan all local history
        _scan(_git(wiki, "log", "-p", "--cc", "--no-color", "--text", "HEAD", check=False).stdout)
        return
    if ref.returncode != 0:
        sys.exit("--push: cannot reach origin/main; nothing was committed")
    if _git(wiki, "fetch", "-q", "origin", "main", check=False).returncode != 0:
        sys.exit("--push: cannot reach origin/main; nothing was committed")
    log = _git(wiki, "log", "-p", "--cc", "--no-color", "--text", "FETCH_HEAD..HEAD", check=False)
    if log.returncode != 0:
        sys.exit("--push: cannot reach origin/main; nothing was committed")
    _scan(log.stdout)


def snapshot(wiki: Path, author: str, push: bool = False) -> str | None:
    paths.refuse_git_inside(wiki)
    _refuse_undeclared_roots(wiki)
    if push and not _has_origin(wiki):
        sys.exit(f"--push: {history_dir(wiki)} has no 'origin' remote")
    _ensure_repo(wiki)
    _git(wiki, "add", "-A", "-f")  # -f: an in-wiki .gitignore must not hide pages from history
    has_head = _git(wiki, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    staged = _git(
        wiki, "diff", "--cached", "--no-color", "--text", *(["HEAD"] if has_head else [])
    ).stdout
    if not staged.strip():
        return None
    _scan(staged)
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
    if push and _git(wiki, "push", "-q", "origin", "HEAD:main", check=False).returncode != 0:
        sys.exit(
            "--push: push to origin was rejected; run "
            f"`git --git-dir {history_dir(wiki)} push origin HEAD:main` by hand to see why"
        )
    return _git(wiki, "rev-parse", "--short", "HEAD").stdout.strip()


def history(wiki: Path, page: str) -> list[str]:
    if not history_dir(wiki).is_dir():
        sys.exit("no history repo yet — run wiki snapshot first")
    result = _git(
        wiki, "log", "--format=%h %ad %an", "--date=short", "--stat", "--", page, check=False
    )
    return [ln for ln in result.stdout.splitlines() if ln.strip()] or [f"no commits touch {page}"]
