---
type: Schema
root: entities/people
required: [type, title, description, category, tags, sources, created, updated]
fields:
  type: {const: Person}
  org: {type: link}
  email: {type: string}
  phone: {type: string}
  timezone: {type: string}
# obsidian-wiki's lint reads every .md under _meta as a page, so this file carries its keys:
title: people schema
category: meta
tags: [schema]
sources: []
created: 2026-09-14
updated: 2026-09-14
---
# entities/people/

One page per person, slug `entities/people/<first-last>.md`; `org` links the
person's `entities/orgs/` page. Example:

```yaml
---
type: Person
title: Jane Doe
description: Partner at Example Ventures; scheduling through her chief of staff.
category: entities
tags: [person, investor]
sources: [{resource: "email:<thread-id>"}]
created: 2026-09-14
updated: 2026-09-14
timezone: America/New_York
---
- Prefers 30-minute video calls before noon Eastern.
```

`org` is a link to the person's org page: a Markdown link whose target is the
page's bundle-absolute path, `/entities/orgs/<slug>.md`, or an Obsidian
wikilink to it.
