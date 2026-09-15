"""YAML frontmatter: the one parser every command shares."""

from __future__ import annotations

import re

import yaml

_BLOCK = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


class FrontmatterError(ValueError):
    """The page has no frontmatter block, or its YAML does not parse to a mapping."""


def parse(text: str) -> tuple[dict, str]:
    match = _BLOCK.match(text)
    if not match:
        raise FrontmatterError("no frontmatter block")
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise FrontmatterError("frontmatter is not valid YAML") from e  # never the excerpt
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter is not a mapping")
    # `field:` with nothing after it parses to None. It says nothing, so no command sees it:
    # dropping it here is what makes every reader below treat written-empty as absent.
    return {k: v for k, v in meta.items() if v is not None}, match.group(2)


def dump(meta: dict, body: str) -> str:
    block = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{block}\n---\n{body}"
