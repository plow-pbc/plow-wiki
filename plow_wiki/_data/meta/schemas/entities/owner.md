---
type: Schema
root: entities/owner
required: [type, title, description, category, tags, sources, created, updated]
fields:
  type: {const: Owner}
# obsidian-wiki's lint reads every .md under _meta as a page, so this file carries its keys:
title: owner schema
category: meta
tags: [schema]
sources: []
created: 2026-09-14
updated: 2026-09-14
---
# entities/owner/

The principal's own preferences and routing: which calendar family events go
on, which email address is for which purpose, default meeting length. One page
per topic, e.g. `entities/owner/preferences.md`, `entities/owner/calendars.md`. Example:

```yaml
---
type: Owner
title: Meeting preferences
description: Defaults the owner has stated for how meetings are booked.
category: entities
tags: [owner, preferences]
sources: [{resource: "plow:<chat-uid>/<message-id>"}]
created: 2026-09-14
updated: 2026-09-14
---
- Default meeting length is 30 minutes, video.
```
