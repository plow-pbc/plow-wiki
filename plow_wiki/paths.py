"""Where the wiki is, what is a page, and the one invariant every writer checks."""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

from plow_wiki.frontmatter import FrontmatterError, parse

SKIP_DIRS = frozenset({"_raw", "_archived", "_staging", ".obsidian", ".wiki", ".git"})
SKIP_FILES = frozenset({"index.md", "log.md", "hot.md", "AGENTS.md", "_schema.md"})
DEFAULT_WIKI = "~/Plow/wiki"


def resolve_wiki(arg: str | None) -> Path:
    return Path(arg or os.environ.get("WIKI_PATH") or DEFAULT_WIKI).expanduser().resolve()


def refuse_git_inside(wiki: Path) -> None:
    if (wiki / ".git").exists():
        sys.exit(f"{wiki}/.git exists — the wiki must not be a git repo; history lives beside it")


def load_roots(wiki: Path) -> dict[str, str]:
    """`{root: writer}` from wiki.toml. A wiki without one is not a wiki."""
    toml = wiki / "wiki.toml"
    if not toml.is_file():
        sys.exit(f"{wiki} is not a wiki: no wiki.toml")
    data = tomllib.loads(toml.read_text())
    return {name: spec["writer"] for name, spec in data.get("roots", {}).items()}


def is_generated(path: Path) -> bool:
    try:
        meta, _ = parse(path.read_text())
    except (FrontmatterError, OSError):
        return False
    return meta.get("generated") is True


def iter_pages(wiki: Path) -> Iterator[Path]:
    """Every page a human or agent authored, under declared roots only."""
    for root in load_roots(wiki):
        root_dir = wiki / root
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*.md")):
            if any(part in SKIP_DIRS for part in path.relative_to(wiki).parts):
                continue
            if path.name in SKIP_FILES or is_generated(path):
                continue
            yield path
