# plow-wiki

A user who opens `~/Plow/wiki` should recognise what they have: an LLM wiki
(Karpathy's pattern, as [obsidian-wiki](https://github.com/Ar9av/obsidian-wiki)
implements it) kept in an Obsidian vault, whose files are an
[OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
bundle.

## Install

```sh
uv tool install plow-wiki
wiki init ~/Plow/wiki
```

Open `~/Plow/wiki` in Obsidian. Agents reach it through Latch, which stages a
released binary rather than this package.

## What you get

A folder you open in Obsidian. Its layout is [obsidian-wiki](https://github.com/Ar9av/obsidian-wiki)'s
(`entities/`, `concepts/`, `skills/`, `references/`, `synthesis/`, `journal/`, `projects/`, with
`_raw/` as the inbox and `AGENTS.md` as the curation policy), so its `wiki-query`, `wiki-ingest`,
`wiki-lint` and `wiki-digest` skills work on it unchanged. Its files are an
[OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) bundle:
every page carries `type`, links are `[text](/path.md)`, `index.md` declares `okf_version`, and
`log.md` is reserved — so any OKF reader, validator or viewer takes it as is. Plow adds
`wiki.toml` (who writes which root), `_meta/schemas/` (what a root's pages carry),
`^[inferred]`/`^[ambiguous]` bullet markers, and snapshot history beside the vault.

## Viewing

Obsidian, first. Also: Google's reference `visualize` renders any bundle as a self-contained
[`viz.html`](https://github.com/GoogleCloudPlatform/open-knowledge-format#visualize);
[Inkeep Open Knowledge](https://github.com/inkeep/open-knowledge) edits one locally;
[W4G1/okf](https://github.com/W4G1/okf) explores one in a terminal;
[okflint](https://github.com/mattdav/okflint) validates one (our tests run it).

## Migrating a 0.1 vault

1. Move the roots: `mkdir entities && mv people orgs owner entities/`; an agent root
   `str/operations` becomes `projects/str/operations` (add `projects/str/str.md` as its overview).
2. In `wiki.toml` rename the roots (`"entities/people"`, …, `"projects/str"`) and move
   `_meta/schemas/` to match; in each schema, `wikilink` field types become `link`.
3. In every page: `summary:` → `description:`; `category:` → the top-level folder
   (`entities`, `projects`); each `sources:` string becomes `- resource: <the string>`.
   `[[links]]` may stay.
4. `wiki validate` lists what is left; then `wiki index --force` (tables re-render with
   markdown links) and `wiki snapshot`.

## Releases

Pushing a `v<ver>` tag publishes `wiki_<ver>_darwin_arm64.tar.gz` and
`wiki_<ver>_darwin_amd64.tar.gz`. Each holds one self-contained `wiki`, signed
with Plow's Developer ID, that needs no Python on the Mac. `checksums.txt`
carries their sha256 digests, which `latch-plugin.json`'s placeholders take. A
tag with a `-` (`v0.2.0-rc.1`) publishes a prerelease.

## Commands

| Command | Does |
|---|---|
| `wiki init <path>` | Creates the wiki: `AGENTS.md`, `wiki.toml`, `log.md`, `_raw/`, one folder per root, each root's schema at `_meta/schemas/<root>.md`, and the `.env` (`OBSIDIAN_VAULT_PATH`, `OBSIDIAN_LINK_FORMAT=markdown`) obsidian-wiki's skills find the wiki by |
| `wiki validate` | Checks every page's frontmatter against its root's schema |
| `wiki index` | Regenerates `index.md` and each root's declared tables with bundle-absolute markdown links, and `.wiki/chunks.json` (the facts agent recall embeds) |
| `wiki snapshot` | Commits the wiki, less `.env`, into `<wiki>.git` beside it (`~/Plow/wiki.git`) after a credential scan |
| `wiki history <path>` | Commits touching a page |

`WIKI_PATH` or `--wiki` names the wiki; default `~/Plow/wiki`.

A root in `wiki.toml` may nest, as `[roots."projects/str"]`, but never inside
another root. Its pages take `projects` as their `category`, its schema
is `_meta/schemas/projects/str.md`, and `index.md` gives it a
`## projects/str` section.

## Tables

A root's schema may declare tables, and `wiki index` rebuilds them from page
frontmatter:

```yaml
tables:
  - path: pipelines/{pipeline}.md  # one generated file per value of `pipeline`
    match: {type: relationship}
    group_by: stage
    sort_by: due
    columns: [title, state, due]
  - into: property  # inside the page each matching page's link field names
    section: "## Operations"
    match: {type: Operation}
    sort_by: title
    columns: [title, description]
```

A section table replaces only the lines between its heading and the next `## `
heading; the rest of the page stays the owner's. `wiki index` writes nothing
when a linked page or its heading is missing, and refuses to overwrite a table
edited by hand unless run with `--force`. A page that no page links any more
keeps its last table.

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
