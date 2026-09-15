"""index.md and the tables each root's schema declares — generated from page frontmatter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from plow_wiki import paths
from plow_wiki.frontmatter import FrontmatterError, dump, parse
from plow_wiki.schema import WIKILINK, load_schema

GENERATED = ".wiki/generated.json"
INDEX = "index.md"
CHUNKS = ".wiki/chunks.json"
_FACT = re.compile(r"^\s*[-*+]\s+(\S.*?)\s*$")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load_pages(wiki: Path) -> dict[str, list[tuple[Path, dict]]]:
    by_root: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for root, page in paths.iter_pages(wiki):
        try:
            meta, _ = parse(page.read_text())
        except FrontmatterError:
            continue  # validate names it; the index skips it rather than guess
        by_root[root].append((page, meta))
    return by_root


def _line(value) -> str:
    """One line of authored text: no newline forges another."""
    return " ".join(str(value).split())


def _cell(value) -> str:
    """One index line or table cell: no newline forges a row, no `|` breaks one."""
    return _line(value).replace("|", r"\|")


def _link(wiki: Path, page: Path, meta: dict, sep: str = "|") -> str:
    """A table cell passes `\\|`: a bare `|` would split the cell the link sits in."""
    target = _cell(page.relative_to(wiki).with_suffix(""))
    return f"[[{target}{sep}{_cell(meta.get('title', page.stem))}]]"


def _tags(meta: dict) -> str:
    """obsidian-wiki's ` ( #tag1 #tag2)`, which `wiki-query` filters on; nothing for no tags."""
    tags = " ".join(f"#{_cell(tag)}" for tag in meta.get("tags", []))
    return f" ( {tags})" if tags else ""


def _generated_meta(title: str, rows: list[tuple[Path, dict]]) -> dict:
    """obsidian-wiki's required keys; dates span the pages listed, so a day alone churns nothing.

    Compared by calendar day: a datetime's own offset decides its day, and strings of mixed
    offsets would not order as the instants they name.
    """
    today = datetime.now(UTC).date().isoformat()
    return {
        "title": title,
        "generated": True,
        "category": "generated",
        "tags": ["generated"],
        "sources": [],
        "created": min((str(m["created"])[:10] for _, m in rows if "created" in m), default=today),
        "updated": max((str(m["updated"])[:10] for _, m in rows if "updated" in m), default=today),
    }


def _render_index(wiki: Path, by_root: dict) -> str:
    lines = ["# Wiki Index", ""]
    for root in paths.load_roots(wiki):
        lines.append(f"## {root}")
        for page, meta in sorted(by_root.get(root, []), key=lambda pm: str(pm[1].get("title", ""))):
            summary = _cell(meta.get("summary", ""))
            lines.append(f"- {_link(wiki, page, meta)} — {summary}{_tags(meta)}")
        lines.append("")
    listed = [pm for pages in by_root.values() for pm in pages]
    return dump(_generated_meta("Wiki Index", listed), "\n".join(lines))


def _sorted(rows: list, sort_by: str | None) -> list:
    return sorted(
        rows,
        key=lambda pm: (
            sort_by is not None and sort_by not in pm[1],
            str(pm[1].get(sort_by, "")) if sort_by else "",
        ),
    )


