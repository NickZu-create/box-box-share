# Marketplace demo review — 2026-11-02

Scope: existing static showcase only. Local preview: http://127.0.0.1:8012/hans/ . No deployment, production API, database changes, real account creation, payment, or outgoing messages in this iteration.

## Verified

- Generator rebuild completed. JavaScript syntax check passed. All 14 focused demo-rule assertions passed: contact threshold, both senders, blank/system exclusion, HK defaults/year rollover, title derivation, rental quotation, malformed shared payload handling.
- All 305 generated HTML pages checked for local link/script/style/image targets: zero unresolved local references.
- Guest rental request opens simulated login, resumes the same item's confirmation, and creates a sample request awaiting owner approval. Seven days at HK$8 produces HK$56, with HK$100 deposit separately displayed. Corrected order handover location to retain source item metadata.
- Guest purchase opens simulated login, resumes confirmation, and creates an awaiting-handover sample order; no payment or automatic completion.
- Sale publisher requires only amount and description; optional title derives from the first sentence. Rental defaults use HK current time, seven-day window, deposit zero, CityUHK campus, all editable. Want-to-buy publisher and type filtering verified.
- New tab opened from a published draft detail URL successfully displays the same title, description and HK$120 amount; guest login and purchase continuation succeed. Own-tab draft avoids self-purchase and directs the publisher to another example.
- Item cards/detail expose a separate small share control, direct detail URL and WhatsApp composer URL. Seeking has zero share buttons. No external share message was sent.
- Four one-sided messages keep contacts locked. Both senders plus four messages unlock; system/empty exclusions covered by focused tests. Independent conversation progression verified. Sign-out removes rendered contact values.
- Demo profile saves fictional contact fields in the tab. Contacts appear inside the eligible conversation, with separate own-contact preview, not public profile.
- Block confirmation hides rendered contacts and disables both sending and simulated peer reply; unblock retains history and restores eligibility. Existing report link retained.
- New conversation appears in inbox/sidebar with latest text and correct item return link.
- At actual viewport widths 360, 768 and 1280, Explore, Seeking, publisher, English sale and Traditional Chinese want-to-buy pages have no horizontal document overflow. Additional chat checks at 390 and 1280 verify mobile sidebar hidden and desktop rail/pane widths 320/879px respectively. Console error log empty during final checks.
- Screenshots visually inspected: mobile sale publisher, mobile unlocked contacts, desktop publisher, desktop messages. Compact dynamic conversation header refined after inspection.

## Limits

- Demo state is sessionStorage per tab. There is no cross-user synchronization, real authentication, durable inventory, server-enforced contact privacy, real seller approval, payment or realtime transport.
- The simulated peer reply button is explicitly labelled. It does not contact anyone. Peer contact values are fictional.
- Shared draft URL contains synthetic text and amounts, not an uploaded listing. Photos are kept only in the publishing tab and not carried into another person's browser.
- WeChat sharing uses the device's native share support when available, otherwise copy-link guidance; no claim of an implemented WeChat integration. WhatsApp opens its share composer; sending remains user-controlled.
- Only the local preview contains these new flows. The existing hosted showcase and Render production have not been updated.

## Evidence

- sale-publish-mobile.png — simplified publisher, 390px
- contacts-unlocked-mobile.png — conversation contact gate, 390px
- publish-desktop.png — simplified publisher, 1280px
- messages-desktop.png — new item-context conversation in existing dual-column layout, 1280px
- purchase-order-mobile.png — shared draft purchase order; captured at desktop width despite filename, do not use as mobile evidence
