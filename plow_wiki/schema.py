"""Per-root schemas: the only owner of what a page must carry."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from plow_wiki.frontmatter import FrontmatterError, parse

_WIKILINK = re.compile(r"^\[\[[^\]]+\]\]$")


@dataclass
class Schema:
    required: list[str]
    fields: dict[str, dict] = field(default_factory=dict)
    tables: list[dict] = field(default_factory=list)


def load_schema(root_dir: Path) -> Schema:
    path = root_dir / "_schema.md"
    if not path.is_file():
        sys.exit(f"{root_dir.name}/ has no _schema.md")
    try:
        meta, _ = parse(path.read_text())
    except FrontmatterError as e:
        sys.exit(f"{path}: {e}")
    return Schema(
        required=list(meta.get("required", [])),
        fields=dict(meta.get("fields", {})),
        tables=list(meta.get("tables", [])),
    )


def _is_date(value) -> bool:
    if isinstance(value, date):
        return True
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def validate_page(meta: dict, schema: Schema, root: str) -> list[str]:
    problems = [f"missing required field: {k}" for k in schema.required if k not in meta]
    if "category" in meta and meta["category"] != root:
        problems.append(f"category must equal the root ({root})")
    sources = meta.get("sources")
    if "sources" in meta and (not isinstance(sources, list) or not sources):
        problems.append("sources must cite at least one source")
    for name, rule in schema.fields.items():
        if name not in meta:
            continue
        value = meta[name]
        if "const" in rule and value != rule["const"]:
            problems.append(f"{name} does not match its required constant")
        if "enum" in rule and value not in rule["enum"]:
            problems.append(f"{name} is not an allowed value")
        kind = rule.get("type")
        if kind == "date" and not _is_date(value):
            problems.append(f"{name} must be a date (YYYY-MM-DD)")
        elif kind == "wikilink" and not (isinstance(value, str) and _WIKILINK.match(value)):
            problems.append(f"{name} must be a [[wikilink]]")
        elif kind == "string" and not isinstance(value, str):
            problems.append(f"{name} must be a string")
        elif kind == "list" and not isinstance(value, list):
            problems.append(f"{name} must be a list")
    return problems
