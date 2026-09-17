---
type: Schema
root: entities/orgs
required: [title, description, category, tags, sources, created, updated]
fields:
  type: {const: Organization}
  website: {type: string}
# obsidian-wiki's lint reads every .md under _meta as a page, so this file carries its keys:
title: orgs schema
category: meta
tags: [schema]
sources: []
created: 2026-09-14
updated: 2026-09-14
---
# entities/orgs/

One page per organization, slug `entities/orgs/<name>.md`. Example:

```yaml
---
type: Organization
title: Example Ventures
description: Seed-stage fund; partners take first meetings themselves.
category: entities
tags: [org, investor]
sources: [{resource: "https://example.com/about"}]
created: 2026-09-14
updated: 2026-09-14
---
- Their scheduler books through a shared calendar link.
```
