"""index.md and the tables each root's schema declares — generated, never hand-edited."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from plow_wiki import paths
from plow_wiki.frontmatter import FrontmatterError, dump, parse
from plow_wiki.schema import load_schema

GENERATED = ".wiki/generated.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_pages(wiki: Path) -> dict[str, list[tuple[Path, dict]]]:
    by_root: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for page in paths.iter_pages(wiki):
        try:
            meta, _ = parse(page.read_text())
        except FrontmatterError:
            continue  # validate names it; the index skips it rather than guess
        by_root[page.relative_to(wiki).parts[0]].append((page, meta))
    return by_root


def _cell(value) -> str:
    """One index line or table cell: no newline forges a row, no `|` breaks one."""
    return " ".join(str(value).split()).replace("|", r"\|")


def _link(wiki: Path, page: Path, meta: dict) -> str:
    target = _cell(page.relative_to(wiki).with_suffix(""))
    return f"[[{target}|{_cell(meta.get('title', page.stem))}]]"


def _generated_meta(title: str, rows: list[tuple[Path, dict]]) -> dict:
    """`updated` is the newest among the pages listed, so a new day alone churns nothing."""
    updated = max((str(m["updated"]) for _, m in rows if "updated" in m), default="")
    return {
        "title": title,
        "generated": True,
        "updated": updated or datetime.now(UTC).date().isoformat(),
    }


def _render_index(wiki: Path, by_root: dict) -> str:
    lines = ["# Wiki Index", ""]
    for root in paths.load_roots(wiki):
        lines.append(f"## {root}")
        for page, meta in sorted(by_root.get(root, []), key=lambda pm: str(pm[1].get("title", ""))):
            lines.append(f"- {_link(wiki, page, meta)} — {_cell(meta.get('summary', ''))}")
        lines.append("")
    listed = [pm for pages in by_root.values() for pm in pages]
    return dump(_generated_meta("Wiki Index", listed), "\n".join(lines))


def _render_table(wiki: Path, name: str, spec: dict, rows: list[tuple[Path, dict]]) -> str:
    sort_by, group_by, columns = spec.get("sort_by"), spec.get("group_by"), spec["columns"]
    rows = sorted(
        rows,
        key=lambda pm: (
            sort_by is not None and sort_by not in pm[1],
            str(pm[1].get(sort_by, "")) if sort_by else "",
        ),
    )
    groups: dict[str, list] = defaultdict(list)
    for page, meta in rows:
        groups[_cell(meta.get(group_by, "")) if group_by else ""].append((page, meta))
    lines = [f"# {name}", ""]
    for group, members in groups.items():
        if group:
            lines += [f"## {group}"]
        lines += ["| " + " | ".join(map(_cell, columns)) + " |", "|" + "---|" * len(columns)]
        for page, meta in members:
            cells = [
                _link(wiki, page, meta) if c == "title" else _cell(meta.get(c, "")) for c in columns
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    title = f"{name} pipeline" if "{" in spec["path"] else name
    return dump(_generated_meta(title, rows), "\n".join(lines))


def _targets(wiki: Path, by_root: dict) -> dict[Path, str]:
    """Every generated file and its new content."""
    out = {wiki / "index.md": _render_index(wiki, by_root)}
    for root in paths.load_roots(wiki):
        if not (wiki / root).is_dir():
            continue
        for spec in load_schema(wiki, root).tables:
            match = spec.get("match", {})
            rows = [
                (p, m)
                for p, m in by_root.get(root, [])
                if all(m.get(k) == v for k, v in match.items())
            ]
            pattern = spec["path"]
            if "{" in pattern:
                key = pattern[pattern.index("{") + 1 : pattern.index("}")]
                by_value: dict[str, list] = defaultdict(list)
                for page, meta in rows:
                    if key in meta:
                        source = f"{page.relative_to(wiki)}: {key}"
                        by_value[paths.safe_segment(str(meta[key]), source)].append((page, meta))
                for value, members in sorted(by_value.items()):
                    out[wiki / root / pattern.replace("{" + key + "}", value)] = _render_table(
                        wiki, value, spec, members
                    )
            else:
                out[wiki / root / pattern] = _render_table(wiki, Path(pattern).stem, spec, rows)
    return out


def build(wiki: Path, force: bool = False) -> list[Path]:
    paths.refuse_git_inside(wiki)
    record_path = paths.contained(wiki, wiki / GENERATED)
    recorded = json.loads(record_path.read_text()) if record_path.is_file() else {}
    targets = _targets(wiki, _load_pages(wiki))
    # What this build no longer generates: its pages are gone, so it must not answer for them.
    stale = [wiki / rel for rel in recorded if wiki / rel not in targets]
    for target in [*targets, *stale]:
        paths.contained(wiki, target)
    if not force:
        for target in [*targets, *stale]:
            rel = str(target.relative_to(wiki))
            if target.exists() and rel in recorded and _sha(target) != recorded[rel]:
                sys.exit(
                    f"{rel} was hand-edited since `wiki index` wrote it; "
                    f"generated files are rebuilt from page frontmatter. Re-run with --force to overwrite."
                )
    for target in stale:
        target.unlink(missing_ok=True)
        del recorded[str(target.relative_to(wiki))]
    for target, text in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        recorded[str(target.relative_to(wiki))] = _sha(target)
    record_path.parent.mkdir(exist_ok=True)
    record_path.write_text(json.dumps(recorded, indent=1, sort_keys=True))
    return list(targets)
