from tests.conftest import run_wiki


def test_wiki_help_names_every_subcommand():
    result = run_wiki("--help")
    assert result.returncode == 0
    for name in ("init", "validate", "index", "snapshot", "history"):
        assert name in result.stdout
