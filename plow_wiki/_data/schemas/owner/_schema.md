---
root: owner
required: [type, title, summary, category, tags, sources, created, updated]
fields:
  type: {const: owner}
---
# owner/

The principal's own preferences and routing: which calendar family events go
on, which email address is for which purpose, default meeting length. One page
per topic, e.g. `owner/preferences.md`, `owner/calendars.md`. Example:

```yaml
---
type: owner
title: Meeting preferences
summary: Defaults the owner has stated for how meetings are booked.
category: owner
tags: [owner, preferences]
sources: ["plow:<chat-uid>/<message-id>"]
created: 2026-09-14
updated: 2026-09-14
---
- Default meeting length is 30 minutes, video.
```
