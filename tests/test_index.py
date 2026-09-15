import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plow_wiki.frontmatter import dump, parse
from plow_wiki.index import build
from tests.conftest import SCHEDULING_SCHEMA, run_wiki


@pytest.mark.parametrize("tags, suffix", [(["x"], " ( #x)"), (["x", "y"], " ( #x #y)"), (None, "")])
def test_index_lists_every_page_under_its_root_in_obsidian_wikis_entry_format(
    sched_wiki, tags, suffix
):
    _with_field(sched_wiki / "scheduling" / "pipelines" / "fundraising" / "acme.md", tags=tags)
    build(sched_wiki)
    meta, body = parse((sched_wiki / "index.md").read_text())
    assert meta["generated"] is True
    lines = body.splitlines()
    entry = "- [[scheduling/pipelines/fundraising/acme|Acme Capital]] — Acme Capital summary"
    assert lines.index(entry + suffix) > lines.index("## scheduling")


def test_index_md_is_rewritten_over_a_hand_edit(sched_wiki):
    """obsidian-wiki's skills update index.md after every write; a refusal fails every nightly."""
    build(sched_wiki)
    index = sched_wiki / "index.md"
    index.write_text(index.read_text() + "- [[scheduling/new-page]] — added by wiki-ingest\n")
    build(sched_wiki)
    assert "wiki-ingest" not in index.read_text()


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
        and r"[[scheduling/pipelines/fundraising/gamma\|Gamma Partners]]" in body
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
    (sched_wiki / "_meta" / "schemas" / "scheduling.md").write_text(
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
    cells = len(["", "title", "state", "next_step", "due", ""])  # a link's own `|` splits no cell
    assert {len(re.split(r"(?<!\\)\|", ln)) for ln in rows} == {cells}, rows
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


def test_an_empty_updated_never_wins_the_generated_date(sched_wiki):
    _with_field(sched_wiki / "scheduling" / "pipelines" / "fundraising" / "acme.md", updated=None)
    build(sched_wiki)
    meta, _ = parse((sched_wiki / "index.md").read_text())
    assert str(meta["updated"]) == "2026-09-01"


def test_generated_dates_compare_calendar_days_not_offset_strings(sched_wiki):
    acme = sched_wiki / "scheduling" / "pipelines" / "fundraising" / "acme.md"
    _with_field(acme, updated="2026-09-20T23:30:00-08:00")
    build(sched_wiki)
    meta, _ = parse((sched_wiki / "index.md").read_text())
    assert str(meta["updated"]) == "2026-09-20"


def test_generated_updated_falls_back_to_today_when_no_page_carries_one(wiki):
    build(wiki)
    meta, _ = parse((wiki / "index.md").read_text())
    assert str(meta["updated"]) == datetime.now(UTC).date().isoformat()


OPERATIONS_SCHEMA = """---
required: [title]
tables:
  - into: property
    section: "## Operations"
    match: {type: Operation}
    sort_by: title
    columns: [title, summary]
---
"""
HUB = "---\ntitle: Casa\n---\n# Casa\n\nIntro prose.\n\n## Operations\n"
TABLE = (
    "\n| title | summary |\n|---|---|\n"
    "| [[str/operations/casa-trash\\|Trash]] | Bins go out Monday |\n"
    "| [[str/operations/casa-wifi\\|Wifi]] | Router in the hall |\n\n"
)


@pytest.fixture
def hub_wiki(wiki: Path) -> Path:
    """str's layout: hand-written hubs, and operations pages that link one each."""
    (wiki / "wiki.toml").write_text(
        (wiki / "wiki.toml").read_text()
        + '[roots."str/properties"]\nwriter = "str"\n[roots."str/operations"]\nwriter = "str"\n'
    )
    assert run_wiki("init", str(wiki)).returncode == 0
    (wiki / "_meta" / "schemas" / "str" / "operations.md").write_text(OPERATIONS_SCHEMA)
    (wiki / "str" / "properties" / "casa.md").write_text(HUB)
    for slug, title, summary, link in (
        ("casa-wifi", "Wifi", "Router in the hall", "[[str/properties/casa]]"),
        ("casa-trash", "Trash", "Bins go out Monday", "[[str/properties/casa|Casa]]"),
    ):
        meta = {"type": "Operation", "title": title, "summary": summary, "property": link}
        (wiki / "str" / "operations" / f"{slug}.md").write_text(dump(meta, "\n- A fact.\n"))
    return wiki


@pytest.mark.parametrize(
    "page, expected",
    [
        pytest.param(
            HUB + "- a list build-hubs left\n\n## Notes\nKeep this.\n",
            HUB + TABLE + "## Notes\nKeep this.\n",
            id="mid-page",
        ),
        pytest.param(
            HUB + "- a list build-hubs left", HUB + TABLE, id="last, saved without a final newline"
        ),
        pytest.param(HUB.removesuffix("\n"), HUB + TABLE, id="a bare heading on the last line"),
    ],
)
def test_a_section_table_lists_its_linking_pages_and_leaves_every_other_byte(
    hub_wiki, page, expected
):
    hub = hub_wiki / "str" / "properties" / "casa.md"
    hub.write_text(page)
    build(hub_wiki)
    assert hub.read_text() == expected

    edited = expected.replace("Intro prose.", "Intro prose, edited by the owner.")
    hub.write_text(edited)
    build(hub_wiki)
    first = hub.read_bytes()
    assert first.decode() == edited, "prose around the table is the owner's, not the index's"
    build(hub_wiki)
    assert hub.read_bytes() == first, "a second run changes nothing"


def _files(wiki: Path) -> dict[str, bytes]:
    return {str(p.relative_to(wiki)): p.read_bytes() for p in wiki.rglob("*") if p.is_file()}


def _hand_edit_the_table(wiki: Path) -> None:
    build(wiki)
    hub = wiki / "str" / "properties" / "casa.md"
    hub.write_text(hub.read_text().replace("Router in the hall", "Router moved"))


def test_a_write_that_fails_leaves_the_hand_written_hub_whole(hub_wiki, monkeypatch):
    hub = hub_wiki / "str" / "properties" / "casa.md"
    before = hub.read_text()

    def interrupted(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("plow_wiki.index.os.replace", interrupted)
    with pytest.raises(OSError):
        build(hub_wiki)
    assert hub.read_text() == before


@pytest.mark.parametrize(
    "breakage, refusal",
    [
        pytest.param(
            lambda w: (w / "str" / "properties" / "casa.md").write_text("---\ntitle: Casa\n---\n"),
            "str/properties/casa.md has no '## Operations' heading",
            id="missing heading",
        ),
        pytest.param(
            lambda w: _with_field(w / "str/operations/casa-wifi.md", property="[[str/nowhere]]"),
            "str/operations/casa-wifi.md: property links a page that does not exist",
            id="missing page",
        ),
        pytest.param(
            lambda w: _with_field(w / "str/operations/casa-wifi.md", property="[[../../../out]]"),
            "str/operations/casa-wifi.md: property is outside the wiki",
            id="a link out of the wiki",
        ),
        pytest.param(
            lambda w: _with_field(w / "str/operations/casa-wifi.md", property="Casa"),
            "str/operations/casa-wifi.md: property is not a [[wikilink]]",
            id="not a wikilink",
        ),
        pytest.param(
            _hand_edit_the_table, "casa.md### Operations was hand-edited", id="hand-edited table"
        ),
    ],
)
def test_a_section_table_refuses_and_writes_nothing(hub_wiki, breakage, refusal):
    breakage(hub_wiki)
    before = _files(hub_wiki)
    with pytest.raises(SystemExit) as e:
        build(hub_wiki)
    assert refusal in str(e.value)
    assert _files(hub_wiki) == before, "nothing is written anywhere"
