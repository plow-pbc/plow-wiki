"""The `wiki` command line."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from plow_wiki import index as index_mod
from plow_wiki import paths
from plow_wiki import snapshot as snap
from plow_wiki.frontmatter import FrontmatterError, parse
from plow_wiki.schema import load_schema, schema_path, validate_page

BASE_SCHEMA = """---
root: {root}
required: [title, summary, category, tags, sources, created, updated]
fields: {{}}
# obsidian-wiki's lint reads every .md under _meta as a page, so this file carries its keys:
title: {root} schema
category: meta
tags: [schema]
sources: []
created: {today}
updated: {today}
---
# {root}/

Pages in this root carry the base fields only. Add fields and a table
declaration here as the root's conventions settle.
"""


def _data(name: str) -> Path:
    return Path(str(resources.files("plow_wiki") / "_data" / name))


def _write_absent(wiki: Path, dest: Path, text: str) -> None:
    """Install a file only where none exists: the owner may have edited the one that does."""
    dest = paths.contained(wiki, dest)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)


def cmd_init(args: argparse.Namespace) -> int:
    wiki = Path(args.path).expanduser().resolve()
    if wiki.exists() and not (wiki / "wiki.toml").is_file() and any(wiki.iterdir()):
        sys.exit(f"{wiki} exists and is not a wiki (no wiki.toml)")
    wiki.mkdir(parents=True, exist_ok=True)
    paths.refuse_git_inside(wiki)
    for name in ("AGENTS.md", "wiki.toml"):
        _write_absent(wiki, wiki / name, _data(name).read_text())
    # How obsidian-wiki's skills find the vault: they walk up from the cwd to this file.
    _write_absent(wiki, wiki / snap.ENV, f"OBSIDIAN_VAULT_PATH={wiki}\n")
    (wiki / "_raw").mkdir(exist_ok=True)
    today = datetime.now(UTC).date().isoformat()
    for root in paths.load_roots(wiki):
        paths.contained(wiki, wiki / root).mkdir(exist_ok=True)
        shipped = _data(f"meta/schemas/{root}.md")
        text = (
            shipped.read_text() if shipped.is_file() else BASE_SCHEMA.format(root=root, today=today)
        )
        _write_absent(wiki, schema_path(wiki, root), text)
    print(f"initialized {wiki}")
    return 0


def _problems(wiki: Path) -> tuple[list[str], int]:
    """Every validation problem in the wiki, as `path: problem` lines, plus the page count."""
    schemas = {
        root: load_schema(wiki, root) for root in paths.load_roots(wiki) if (wiki / root).is_dir()
    }
    lines, count = [], 0
    for page in paths.iter_pages(wiki):
        count += 1
        rel = page.relative_to(wiki)
        root = rel.parts[0]
        try:
            meta, _ = parse(page.read_text())
        except FrontmatterError as e:
            lines.append(f"{rel}: {e}")
            continue
        lines.extend(f"{rel}: {p}" for p in validate_page(meta, schemas[root], root))
    return lines, count


def cmd_validate(args: argparse.Namespace) -> int:
    wiki = paths.resolve_wiki(args.wiki)
    lines, count = _problems(wiki)
    for line in lines:
        print(line)
    if lines:
        return 1
    print(f"validated {count} pages")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    wiki = paths.resolve_wiki(args.wiki)
    for path in index_mod.build(wiki, force=args.force):
        print(path.relative_to(wiki))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    wiki = paths.resolve_wiki(args.wiki)
    author = args.author or os.environ.get("WIKI_AUTHOR") or os.environ.get("USER", "unknown")
    done = snap.snapshot(wiki, author=author, push=args.push)
    print(f"{done.action} {done.sha}" if done else "nothing to snapshot")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    for line in snap.history(paths.resolve_wiki(args.wiki), args.path):
        print(line)
    return 0


def _snapshot_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--push", action="store_true")
    p.add_argument("--author")


SUBCOMMANDS = {
    "init": (lambda p: p.add_argument("path"), cmd_init),
    "validate": (lambda p: None, cmd_validate),
    "index": (lambda p: p.add_argument("--force", action="store_true"), cmd_index),
    "snapshot": (_snapshot_args, cmd_snapshot),
    "history": (lambda p: p.add_argument("path"), cmd_history),
}


def _add_wiki_arg(p: argparse.ArgumentParser, default) -> None:
    p.add_argument("--wiki", default=default, help="wiki path (default: $WIKI_PATH or ~/Plow/wiki)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki", description="Curated Plow wiki.")
    _add_wiki_arg(parser, None)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (configure, func) in SUBCOMMANDS.items():
        p = sub.add_parser(name)
        if name != "init":
            # SUPPRESS: an unused subcommand flag must not overwrite `wiki --wiki /x validate`
            _add_wiki_arg(p, argparse.SUPPRESS)
        configure(p)
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
