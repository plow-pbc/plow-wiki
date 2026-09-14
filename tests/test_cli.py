import json
import os
import tomllib

import pytest

from tests.conftest import REPO, run_wiki


def test_wiki_help_names_every_subcommand():
    result = run_wiki("--help")
    assert result.returncode == 0
    for name in ("init", "validate", "index", "snapshot", "history"):
        assert name in result.stdout


def test_init_lays_out_the_wiki(wiki):
    assert (wiki / "AGENTS.md").is_file()
    assert (wiki / "_raw").is_dir()
    roots = tomllib.loads((wiki / "wiki.toml").read_text())["roots"]
    assert set(roots) == {"owner", "people", "orgs"}
    for root in roots:
        assert (wiki / root / "_schema.md").is_file()


def test_init_refuses_a_non_wiki_directory(tmp_path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "notes.txt").write_text("x")
    result = run_wiki("init", str(target))
    assert result.returncode == 1
    assert "not a wiki" in result.stderr


def test_init_is_idempotent_on_an_existing_wiki(wiki):
    (wiki / "AGENTS.md").write_text("owner edited")
    assert run_wiki("init", str(wiki)).returncode == 0
    assert (wiki / "AGENTS.md").read_text() == "owner edited"


def _page(**over):
    base = {
        "type": "person",
        "title": "Jane Doe",
        "summary": "s",
        "category": "people",
        "tags": ["person"],
        "sources": ["email:1"],
        "created": "2026-09-14",
        "updated": "2026-09-14",
    }
    base.update(over)
    from plow_wiki.frontmatter import dump

    return dump(base, "\n- A fact.\n")


def test_validate_reports_bad_pages_by_path(wiki):
    (wiki / "people" / "jane-doe.md").write_text(_page())
    (wiki / "people" / "bad.md").write_text(_page(type="org"))
    (wiki / "people" / "empty.md").write_text(_page(summary=None))
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "people/bad.md: type must be person" in result.stdout
    assert "people/empty.md: missing required field: summary" in result.stdout
    assert "jane-doe" not in result.stdout


def test_validate_passes_a_clean_wiki(wiki):
    (wiki / "people" / "jane-doe.md").write_text(_page())
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 0
    assert "validated 1 pages" in result.stdout


SECRET = "sk-abcdefghijklmnopqrstuvwxyz"  # shaped like an API key a person pasted into a page

LEAK_SCHEMA = """---
root: people
required: [title]
fields:
  type: {const: person}
  state: {enum: [idle, met]}
---
"""


@pytest.mark.parametrize(
    "page",
    [
        pytest.param(_page(type=SECRET), id="const field"),
        pytest.param(_page(state=SECRET), id="enum field"),
        pytest.param(f"---\ntitle: [unclosed\nsecret: {SECRET}\n---\n", id="malformed YAML"),
    ],
)
def test_validate_names_the_problem_and_never_echoes_the_value(wiki, page):
    (wiki / "people" / "_schema.md").write_text(LEAK_SCHEMA)
    (wiki / "people" / "leak.md").write_text(page)
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "people/leak.md" in result.stdout
    assert SECRET not in result.stdout + result.stderr


def test_index_prints_what_it_wrote(wiki):
    (wiki / "people" / "jane-doe.md").write_text(_page())
    result = run_wiki("index", "--wiki", str(wiki))
    assert result.returncode == 0
    assert "index.md" in result.stdout
    assert "[[people/jane-doe|Jane Doe]]" in (wiki / "index.md").read_text()


def test_snapshot_cli_reports_sha_then_nothing(wiki):
    (wiki / "people" / "jane-doe.md").write_text(_page())
    first = run_wiki("snapshot", "--wiki", str(wiki), "--author", "calendaring")
    assert first.returncode == 0 and first.stdout.startswith("snapshot ")
    second = run_wiki("snapshot", "--wiki", str(wiki), "--author", "calendaring")
    assert "nothing to snapshot" in second.stdout


