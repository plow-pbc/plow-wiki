import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plow_wiki.frontmatter import dump, parse
from plow_wiki.index import build

SCHEDULING_SCHEMA = """---
root: scheduling
required: [type, title, summary, category, tags, sources, created, updated]
fields:
  type: {const: relationship}
tables:
  - path: pipelines/{pipeline}.md
    match: {type: relationship}
    group_by: stage
    sort_by: due
    columns: [title, state, next_step, due]
---
"""


def _rel(title, stage, due, state="offered", pipeline="fundraising"):
    return dump(
        {
            "type": "relationship",
            "title": title,
            "summary": f"{title} summary",
            "category": "scheduling",
            "tags": ["x"],
            "sources": ["email:1"],
            "created": "2026-09-01",
            "updated": "2026-09-01",
            "pipeline": pipeline,
            "stage": stage,
            "state": state,
            "due": due,
            "next_step": "Confirm",
        },
        "\n## Log\n",
    )


@pytest.fixture
def sched_wiki(wiki: Path):
    (wiki / "wiki.toml").write_text(
        (wiki / "wiki.toml").read_text() + '[roots.scheduling]\nwriter = "calendaring"\n'
    )
    d = wiki / "scheduling" / "pipelines" / "fundraising"
    d.mkdir(parents=True)
    (wiki / "scheduling" / "_schema.md").write_text(SCHEDULING_SCHEMA)
    (d / "acme.md").write_text(_rel("Acme Capital", "scheduling", "2026-09-20"))
    (d / "beta.md").write_text(_rel("Beta Fund", "scheduling", "2026-09-10"))
    (d / "gamma.md").write_text(_rel("Gamma Partners", "met", "2026-09-05", state="met"))
    return wiki


def test_index_lists_every_page_under_its_root(sched_wiki):
    build(sched_wiki)
    text = (sched_wiki / "index.md").read_text()
    meta, body = parse(text)
    assert meta["generated"] is True
    assert "## scheduling" in body
    assert "[[scheduling/pipelines/fundraising/acme|Acme Capital]] — Acme Capital summary" in body


def test_table_groups_by_stage_and_sorts_by_due(sched_wiki):
    build(sched_wiki)
    body = (sched_wiki / "scheduling" / "pipelines" / "fundraising.md").read_text()
    met = body.index("## met")
    sched = body.index("## scheduling")
    assert met < sched, "groups follow first appearance after sorting by due"
    beta = body.index("Beta Fund")
    acme = body.index("Acme Capital")
    assert beta < acme
    assert (
        "| Gamma Partners" not in body
        and "[[scheduling/pipelines/fundraising/gamma|Gamma Partners]]" in body
    )


def test_index_refuses_to_overwrite_a_hand_edited_generated_file(sched_wiki):
    build(sched_wiki)
    target = sched_wiki / "scheduling" / "pipelines" / "fundraising.md"
    target.write_text(target.read_text() + "\nhand edit\n")
    with pytest.raises(SystemExit, match="hand-edited"):
        build(sched_wiki)
    build(sched_wiki, force=True)
    assert "hand edit" not in target.read_text()


def test_generated_hashes_are_recorded(sched_wiki):
    written = build(sched_wiki)
    recorded = json.loads((sched_wiki / ".wiki" / "generated.json").read_text())
    for path in written:
        rel = str(path.relative_to(sched_wiki))
        assert recorded[rel] == hashlib.sha256(path.read_bytes()).hexdigest()


def _with_field(page: Path, **over):
    meta, body = parse(page.read_text())
    meta.update(over)
    page.write_text(dump(meta, body))


def test_a_traversal_field_value_writes_nothing_inside_or_outside_the_wiki(sched_wiki):
    _with_field(
        sched_wiki / "scheduling" / "pipelines" / "fundraising" / "acme.md",
        pipeline="../../../../pwned",
    )
    escaped = sched_wiki.parent.parent / "pwned.md"  # where the traversal would land
    with pytest.raises(SystemExit) as e:
        build(sched_wiki)
    assert "scheduling/pipelines/fundraising/acme.md: pipeline is not a safe path segment" in str(
        e.value
    )
    assert "pwned" not in str(e.value), "the refusal names the source, never the page's value"
    assert not escaped.exists()
    assert not (sched_wiki / "index.md").exists(), "nothing is written inside the wiki either"


def test_a_traversal_table_path_in_a_schema_writes_nothing_outside_the_wiki(sched_wiki):
    (sched_wiki / "scheduling" / "_schema.md").write_text(
        SCHEDULING_SCHEMA.replace("pipelines/{pipeline}.md", "../../../pwned.md")
    )
    escaped = sched_wiki.parent.parent / "pwned.md"
    with pytest.raises(SystemExit, match="outside the wiki"):
        build(sched_wiki)
    assert not escaped.exists()
    assert not (sched_wiki / "index.md").exists()


def test_a_newline_summary_and_a_pipe_title_forge_neither_a_line_nor_a_column(sched_wiki):
    _with_field(
        sched_wiki / "scheduling" / "pipelines" / "fundraising" / "acme.md",
        title="Acme | Capital",
        summary="one\n- [[forged|Forged]] — injected",
    )
    build(sched_wiki)
    hits = [ln for ln in (sched_wiki / "index.md").read_text().splitlines() if "injected" in ln]
    assert len(hits) == 1, hits
    assert hits[0].startswith("- [[scheduling/pipelines/fundraising/acme|"), hits[0]
    assert "Acme \\| Capital" in hits[0]

    table = (sched_wiki / "scheduling" / "pipelines" / "fundraising.md").read_text()
    rows = [ln for ln in table.splitlines() if ln.startswith("| [[")]
    assert len({len(re.split(r"(?<!\\)\|", ln)) for ln in rows}) == 1, rows
    assert "Acme \\| Capital" in table


def test_a_generated_table_goes_when_its_last_page_does(sched_wiki):
    page = sched_wiki / "scheduling" / "pipelines" / "fundraising" / "acme.md"
    _with_field(page, pipeline="seed")
    build(sched_wiki)
    seed = sched_wiki / "scheduling" / "pipelines" / "seed.md"
    assert seed.is_file()

    page.unlink()
    build(sched_wiki)
    assert not seed.exists(), "a table nothing generates any more must not answer for the wiki"
    assert "seed.md" not in (sched_wiki / ".wiki" / "generated.json").read_text()


def test_an_empty_field_renders_an_empty_cell(sched_wiki):
    _with_field(sched_wiki / "scheduling" / "pipelines" / "fundraising" / "acme.md", next_step=None)
    build(sched_wiki)
    table = (sched_wiki / "scheduling" / "pipelines" / "fundraising.md").read_text()
    row = next(ln for ln in table.splitlines() if "Acme Capital" in ln)
    assert "None" not in row, row


def test_generated_updated_comes_from_the_pages_not_the_clock(sched_wiki):
    _with_field(
        sched_wiki / "scheduling" / "pipelines" / "fundraising" / "beta.md", updated="2026-09-08"
    )
    build(sched_wiki)
    for target in ("index.md", "scheduling/pipelines/fundraising.md"):
        meta, _ = parse((sched_wiki / target).read_text())
        assert str(meta["updated"]) == "2026-09-08", target


def test_generated_updated_falls_back_to_today_when_no_page_carries_one(wiki):
    build(wiki)
    meta, _ = parse((wiki / "index.md").read_text())
    assert str(meta["updated"]) == datetime.now(UTC).date().isoformat()
