from datetime import date
from pathlib import Path

import pytest

from plow_wiki.schema import link_target, load_schema, schema_path, validate_page

SCHEMA = """---
root: scheduling
required: [type, title, description, category, tags, sources, created, updated, state]
fields:
  type: {const: relationship}
  state: {enum: [idle, requested, awaiting_owner, offered, booked, met]}
  due: {type: date}
  org: {type: link}
---
"""

GOOD = {
    "type": "relationship",
    "title": "Example Ventures",
    "description": "s",
    "category": "scheduling",
    "tags": ["fundraising"],
    "sources": [{"resource": "email:1"}],
    "created": "2026-09-14",
    "updated": "2026-09-14",
    "state": "offered",
    "due": "2026-09-16",
    "org": "[Example Ventures](/entities/orgs/example-ventures.md)",
}


def _write_schema(wiki: Path, text: str) -> None:
    path = schema_path(wiki, "scheduling")
    path.parent.mkdir(parents=True)
    path.write_text(text)


@pytest.fixture
def schema(tmp_path: Path):
    _write_schema(tmp_path, SCHEMA)
    return load_schema(tmp_path, "scheduling")


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
        ({"org": "Example"}, "org must be a link"),
        ({"category": "people"}, "category must equal the root's top-level folder (scheduling)"),
        ({"sources": []}, "sources must cite at least one"),
        ({"sources": ["email:1"]}, "sources entries must be mappings with a resource"),
        ({"sources": [{"title": "x"}]}, "sources entries must be mappings with a resource"),
        ({"sources": [{"resource": ""}]}, "sources entries must be mappings with a resource"),
        ({"tags": "fundraising"}, "tags must be a list"),
    ],
)
def test_each_violation_is_named(schema, change, fragment):
    meta = {k: v for k, v in {**GOOD, **change}.items() if v is not None}
    problems = validate_page(meta, schema, "scheduling")
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize(
    "value, target",
    [
        ("[[entities/orgs/x]]", "entities/orgs/x"),
        ("[[entities/orgs/x|Alias]]", "entities/orgs/x"),
        ("[X](/entities/orgs/x.md)", "entities/orgs/x"),
        ("[X](entities/orgs/x.md)", None),
        ("[X](https://example.com)", None),
        ("[X](https://example.com/x.md)", None),
        ("see [x](/a.md) later", None),
        ("plain", None),
    ],
)
def test_link_target_reads_wikilinks_and_bundle_absolute_links(value, target):
    assert link_target(value) == target


def test_category_is_the_top_level_folder_of_a_nested_root(schema):
    meta = {**GOOD, "category": "projects"}
    assert validate_page(meta, schema, "projects/str/operations") == []
    meta["category"] = "operations"
    assert any(
        "top-level folder (projects)" in p
        for p in validate_page(meta, schema, "projects/str/operations")
    )


@pytest.mark.parametrize(
    "contents, fragment",
    [
        (None, "scheduling has no schema: _meta/schemas/scheduling.md is missing"),
        ("no frontmatter here\n", "no frontmatter block"),
        ("---\n: bad\n---\n", "not valid YAML"),
        ("---\n- a\n- b\n---\n", "not a mapping"),
        ("---\nrequired: [title]\nfields:\n  org: {type: wikilink}\n---\n", "has unknown type"),
        ("---\nrequired: [title]\nfields:\n  org: link\n---\n", "has unknown type"),
    ],
)
def test_load_schema_refuses_a_missing_or_malformed_schema(tmp_path, contents, fragment):
    if contents is not None:
        _write_schema(tmp_path, contents)
    with pytest.raises(SystemExit) as e:
        load_schema(tmp_path, "scheduling")
    assert fragment in str(e.value)


def test_a_schema_without_a_root_key_still_loads(tmp_path):
    _write_schema(tmp_path, "---\nrequired: [title]\n---\n")
    assert load_schema(tmp_path, "scheduling").required == ["title"]