def test_nightly_end_to_end(sched_wiki):
    env = {**os.environ, "WIKI_PATH": str(sched_wiki), "WIKI_AUTHOR": "calendaring"}
    for cmd in (["validate"], ["index"], ["snapshot"]):
        result = run_wiki(*cmd, env=env)
        assert result.returncode == 0, (cmd, result.stdout, result.stderr)
    assert "Acme Capital" in (sched_wiki / "index.md").read_text()
    table = sched_wiki / "scheduling" / "pipelines" / "fundraising.md"
    assert "## scheduling" in table.read_text()
    hist = run_wiki("history", "scheduling/pipelines/fundraising/acme.md", env=env)
    assert "calendaring" in hist.stdout


def test_latch_manifest_matches_the_cli():
    manifest = json.loads((REPO / "latch-plugin.json").read_text())
    assert manifest["command"] == "wiki"
    assert manifest["skill"] == "skill.md" and (REPO / "skill.md").is_file()
    argv = {bucket: {tuple(a) for a in cmds} for bucket, cmds in manifest["argv"].items()}
    assert argv["read"] == {("validate",), ("history",)}  # a command that writes is not a read
    assert argv["write"] == {("init",), ("index",), ("snapshot",)}


def test_init_refuses_a_traversal_root_and_creates_nothing_outside_the_wiki(tmp_path):
    target = tmp_path / "wiki"
    target.mkdir()
    (target / "wiki.toml").write_text('[roots."../escaped"]\nwriter = "shared"\n')
    result = run_wiki("init", str(target))
    assert result.returncode == 1
    assert "not a safe path segment" in result.stderr
    assert not (tmp_path / "escaped").exists()


def test_a_page_symlinked_out_of_the_wiki_is_neither_indexed_nor_validated(wiki, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text(_page(title="Outside Page"))
    (wiki / "people" / "outside.md").symlink_to(outside)
    (wiki / "people" / "jane-doe.md").write_text(_page())
    assert run_wiki("index", "--wiki", str(wiki)).returncode == 0
    assert "Outside Page" not in (wiki / "index.md").read_text()
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 0 and "validated 1 pages" in result.stdout


def test_init_refuses_a_root_symlinked_out_of_the_wiki(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "wiki"
    target.mkdir()
    (target / "wiki.toml").write_text('[roots.people]\nwriter = "shared"\n')
    (target / "people").symlink_to(outside)
    result = run_wiki("init", str(target))
    assert result.returncode == 1
    assert "outside the wiki" in result.stderr
    assert not any(outside.iterdir()), "no _schema.md is written through the symlink"


def test_init_refuses_a_shipped_file_symlinked_out_of_the_wiki(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "wiki"
    target.mkdir()
    (target / "wiki.toml").write_text('[roots.people]\nwriter = "shared"\n')
    (target / "AGENTS.md").symlink_to(outside / "AGENTS.md")  # dangling: exists() reads False
    result = run_wiki("init", str(target))
    assert result.returncode == 1
    assert "outside the wiki" in result.stderr
    assert not any(outside.iterdir()), "no template is written through the symlink"


def test_index_refuses_a_generated_record_symlinked_out_of_the_wiki(wiki, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (wiki / ".wiki").symlink_to(outside)
    (wiki / "people" / "jane-doe.md").write_text(_page())
    result = run_wiki("index", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "outside the wiki" in result.stderr
    assert not any(outside.iterdir()), "generated.json is not written through the symlink"
    assert not (wiki / "index.md").exists(), "nothing is written inside the wiki either"


@pytest.mark.parametrize("flag_first", [True, False])
def test_the_wiki_flag_resolves_the_same_wiki_before_or_after_the_subcommand(
    wiki, tmp_path, flag_first
):
    (wiki / "people" / "jane-doe.md").write_text(_page())
    argv = ("--wiki", str(wiki), "validate") if flag_first else ("validate", "--wiki", str(wiki))
    result = run_wiki(*argv, env={**os.environ, "WIKI_PATH": str(tmp_path / "decoy")})
    assert result.returncode == 0, result.stderr
    assert "validated 1 pages" in result.stdout


def test_validate_names_a_root_that_has_no_schema(wiki):
    (wiki / "people" / "_schema.md").unlink()
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "people/ has no _schema.md" in result.stderr


def test_gitignore_keeps_review_artifacts_and_build_output_out_of_the_sdist():
    assert {".superpowers/", "dist/"} <= set((REPO / ".gitignore").read_text().split())
