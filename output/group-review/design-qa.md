# Buddy group chat QA — 2026-11-03

Scope: existing Django project plus isolated synthetic static preview. No deployment, real school login, real email delivery, real user messages or production database mutation.

## Checks completed

- Full Django suite: 114 passed, including 14 new group tests. Covers host-only creation after acceptance, repeat and concurrent creation, concurrent joining, opt-in membership, current approval, later approvals, late-join watermark, repeat-join idempotency, rejoin watermark, withdrawal/removal revocation, group leave preserving Buddy membership, closed/ended recruitment, blocked peers, host blocking, report visibility boundaries, CSRF/POST-only actions, message validation/escaping, inbox and Buddy links in English/Traditional/Simplified, concurrent send versus withdrawal, and migration preserving old private messages/profile data.
- Existing pure demo checks: 14 passed. Syntax checks for new group-demo.js and modified market-demo.js passed. Migration dry-run: no changes detected.
- Migration applied only to a new output/group-review/preview.sqlite3. Original data.sqlite3 and online databases unchanged.
- Real browser flow on :8014: synthetic local-file sign-in; host creates group; membership count is one (host only); host sends a pre-join message; accepted member signs in and voluntarily joins; pre-join text absent; member sends a message; group leave confirmation works; rejoin hides previous membership text; sending works again. No mail network transport was enabled.
- Static browser flow on :8012: guest create prompts simulated login then resumes create; host starts alone; simulated Jamie opts in; group messages and explicit simulated replies work. Accepted-member example hides its pre-join message. Sample message report is local-only, group leave requires confirmation, rejoin hides old messages, and demo sign-out removes rendered group messages. Pending example has no join button.
- Responsive document checks at actual widths 360, 768, 1280: no horizontal overflow in backend group or static group. Static sidebar hidden at 360/768, desktop sidebar present at 1280. Additional 1024 desktop edge check passed. Browser console error log empty in checked flows.
- Corrected a generic header-style collision found by visual testing: group heading uses a local div, avoiding old fixed header height that covered the leave confirmation. Static group forms stop legacy inert-action notices from running after a successful simulated send/report. Message input validity resets on editing.

## Evidence

- group-desktop.jpg — static group in Messages at the desktop breakpoint.
- group-mobile.jpg — static mobile group from page top, with recruitment return, member controls, messages and composer.
- backend-member-desktop.png — real isolated Django group after rejoining. Earlier backend-host-desktop.png and demo-group-*.png were intermediate captures; do not treat them as final layout evidence.

## Limits

- Manual refresh; no realtime transport or typing/presence indicators.
- Backend loads latest 300 messages within the join boundary, consistent with the existing private-chat limit.
- Static demo stores synthetic content in sessionStorage and is not a privacy/security implementation. Only the Django services enforce actual membership and history isolation.
- No deployment or push performed. Existing public showcase and Render unchanged by this iteration.
