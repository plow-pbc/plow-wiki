import json
import os
import tomllib

import pytest
from obsidian_wiki.lint import lint_vault

from tests.conftest import REPO, run_wiki

RELEASE = "https://github.com/plow-pbc/plow-wiki/releases/download/v<ver>/"

CATEGORIES = ("concepts", "skills", "references", "synthesis", "journal")
ENTITY_ROOTS = ("entities/people", "entities/orgs", "entities/owner")


def test_wiki_help_names_every_subcommand():
    result = run_wiki("--help")
    assert result.returncode == 0
    for name in ("init", "validate", "index", "snapshot", "history"):
        assert name in result.stdout


def test_init_lays_out_the_wiki(wiki):
    assert (wiki / "AGENTS.md").is_file() and (wiki / "log.md").read_text() == "# Log\n"
    assert (wiki / ".env").read_text() == (
        f"OBSIDIAN_VAULT_PATH={wiki.resolve()}\nOBSIDIAN_LINK_FORMAT=markdown\n"
    )
    assert (wiki / "_raw").is_dir()
    roots = tomllib.loads((wiki / "wiki.toml").read_text())["roots"]
    assert set(roots) == set(ENTITY_ROOTS) | set(CATEGORIES)
    for root in roots:
        assert (wiki / root).is_dir()
        assert (wiki / "_meta" / "schemas" / f"{root}.md").is_file()
    assert "entities" not in roots  # the category folder holds roots; it is not one


def test_shipped_policy_and_schemas_carry_an_okf_type(wiki):
    from plow_wiki.frontmatter import parse

    assert parse((wiki / "AGENTS.md").read_text())[0]["type"] == "Policy"
    for root in ENTITY_ROOTS + CATEGORIES:
        assert parse((wiki / "_meta" / "schemas" / f"{root}.md").read_text())[0]["type"] == "Schema"


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
        "type": "Person",
        "title": "Jane Doe",
        "description": "s",
        "category": "entities",
        "tags": ["person"],
        "sources": [{"resource": "email:1"}],
        "created": "2026-09-14",
        "updated": "2026-09-14",
    }
    base.update(over)
    from plow_wiki.frontmatter import dump

    return dump(base, "\n- A fact.\n")


def test_validate_reports_bad_pages_by_path(wiki):
    (wiki / "entities" / "people" / "jane-doe.md").write_text(_page())
    (wiki / "entities" / "people" / "bad.md").write_text(_page(type="org"))
    (wiki / "entities" / "people" / "empty.md").write_text(_page(description=None))
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "entities/people/bad.md: type does not match its required constant" in result.stdout
    assert "entities/people/empty.md: missing required field: description" in result.stdout
    assert "jane-doe" not in result.stdout


@pytest.mark.parametrize(
    "root, page",
    [
        pytest.param("entities/people", _page(), id="type Person under the shipped people schema"),
        pytest.param(
            "notes", _page(type=None, category="notes"), id="no type under the base schema"
        ),
    ],
)
def test_validate_passes_a_clean_wiki(wiki, root, page):
    (wiki / "wiki.toml").write_text(
        (wiki / "wiki.toml").read_text() + '[roots.notes]\nwriter = "shared"\n'
    )
    assert run_wiki("init", str(wiki)).returncode == 0
    (wiki / root / "page.md").write_text(page)
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 0
    assert "validated 1 pages" in result.stdout


SECRET = "sk-abcdefghijklmnopqrstuvwxyz"  # shaped like an API key a person pasted into a page


def _leak_schema(const: str = "Person", enum: str = "idle") -> str:
    return f"---\nroot: entities/people\nrequired: [title]\nfields:\n  type: {{const: {const}}}\n  state: {{enum: [{enum}, met]}}\n---\n"


@pytest.mark.parametrize(
    "schema, page",
    [
        pytest.param(_leak_schema(), _page(type=SECRET), id="page const field"),
        pytest.param(_leak_schema(), _page(state=SECRET), id="page enum field"),
        pytest.param(
            _leak_schema(), f"---\ntitle: [unclosed\nsecret: {SECRET}\n---\n", id="malformed YAML"
        ),
        pytest.param(_leak_schema(const=SECRET), _page(), id="schema const"),
        pytest.param(_leak_schema(enum=SECRET), _page(state="flying"), id="schema enum"),
    ],
)
def test_validate_names_the_problem_and_never_echoes_the_value(wiki, schema, page):
    (wiki / "_meta" / "schemas" / "entities" / "people.md").write_text(schema)
    (wiki / "entities" / "people" / "leak.md").write_text(page)
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "entities/people/leak.md" in result.stdout
    assert SECRET not in result.stdout + result.stderr


def test_index_prints_what_it_wrote(wiki):
    (wiki / "entities" / "people" / "jane-doe.md").write_text(_page())
    result = run_wiki("index", "--wiki", str(wiki))
    assert result.returncode == 0
    assert "index.md" in result.stdout
    assert (
        "- [Jane Doe](/entities/people/jane-doe.md) — s ( #person)"
        in (wiki / "index.md").read_text()
    )


