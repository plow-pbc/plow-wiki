import pytest

from plow_wiki.frontmatter import FrontmatterError, dump, parse

PAGE = "---\ntitle: Jane Doe\ntags: [person]\nsources:\n  - email:abc\n---\n\n- A fact.\n"


def test_parse_returns_meta_and_body():
    meta, body = parse(PAGE)
    assert meta == {"title": "Jane Doe", "tags": ["person"], "sources": ["email:abc"]}
    assert body == "\n- A fact.\n"


@pytest.mark.parametrize("text", ["no frontmatter", "---\ntitle: x\n", "---\n: bad\n---\n"])
def test_parse_refuses_missing_or_malformed(text):
    with pytest.raises(FrontmatterError):
        parse(text)


def test_dump_round_trips():
    meta, body = parse(PAGE)
    assert parse(dump(meta, body)) == (meta, body)
