import tomllib

from tests.conftest import run_wiki


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
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 1
    assert "people/bad.md: type must be person" in result.stdout
    assert "jane-doe" not in result.stdout


def test_validate_passes_a_clean_wiki(wiki):
    (wiki / "people" / "jane-doe.md").write_text(_page())
    result = run_wiki("validate", "--wiki", str(wiki))
    assert result.returncode == 0
    assert "validated 1 pages" in result.stdout
