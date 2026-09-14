"""The `wiki` command line."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from plow_wiki import index as index_mod
from plow_wiki import paths
from plow_wiki import snapshot as snap
from plow_wiki.frontmatter import FrontmatterError, parse
from plow_wiki.schema import load_schema, validate_page

SUBCOMMANDS = ("init", "validate", "index", "snapshot", "history")

BASE_SCHEMA = """---
root: {root}
required: [type, title, summary, category, tags, sources, created, updated]
fields: {{}}
---
# {root}/

Pages in this root carry the base fields only. Add fields and a table
declaration here as the root's conventions settle.
"""


def _data(name: str) -> Path:
    return Path(str(resources.files("plow_wiki") / "_data" / name))


def cmd_init(args: argparse.Namespace) -> int:
    wiki = Path(args.path).expanduser().resolve()
    if wiki.exists() and not (wiki / "wiki.toml").is_file() and any(wiki.iterdir()):
        sys.exit(f"{wiki} exists and is not a wiki (no wiki.toml)")
    wiki.mkdir(parents=True, exist_ok=True)
    paths.refuse_git_inside(wiki)
    for name in ("AGENTS.md", "wiki.toml"):
        if not (wiki / name).exists():
            shutil.copy(_data(name), wiki / name)
    (wiki / "_raw").mkdir(exist_ok=True)
    for root in paths.load_roots(wiki):
        (wiki / root).mkdir(exist_ok=True)
        schema = wiki / root / "_schema.md"
        if schema.exists():
            continue
        shipped = _data(f"schemas/{root}/_schema.md")
        schema.write_text(
            shipped.read_text() if shipped.is_file() else BASE_SCHEMA.format(root=root)
        )
    print(f"initialized {wiki}")
    return 0


def _problems(wiki: Path) -> tuple[list[str], int]:
    """Every validation problem in the wiki, as `path: problem` lines, plus the page count."""
    schemas = {
        root: load_schema(wiki / root) for root in paths.load_roots(wiki) if (wiki / root).is_dir()
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
    sha = snap.snapshot(wiki, author=author, push=args.push)
    print(f"snapshot {sha}" if sha else "nothing to snapshot")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    for line in snap.history(paths.resolve_wiki(args.wiki), args.path):
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    wiki_arg = argparse.ArgumentParser(add_help=False)
    wiki_arg.add_argument("--wiki", help="wiki path (default: $WIKI_PATH or ~/Plow/wiki)")

    parser = argparse.ArgumentParser(
        prog="wiki", description="Curated Plow wiki.", parents=[wiki_arg]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.add_argument("path")
    p.set_defaults(func=cmd_init)

    for name in SUBCOMMANDS:
        if name == "init":
            continue
        p = sub.add_parser(name, parents=[wiki_arg])
        if name == "validate":
            p.set_defaults(func=cmd_validate)
            continue
        if name == "index":
            p.add_argument("--force", action="store_true")
            p.set_defaults(func=cmd_index)
            continue
        if name == "snapshot":
            p.add_argument("--push", action="store_true")
            p.add_argument("--author")
            p.set_defaults(func=cmd_snapshot)
            continue
        if name == "history":
            p.add_argument("path")
            p.set_defaults(func=cmd_history)
            continue
        p.set_defaults(func=lambda args: sys.exit(f"wiki {args.command}: not implemented"))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
