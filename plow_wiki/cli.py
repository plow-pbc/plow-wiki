"""The `wiki` command line."""

from __future__ import annotations

import argparse
import sys

SUBCOMMANDS = ("init", "validate", "index", "snapshot", "history")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki", description="Curated Plow wiki.")
    parser.add_argument("--wiki", help="wiki path (default: $WIKI_PATH or ~/Plow/wiki)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in SUBCOMMANDS:
        sub.add_parser(name)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.exit(f"wiki {args.command}: not implemented")


if __name__ == "__main__":
    raise SystemExit(main())
