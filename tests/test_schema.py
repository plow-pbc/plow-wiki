from datetime import date
from pathlib import Path

import pytest

from plow_wiki.schema import load_schema, validate_page

SCHEMA = """---
root: scheduling
required: [type, title, summary, category, tags, sources, created, updated, state]
fields:
  type: {const: relationship}
  state: {enum: [idle, requested, awaiting_owner, offered, booked, met]}
  due: {type: date}
  org: {type: wikilink}
---
"""

GOOD = {
    "type": "relationship",
    "title": "Example Ventures",
    "summary": "s",
    "category": "scheduling",
    "tags": ["fundraising"],
    "sources": ["email:1"],
    "created": "2026-09-14",
    "updated": "2026-09-14",
    "state": "offered",
    "due": "2026-09-16",
    "org": "[[orgs/example-ventures]]",
}


@pytest.fixture
def schema(tmp_path: Path):
    (tmp_path / "_schema.md").write_text(SCHEMA)
    return load_schema(tmp_path)


@pytest.mark.parametrize(
    "due", ["2026-09-16", "2026-09-16T10:30:00Z", "2026-09-16T10:30:00-07:00", date(2026, 9, 16)]
)
def test_valid_page_has_no_problems(schema, due):
    assert validate_page({**GOOD, "due": due}, schema, "scheduling") == []


@pytest.mark.parametrize(
    "change, fragment",
    [
        ({"state": None}, "missing required field: state"),
        ({"state": "flying"}, "state is not an allowed value"),
        ({"type": "person"}, "type does not match its required constant"),
        ({"due": "next week"}, "due must be an ISO date or datetime"),
        ({"org": "Example"}, "org must be a [[wikilink]]"),
        ({"category": "people"}, "category must equal the root"),
        ({"sources": []}, "sources must cite at least one"),
    ],
)
def test_each_violation_is_named(schema, change, fragment):
    meta = {k: v for k, v in {**GOOD, **change}.items() if v is not None}
    problems = validate_page(meta, schema, "scheduling")
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize(
    "contents, fragment",
    [
        (None, "has no _schema.md"),
        ("no frontmatter here\n", "no frontmatter block"),
        ("---\n: bad\n---\n", "not valid YAML"),
        ("---\n- a\n- b\n---\n", "not a mapping"),
    ],
)
def test_load_schema_refuses_a_missing_or_malformed_schema(tmp_path, contents, fragment):
    root = tmp_path / "scheduling"
    root.mkdir()
    if contents is not None:
        (root / "_schema.md").write_text(contents)
    with pytest.raises(SystemExit) as e:
        load_schema(root)
    assert fragment in str(e.value)


def test_a_schema_without_a_root_key_still_loads(tmp_path):
    (tmp_path / "_schema.md").write_text("---\nrequired: [title]\n---\n")
    assert load_schema(tmp_path).required == ["title"]
