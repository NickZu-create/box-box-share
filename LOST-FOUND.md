# Lost & Found and contact safety

Added after Impact in desktop and mobile navigation. Two boards separate found
items from lost items, with separate publishing entries. Search combines keywords,
12 item categories and place; occurrence date and status are optional extra filters.

Members can publish/edit their own notices, attach a sanitized image, mark an item
reunited or reopen a notice. Details link directly to a private conversation with
the poster; friendship and Buddy membership are not required. Messages identifies
the associated notice and links back to it.

Conversation and member pages provide blocking, unblocking and harassment reports.
Blocking prevents new messages and contacts in both directions, including existing
item, order, Buddy, friend and lost/found conversations. Historical messages and
existing order actions remain available. Blocking does not notify the other person.
Only participants can report a private conversation. Authorized moderators can
inspect reports and the associated conversation in Django admin.

## Code and data

- Additive migration: `market/migrations/0006_lostfound_blocks.py`.
- Models: LostFoundPost, UserBlock and nullable Thread.lostfound.
- Local demo database migrated after an SQLite backup under ignored `output/backups/`.
- Full suite: 87 tests passed. Migration drift and whitespace checks passed.
- Browser checks: combined keyword/category filtering, detail contact into the
  matching Messages example, safety controls, and all internal exported links.

## Public showcase

Updated the existing independent, public Sites showcase to version 2:
https://box-box-share-showcase.fantasy-zu.chatgpt.site/hans/lost-found/

It has 286 sanitized pages across three languages. Contact buttons open sample
conversations. Publishing, sending messages, blocking and reporting remain
browse-only demonstrations; they do not save changes or affect real users.
The corresponding Django backend is implemented and tested locally, not deployed
to the original Render service. The original GitHub main branch is unchanged.