def _table(wiki: Path, columns: list[str], rows: list) -> list[str]:
    lines = ["| " + " | ".join(map(_cell, columns)) + " |", "|" + "---|" * len(columns)]
    for page, meta in rows:
        cells = [
            _link(wiki, page, meta, r"\|") if c == "title" else _cell(meta.get(c, ""))
            for c in columns
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _render_table(wiki: Path, name: str, spec: dict, rows: list[tuple[Path, dict]]) -> str:
    group_by = spec.get("group_by")
    groups: dict[str, list] = defaultdict(list)
    for page, meta in _sorted(rows, spec.get("sort_by")):
        groups[_cell(meta.get(group_by, "")) if group_by else ""].append((page, meta))
    lines = [f"# {name}", ""]
    for group, members in groups.items():
        lines += [f"## {group}"] if group else []
        lines += [*_table(wiki, spec["columns"], members), ""]
    title = f"{name} pipeline" if "{" in spec["path"] else name
    return dump(_generated_meta(title, rows), "\n".join(lines))


def _render_chunks(wiki: Path, by_root: dict) -> str:
    """What recall embeds: each page's summary and tags, then each fact bullet, in body order.

    Each chunk carries its root's writer, so recall can keep an agent-owned root to that agent.
    `by_root` is keyed by the page's declared root, nested ones included, so a nested root's
    writer is its own — never the top-level folder's."""
    writers = paths.load_roots(wiki)
    pages = sorted(
        ((page, meta, writers[root]) for root, pms in by_root.items() for page, meta in pms),
        key=lambda pmw: pmw[0].relative_to(wiki),
    )
    chunks = []
    for page, meta, writer in pages:
        slug = str(page.relative_to(wiki).with_suffix(""))
        title = _line(meta.get("title", page.stem))
        tags = " ".join(f"#{t}" for t in meta.get("tags", []))
        lead = " ".join(part for part in (_line(meta.get("summary", "")), tags) if part)
        _, body = parse(page.read_text())
        texts = ([lead] if lead else []) + [
            m.group(1) for m in map(_FACT.match, body.splitlines()) if m
        ]
        chunks += [{"page": slug, "title": title, "writer": writer, "text": t} for t in texts]
    updated = _generated_meta("", [(page, meta) for page, meta, _ in pages])["updated"]
    return json.dumps({"updated": updated, "chunks": chunks}, indent=1, ensure_ascii=False) + "\n"


def _splice(text: str, section: str, table: list[str], rel: str) -> tuple[str, str, str]:
    """`text` with the lines strictly between the `section` heading and the next `## ` heading
    (or the end) replaced by the table, every other byte kept; and that region, old and new."""
    lines = text.splitlines(keepends=True)
    at = next((i for i, line in enumerate(lines) if line.rstrip("\n") == section), None)
    if at is None:
        sys.exit(f"{rel} has no '{section}' heading for its table; nothing was written")
    end = next((i for i in range(at + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    old, new = "".join(lines[at + 1 : end]), "\n" + "\n".join(table) + "\n\n"
    # `section + "\n"`: Obsidian saves a last line, this heading perhaps, without its newline.
    return "".join(lines[:at]) + section + "\n" + new + "".join(lines[end:]), old, new


def _link_target(wiki: Path, value, source: str) -> Path:
    """The page a `[[path]]` or `[[path|alias]]` field names: in the wiki, and there."""
    link = WIKILINK.fullmatch(value) if isinstance(value, str) else None
    if link is None:
        sys.exit(f"{source} is not a [[wikilink]]")
    target = paths.contained(wiki, wiki / f"{link.group(1)}.md", source)
    if not target.is_file():
        sys.exit(f"{source} links a page that does not exist; nothing was written")
    return target


Regions = dict[str, tuple[str | None, str]]  # generated.json key -> (text now, text to write)


def _file_tables(wiki: Path, root: str, spec: dict, rows: list, files: dict, regions: Regions):
    pattern = spec["path"]
    tables = {pattern: (Path(pattern).stem, rows)}
    if "{" in pattern:
        key = pattern[pattern.index("{") + 1 : pattern.index("}")]
        by_value: dict[str, list] = defaultdict(list)
        for page, meta in rows:
            if key in meta:
                source = f"{page.relative_to(wiki)}: {key}"
                by_value[paths.safe_segment(str(meta[key]), source)].append((page, meta))
        tables = {pattern.replace("{" + key + "}", v): (v, m) for v, m in sorted(by_value.items())}
    for rel_path, (name, members) in tables.items():
        rel = f"{root}/{rel_path}"
        path = paths.contained(wiki, wiki / rel)
        files[path] = _render_table(wiki, name, spec, members)
        regions[rel] = (path.read_text() if path.exists() else None, files[path])


def _section_tables(wiki: Path, spec: dict, rows: list, files: dict, regions: Regions):
    """A table inside a hand-written page: each page `into`'s wikilink field names."""
    key, section = spec["into"], spec["section"]
    by_target: dict[Path, list] = defaultdict(list)
    for page, meta in rows:
        if key in meta:
            source = f"{page.relative_to(wiki)}: {key}"
            by_target[_link_target(wiki, meta[key], source)].append((page, meta))
    for target, members in sorted(by_target.items()):
        rel = str(target.relative_to(wiki.resolve()))
        table = _table(wiki, spec["columns"], _sorted(members, spec.get("sort_by")))
        text = files.get(target) or target.read_text()  # a page may take a table per section
        files[target], old, new = _splice(text, section, table, rel)
        regions[f"{rel}#{section}"] = (old, new)


def _outputs(wiki: Path, by_root: dict) -> tuple[dict[Path, str], Regions]:
    """Every file `wiki index` writes, with its new text, and every region it records."""
    index, chunks = paths.contained(wiki, wiki / INDEX), paths.contained(wiki, wiki / CHUNKS)
    files = {index: _render_index(wiki, by_root), chunks: _render_chunks(wiki, by_root)}
    # No text now for index.md: never guarded, since obsidian-wiki's skills rewrite it. chunks.json
    # is guarded like a table: a hand edit there is lost silently the moment recall re-embeds it.
    regions: Regions = {
        INDEX: (None, files[index]),
        CHUNKS: (chunks.read_text() if chunks.exists() else None, files[chunks]),
    }
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
            if "into" in spec:
                _section_tables(wiki, spec, rows, files, regions)
            else:
                _file_tables(wiki, root, spec, rows, files, regions)
    return files, regions


def _replace(path: Path, text: str) -> None:
    """Whole or not at all: a hub is hand-written, so a write cut short must never truncate it.
    The temp file is created exclusively, so no link planted beside the page can take the write."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def build(wiki: Path, force: bool = False) -> list[Path]:
    paths.refuse_git_inside(wiki)
    record_path = paths.contained(wiki, wiki / GENERATED)
    recorded = json.loads(record_path.read_text()) if record_path.is_file() else {}
    files, regions = _outputs(wiki, _load_pages(wiki))
    # A table file this build no longer generates: its pages are gone, so it must not answer for
    # them. A section's last table stays: the page around it is not the index's to delete.
    gone = sorted(k for k in recorded.keys() - regions.keys() if "#" not in k)
    stale = {key: paths.contained(wiki, wiki / key) for key in gone}
    if not force:
        now = {key: old for key, (old, _) in regions.items()}
        now |= {key: path.read_text() for key, path in stale.items() if path.exists()}
        for key, text in now.items():
            if text is not None and key in recorded and _sha(text) != recorded[key]:
                sys.exit(
                    f"{key} was hand-edited since `wiki index` wrote it; generated tables are "
                    "rebuilt from page frontmatter. Re-run with --force to overwrite."
                )
    for key, path in stale.items():
        path.unlink(missing_ok=True)
        del recorded[key]
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        _replace(path, text)
    recorded |= {key: _sha(new) for key, (_, new) in regions.items()}
    record_path.parent.mkdir(exist_ok=True)
    _replace(record_path, json.dumps(recorded, indent=1, sort_keys=True))
    return list(files)
