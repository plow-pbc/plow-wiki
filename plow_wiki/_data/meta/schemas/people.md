---
root: people
required: [type, title, summary, category, tags, sources, created, updated]
fields:
  type: {const: person}
  org: {type: wikilink}
  email: {type: string}
  phone: {type: string}
  timezone: {type: string}
---
# people/

One page per person, slug `people/<first-last>.md`. Example:

```yaml
---
type: person
title: Jane Doe
summary: Partner at Example Ventures; scheduling through her chief of staff.
category: people
tags: [person, investor]
sources: ["email:<thread-id>"]
created: 2026-09-14
updated: 2026-09-14
org: "[[orgs/example-ventures]]"
timezone: America/New_York
---
- Prefers 30-minute video calls before noon Eastern.
```
