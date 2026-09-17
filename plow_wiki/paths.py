"""Where the wiki is, what is a page, and the one invariant every writer checks."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

from obsidian_wiki.graph_analysis import SKIP_DIRS as OBSIDIAN_SKIP_DIRS

from plow_wiki.frontmatter import FrontmatterError, parse

# obsidian-wiki's own page selection, which it requires every module walking the vault to share,
# plus plow-wiki's generated-file record and git.
SKIP_DIRS = OBSIDIAN_SKIP_DIRS | {".wiki", ".git"}
SKIP_FILES = frozenset({"index.md", "log.md", "hot.md", "AGENTS.md"})
DEFAULT_WIKI = "~/Plow/wiki"
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")


def safe_segment(value: str, source: str) -> str:
    """One path component out of untrusted wiki content — a root name, a substituted field."""
    if value in {".", ".."} or not _SAFE_SEGMENT.fullmatch(value):
        sys.exit(f"{source} is not a safe path segment")
    return value


def resolve_wiki(arg: str | None) -> Path:
    return Path(arg or os.environ.get("WIKI_PATH") or DEFAULT_WIKI).expanduser().resolve()


def refuse_git_inside(wiki: Path) -> None:
    if (wiki / ".git").exists():
        sys.exit(f"{wiki}/.git exists — the wiki must not be a git repo; history lives beside it")


def load_roots(wiki: Path) -> dict[str, str]:
    """`{root: writer}` from wiki.toml. A wiki without one is not a wiki.

    A root may nest (`[roots."str/operations"]`), but never inside another root: a page must
    belong to exactly one."""
    toml = wiki / "wiki.toml"
    if not toml.is_file():
        sys.exit(f"{wiki} is not a wiki: no wiki.toml")
    roots = tomllib.loads(toml.read_text()).get("roots", {})
    for name in roots:
        parts = [safe_segment(part, f"{toml.name}: root {name!r}") for part in name.split("/")]
        if any("/".join(parts[:i]) in roots for i in range(1, len(parts))):
            sys.exit(f"{toml.name}: root {name!r} is inside another root; roots must not overlap")
    return {name: spec["writer"] for name, spec in roots.items()}


def contained(wiki: Path, path: Path, source: str | None = None) -> Path:
    """The resolved path, refusing one a symlink or `..` carries out of the wiki.

    `source` names where an untrusted path came from, so the refusal never echoes it."""
    resolved = path.resolve()
    if not resolved.is_relative_to(wiki.resolve()):
        sys.exit(f"refusing — {source or os.path.relpath(path, wiki)} is outside the wiki")
    return resolved


def is_generated(path: Path) -> bool:
    try:
        meta, _ = parse(path.read_text())
    except (FrontmatterError, OSError):
        return False
    return "generated_by" in meta or meta.get("generated") is True  # `generated: true`: a 0.1 vault


def iter_pages(wiki: Path) -> Iterator[tuple[str, Path]]:
    """Every page a human or agent authored, with the declared root it sits in."""
    inside = wiki.resolve()
    for root in load_roots(wiki):
        root_dir = wiki / root
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*.md")):
            if any(part in SKIP_DIRS for part in path.relative_to(wiki).parts):
                continue
            if path.name in SKIP_FILES or not path.resolve().is_relative_to(inside):
                continue  # a symlink out of the wiki is not this wiki's page
            if is_generated(path):
                continue
            yield root, path
