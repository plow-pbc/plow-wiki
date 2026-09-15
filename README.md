# plow-wiki

A curated, Obsidian-compatible wiki of durable facts, kept as plain Markdown in
`~/Plow/wiki` on the owner's Mac, written by agents and humans alike, and shared
by every Plow agent that drives that Mac.

## Install

```sh
uv tool install plow-wiki
wiki init ~/Plow/wiki
```

Open `~/Plow/wiki` in Obsidian. Agents reach it through Latch.

## Commands

| Command | Does |
|---|---|
| `wiki init <path>` | Creates the wiki: `AGENTS.md`, `wiki.toml`, `_raw/`, one folder per root, each root's schema at `_meta/schemas/<root>.md`, and the `.env` obsidian-wiki's skills find the wiki by |
| `wiki validate` | Checks every page's frontmatter against its root's schema |
| `wiki index` | Regenerates `index.md` and each root's declared tables |
| `wiki snapshot` | Commits the wiki, less `.env`, into `<wiki>.git` beside it (`~/Plow/wiki.git`) after a credential scan |
| `wiki history <path>` | Commits touching a page |

`WIKI_PATH` or `--wiki` names the wiki; default `~/Plow/wiki`.

A root in `wiki.toml` may nest, as `[roots."str/operations"]`, but never inside
another root. Its pages take the last segment as their `category`, its schema
is `_meta/schemas/str/operations.md`, and `index.md` gives it a
`## str/operations` section.

## Agent skills

An agent that uses the wiki needs five skills. One is this repo's
[`skill.md`](skill.md), installed as its `plow-wiki` skill: through `skills.tsv`
or fetched at a pinned commit for a Hermes agent, and through the manifest's
`skill` for a Latch plugin. The other four (`wiki-query`, `wiki-ingest`,
`wiki-lint`, `wiki-digest`) ship inside the `obsidian-wiki` wheel this package
depends on, under `obsidian_wiki/_data/skills/`. Installing the package puts
them on disk but publishes them to no agent, so the agent's image copies them
out of the wheel, with the Python that has `obsidian-wiki` installed:

```sh
src="$(python -c 'import obsidian_wiki, pathlib; print(pathlib.Path(obsidian_wiki.__file__).parent / "_data" / "skills")')"
for skill in wiki-query wiki-ingest wiki-lint wiki-digest; do
  cp -R "$src/$skill" "$SKILLS_DIR/$skill"
done
```

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2026
The Plow Collective, Inc. The skills this package depends on come from
[obsidian-wiki](https://github.com/Ar9av/obsidian-wiki) (MIT).

"Plow" and the Plow logo are trademarks of The Plow Collective, Inc. The
license grants no trademark rights.
