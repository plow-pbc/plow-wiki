import hashlib
import json
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
