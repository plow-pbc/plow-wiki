"""Per-root schemas: the only owner of what a page must carry."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from plow_wiki.frontmatter import FrontmatterError, parse

WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")  # [[path]] or [[path|alias]]; fullmatch
# [text](/path.md) — OKF's bundle-absolute form; the leading slash is required, so a
# page-relative link ([text](path.md)) or an external one ([text](https://...)) does not match.
MDLINK = re.compile(r"\[[^\]]*\]\(/([^)]+?)\.md\)")


def link_target(value) -> str | None:
    """The wiki-relative page path (no `.md`) a link field names, in either form; else None."""
    if not isinstance(value, str):
        return None
    if match := MDLINK.fullmatch(value):
        return unquote(match.group(1))  # a markdown destination carries `Jane Doe` as `Jane%20Doe`
    match = WIKILINK.fullmatch(value)
    return match.group(1) if match else None


FIELD_TYPES = frozenset({"date", "link", "string", "list"})


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
    fields = dict(meta.get("fields", {}))
    for name, rule in fields.items():
        # A rule is a mapping; its type, when given, is one of FIELD_TYPES.
        if not isinstance(rule, dict) or rule.get("type", "string") not in FIELD_TYPES:
            sys.exit(f"{path.relative_to(wiki)}: field {name!r} has unknown type")
    return Schema(
        required=list(meta.get("required", [])),
        fields=fields,
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
    category = root.split("/", 1)[0]  # obsidian-wiki's category: the top-level folder
    if "category" in meta and meta["category"] != category:
        problems.append(f"category must equal the root's top-level folder ({category})")
    sources = meta.get("sources")
    if "sources" in meta and (not isinstance(sources, list) or not sources):
        problems.append("sources must cite at least one source")
    elif "sources" in meta and not all(
        isinstance(s, dict) and isinstance(s.get("resource"), str) and s["resource"]
        for s in sources
    ):
        problems.append(
            "sources entries must be mappings with a resource"
        )  # OKF sources[].resource
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
        elif kind == "link" and link_target(value) is None:
            problems.append(f"{name} must be a link: [text](/path.md) or [[path]]")
        elif kind == "string" and not isinstance(value, str):
            problems.append(f"{name} must be a string")
        elif kind == "list" and not isinstance(value, list):
            problems.append(f"{name} must be a list")
    return problems
