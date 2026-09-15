import subprocess
import sys
from pathlib import Path

import pytest

from plow_wiki.frontmatter import dump

REPO = Path(__file__).resolve().parent.parent


def run_wiki(*args: str, cwd: Path | None = None, env: dict | None = None):
    return subprocess.run(
        [sys.executable, "-m", "plow_wiki.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    path = tmp_path / "wiki"
    result = run_wiki("init", str(path))
    assert result.returncode == 0, result.stderr
    return path


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