def test_snapshot_cli_reports_sha_then_nothing(wiki):
    (wiki / "entities" / "people" / "jane-doe.md").write_text(_page())
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
    findings = lint_vault(sched_wiki)["findings"]  # plow-wiki's own files pass obsidian-wiki's lint
    assert findings["missing_frontmatter"] == findings["broken_links"] == [], findings
    assert findings["machine_path_sources"] == [], findings


def test_latch_manifest_matches_the_cli():
    manifest = json.loads((REPO / "latch-plugin.json").read_text())
    assert manifest["command"] == "wiki"
    assert manifest["skill"] == "skill.md" and (REPO / "skill.md").is_file()
    argv = {bucket: {tuple(a) for a in cmds} for bucket, cmds in manifest["argv"].items()}
    assert argv["read"] == {("validate",), ("history",)}  # a command that writes is not a read
    assert argv["write"] == {("init",), ("index",), ("snapshot",)}
    (binary,) = manifest["runtime"]["binaries"]
    assert binary["name"] == "wiki"
    assert binary["url"] == {
        "arm64": RELEASE + "wiki_<ver>_darwin_arm64.tar.gz",
        "x64": RELEASE + "wiki_<ver>_darwin_amd64.tar.gz",
    }


@pytest.mark.parametrize(
    "roots, refusal",
    [
        pytest.param('[roots."../escaped"]', "not a safe path segment", id="traversal"),
        pytest.param(
            '[roots."str/../../escaped"]', "not a safe path segment", id="nested traversal"
        ),
        pytest.param(
            '[roots."str/operations"]\nwriter = "str"\n[roots.str]',
            "roots must not overlap",
            id="a root inside another",
        ),
    ],
)
def test_init_refuses_a_bad_root_and_creates_nothing_outside_the_wiki(tmp_path, roots, refusal):
    target = tmp_path / "wiki"
    target.mkdir()
    (target / "wiki.toml").write_text(f'{roots}\nwriter = "shared"\n')
    result = run_wiki("init", str(target))
    assert result.returncode == 1
    assert refusal in result.stderr
    assert not (tmp_path / "escaped").exists()
    assert not (target / "str").exists()


def test_a_nested_root_validates_indexes_and_snapshots(wiki):
    (wiki / "wiki.toml").write_text(
        (wiki / "wiki.toml").read_text() + '[roots."projects/str"]\nwriter = "str"\n'
    )
    assert run_wiki("init", str(wiki)).returncode == 0
    assert (wiki / "_meta" / "schemas" / "projects" / "str.md").is_file()
    ops = wiki / "projects" / "str" / "operations"
    ops.mkdir(parents=True)
    (ops / "casa-wifi.md").write_text(_page(type=None, title="Casa wifi", category="projects"))
    (ops / "bad.md").write_text(_page(type=None, category="operations"))
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.stdout.splitlines() == [
        "projects/str/operations/bad.md: category must equal the root's top-level folder (projects)"
    ]
    (ops / "bad.md").unlink()
    for cmd in (["validate"], ["index"], ["snapshot", "--author", "str"]):
        result = run_wiki("--wiki", str(wiki), *cmd)
        assert result.returncode == 0, (cmd, result.stdout, result.stderr)
    index = (wiki / "index.md").read_text()
    assert index.index("- [Casa wifi](/projects/str/operations/casa-wifi.md)") > index.index(
        "## projects/str"
    )


def test_a_page_symlinked_out_of_the_wiki_is_neither_indexed_nor_validated(wiki, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text(_page(title="Outside Page"))
    (wiki / "entities" / "people" / "outside.md").symlink_to(outside)
    (wiki / "entities" / "people" / "jane-doe.md").write_text(_page())
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
    assert not any(outside.iterdir()), "nothing is written through the symlink"


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
    (wiki / "entities" / "people" / "jane-doe.md").write_text(_page())
    result = run_wiki("index", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "outside the wiki" in result.stderr
    assert not any(outside.iterdir()), "generated.json is not written through the symlink"
    assert not (wiki / "index.md").exists(), "nothing is written inside the wiki either"


@pytest.mark.parametrize("flag_first", [True, False])
def test_the_wiki_flag_resolves_the_same_wiki_before_or_after_the_subcommand(
    wiki, tmp_path, flag_first
):
    (wiki / "entities" / "people" / "jane-doe.md").write_text(_page())
    argv = ("--wiki", str(wiki), "validate") if flag_first else ("validate", "--wiki", str(wiki))
    result = run_wiki(*argv, env={**os.environ, "WIKI_PATH": str(tmp_path / "decoy")})
    assert result.returncode == 0, result.stderr
    assert "validated 1 pages" in result.stdout


def test_validate_names_a_root_that_has_no_schema(wiki):
    (wiki / "_meta" / "schemas" / "entities" / "people.md").unlink()
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 1
    assert (
        "entities/people has no schema: _meta/schemas/entities/people.md is missing"
        in result.stderr
    )


def test_gitignore_keeps_review_artifacts_and_build_output_out_of_the_sdist():
    assert {".superpowers/", "dist/"} <= set((REPO / ".gitignore").read_text().split())
