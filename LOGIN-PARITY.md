# Logged-in website comparison — 2026-10-28

Compared the existing signed-in Chrome session at `https://box-box-share.onrender.com/`
with Claude branch `claude/admiring-galileo-9bmno1`, commit `1f397809`.
The local preview uses independent, explicitly labelled test records. No production
account, listing, request, message or order was changed or copied into the preview.

## Findings

| Existing area | Result in the latest Buddy branch |
| --- | --- |
| Explore and Seeking | Original page layout, hero, filters and listing/request details retained. |
| My activity | Orders, own listings, own requests and edit/publish links retained; Buddy added below. |
| Messages | Existing conversations, notifications and mark-all-read retained; friends added alongside. |
| Orders | Booking, payment confirmations, handover/return, extension, dispute and review logic retained. Production account has no orders, so these were checked locally and in tests. |
| Public member page | Avatar, rating and community reviews retained. Report entry had become conditional on friend eligibility; restored the original entry for other members. Existing server permission checks remain. |
| Profile | Production page was unavailable in the earlier check. Claude's plain file-input fix is already present; tested local profile with an uploaded avatar and the database-storage regression test passes. |
| Impact | No diff from main in its calculation or original template before this work. Three statistics, six categories, five reference links, survey threshold, method, method source and limitations all remain visible in the local browser. Zero completed orders do not hide them. |

## Changes in this workspace

- Restore the public member report entry independently of friend eligibility.
- Localize Impact category names and Chinese reference-item names through the same
  language mechanism as the rest of the Buddy branch. Preserve all calculations,
  factors, links, layout and explanatory text.
- Add member-page regression checks for original records, edit links, conversations,
  notifications, booking, offers and reviews.
- Check full Impact content as both a guest and a signed-in member in English,
  Traditional Chinese and Simplified Chinese, with zero and nonzero completed orders.

## Preview boundaries

The local database is separate from the hosted database. Empty local lists do not
establish that a feature or production record was deleted. A signed-out browser
also hides My activity, Messages and the profile link by design.

The two existing local Chrome tabs pointed at `http://127.0.0.1:8000/。`.
The working local preview is `http://127.0.0.1:8000/` (without the final punctuation).

Changes are local; no push, merge or deployment was performed.

## Verification

- Full Django suite: 79 tests passed (74 existing plus 5 parity checks).
- Django system checks: no issues. Git whitespace checks passed.
- Chrome local signed-in preview: original dashboard records, avatar profile and
  complete Impact page inspected. Impact screenshots saved under `output/`.
- Screenshots contain local test values, not the production impact figures.
