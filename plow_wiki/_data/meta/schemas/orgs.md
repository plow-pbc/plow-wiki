---
root: orgs
required: [title, summary, category, tags, sources, created, updated]
fields:
  type: {const: Organization}
  website: {type: string}
---
# orgs/

One page per organization, slug `orgs/<name>.md`. Example:

```yaml
---
type: Organization
title: Example Ventures
summary: Seed-stage fund; partners take first meetings themselves.
category: orgs
tags: [org, investor]
sources: ["https://example.com/about"]
created: 2026-09-14
updated: 2026-09-14
---
- Their scheduler books through a shared calendar link.
```
