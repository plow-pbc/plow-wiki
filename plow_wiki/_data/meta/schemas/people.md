---
root: people
required: [title, summary, category, tags, sources, created, updated]
fields:
  type: {const: Person}
  org: {type: wikilink}
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
# people/

One page per person, slug `people/<first-last>.md`; `org` links the person's
`orgs/` page. Example:

```yaml
---
type: Person
title: Jane Doe
summary: Partner at Example Ventures; scheduling through her chief of staff.
category: people
tags: [person, investor]
sources: ["email:<thread-id>"]
created: 2026-09-14
updated: 2026-09-14
timezone: America/New_York
---
- Prefers 30-minute video calls before noon Eastern.
```
