"""A `wiki init`'d vault, with one page per shipped schema example, is an OKF v0.2 bundle.

okflint is the de-facto linter (Google publishes no suite); its manifest is its own concept,
written here into the temp dir — the vault itself carries no okflint file."""

import subprocess
import sys
from pathlib import Path

from plow_wiki.frontmatter import dump
from tests.conftest import run_wiki

MANIFEST = """okf_version: "0.2"
base:
  name: plow-wiki
  roots:
    - path: {wiki}
      exclude_patterns: ["_raw/**", ".wiki/**"]
  reserved_files:
    index: index.md
    log: log.md
hygiene:
  broken_links: error
  okf_v02_shapes: error
  reserved_files: error
  legacy_forms: error
"""


def _page(type_, title, category, **fields):
    return dump(
        {
            "type": type_,
            "title": title,
            "description": f"{title}.",
            "category": category,
            "tags": [category],
            "sources": [{"resource": "https://example.com"}],
            "created": "2026-09-14",
            "updated": "2026-09-14",
            **fields,
        },
        "\n- A fact.\n",
    )


def test_an_initialised_wiki_is_okf_conformant(wiki: Path, tmp_path: Path):
    (wiki / "entities/orgs/example-ventures.md").write_text(
        _page("Organization", "Example Ventures", "entities")
    )
    (wiki / "entities/people/jane-doe.md").write_text(
        _page(
            "Person",
            "Jane Doe",
            "entities",
            org="[Example Ventures](/entities/orgs/example-ventures.md)",
        )
    )
    (wiki / "entities/owner/preferences.md").write_text(_page("Owner", "Preferences", "entities"))
    assert run_wiki("--wiki", str(wiki), "validate").returncode == 0
    assert run_wiki("--wiki", str(wiki), "index").returncode == 0
    manifest = tmp_path / "okf-base.yaml"
    manifest.write_text(MANIFEST.format(wiki=wiki))
    result = subprocess.run(
        [sys.executable, "-m", "okflint", "validate", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
