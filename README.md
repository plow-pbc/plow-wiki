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
| `wiki init <path>` | Creates the wiki: `AGENTS.md`, `wiki.toml`, `_raw/`, one folder per root, and each root's schema at `_meta/schemas/<root>.md` |
| `wiki validate` | Checks every page's frontmatter against its root's schema |
| `wiki index` | Regenerates `index.md` and each root's declared tables |
| `wiki snapshot` | Commits the wiki into `<parent>/.wiki-history.git` after a credential scan |
| `wiki history <path>` | Commits touching a page |

`WIKI_PATH` or `--wiki` names the wiki; default `~/Plow/wiki`.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2026
The Plow Collective, Inc. The skills this package depends on come from
[obsidian-wiki](https://github.com/Ar9av/obsidian-wiki) (MIT).

"Plow" and the Plow logo are trademarks of The Plow Collective, Inc. The
license grants no trademark rights.
