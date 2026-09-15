"""Per-root schemas: the only owner of what a page must carry."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from plow_wiki.frontmatter import FrontmatterError, parse

WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")  # [[path]] or [[path|alias]]; fullmatch


@dataclass
class Schema:
    required: list[str]
    fields: dict[str, dict] = field(default_factory=dict)
    tables: list[dict] = field(default_factory=list)


def schema_path(wiki: Path, root: str) -> Path:
    """Beside obsidian-wiki's own owner metadata, never among the pages a glob of a root finds."""
    return wiki / "_meta" / "schemas" / f"{root}.md"


def load_schema(wiki: Path, root: str) -> Schema:
    path = schema_path(wiki, root)
    if not path.is_file():
        sys.exit(f"{root} has no schema: {path.relative_to(wiki)} is missing")
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
    """An ISO date or datetime: obsidian-wiki's page template writes `created: ...T10:30:00Z`."""
    try:
        datetime.fromisoformat(str(value))  # str(): YAML already parsed an unquoted one
        return True
    except ValueError:
        return False


def validate_page(meta: dict, schema: Schema, root: str) -> list[str]:
    problems = [f"missing required field: {k}" for k in schema.required if k not in meta]
    category = root.rsplit("/", 1)[-1]  # str/operations holds obsidian-wiki's `operations`
    if "category" in meta and meta["category"] != category:
        problems.append(f"category must equal the root's last segment ({category})")
    sources = meta.get("sources")
    if "sources" in meta and (not isinstance(sources, list) or not sources):
        problems.append("sources must cite at least one source")
    if "tags" in meta and not isinstance(meta["tags"], list):  # the index renders each as a #tag
        problems.append("tags must be a list")
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
            problems.append(f"{name} must be an ISO date or datetime")
        elif kind == "wikilink" and not (isinstance(value, str) and WIKILINK.fullmatch(value)):
            problems.append(f"{name} must be a [[wikilink]]")
        elif kind == "string" and not isinstance(value, str):
            problems.append(f"{name} must be a string")
        elif kind == "list" and not isinstance(value, list):
            problems.append(f"{name} must be a list")
    return problems
