"""The `wiki` command line."""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path

from plow_wiki import paths

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki", description="Curated Plow wiki.")
    parser.add_argument("--wiki", help="wiki path (default: $WIKI_PATH or ~/Plow/wiki)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.add_argument("path")
    p.set_defaults(func=cmd_init)

    for name in SUBCOMMANDS:
        if name == "init":
            continue
        p = sub.add_parser(name)
        p.set_defaults(func=lambda args: sys.exit(f"wiki {args.command}: not implemented"))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
