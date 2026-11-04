# Local design preview

Build from the existing sanitized showcase export:

```powershell
& ./.venv/Scripts/python.exe output/build_preview_v3.py
& ./.venv/Scripts/python.exe -m http.server 8012 --bind 127.0.0.1 --directory output/design-preview
```

Run from the Box Box Share workspace. Keep `preview.css`, `preview.js`, `collection.css`, `hero-motion.css`, `collection-motion.js`, and `preview-assets/` here; the generator does not overwrite them. Rebuild after editing assets to refresh the asset version in the generated pages. The old `output/build_design_preview.py` is retained for history and should not be used for this version.

Routes: `/hans/`, `/hans/buddy/`, `/hans/messages/`, `/hans/messages/7/`, `/hans/items/2/`. English uses `/en/`; Traditional Chinese uses `/zh/`.

The latest marketplace demo simulates sign-in, publishing, requests, purchases, messages and contact visibility in sessionStorage within the current tab. It never connects to real accounts, transactions or message recipients. This server is loopback-only. Publishing is not part of this workflow. See `../market-review/design-qa.md` for current checks and limits.

The latest review focuses only on Explore and Seeking (`/hans/seeking/`, `/zh/seeking/`, `/en/seeking/`). Their scoped visual layer is `collection.css`; other page designs stay at the previous preview version. Latest evidence and checks: `../collection-review/design-qa.md`. Unlinked `__qa/` pages are layout/date fixtures, not inventory records or product flows.

The original Borrow promotional hero is now restored above that collection layout. Bidirectional route transitions and continuous scroll collapse are in `hero-motion.css` and `collection-motion.js`. The latest hero/motion evidence and checks are in `../motion-review/design-qa.md`.

The shared detail pass now covers Buddy, Lost & Found, Messages and borrow management as well as collection controls. Keep `polish.css` and `polish.js` alongside the other maintained assets. `../polish_preview.py` adds the hooks during the existing build. Latest screenshots, checks and remaining limitations: `../polish-review/design-qa.md`.

Keep `market-demo.css`, `market-demo.js` and `demo-core.js` alongside these assets. `../marketplace_demo.py` generates their page hooks, publisher, synthetic sale/buy examples and dynamic demo routes. Build from the frozen sanitized `../showcase-baseline/`, not from a newly published export. Focused rules: `node output/test_demo_core.cjs` from the workspace root.

New routes: `/hans/items/sale-example/`, `/hans/items/new/`, `/hans/wanted/new/`, `/hans/wanted/buy-example/`, `/hans/profile/`. Generated listing detail links carry a sanitized synthetic payload in their hash, so the textual listing can open in a fresh tab. Photos remain local to the publishing tab. Orders and simulated conversations remain tab-specific. Seeking requests intentionally have no share control. The contact gate counts at least four messages in the same conversation, with at least one from each participant; system messages do not count. Blocking hides contacts and disables send/reply controls. This is a UI demonstration, not production authentication or privacy enforcement.

Buddy group chat preview: `/hans/buddy/1/` for host creation, `/hans/buddy/2/` for accepted-member opt-in, `/hans/buddy/3/` for pending eligibility. Group conversations render in `/hans/messages/groups/1/` and `/hans/messages/groups/2/`; groups appear alongside existing private chats. Keep `group-demo.js` and `group-demo.css`; `../group_preview.py` generates their hooks. Demo reset clears group state too. Latest group evidence: `../group-review/design-qa.md`. All group demo data is synthetic and tab-local; these changes have not been published.

The latest experience pass refines group entry/chat, Profile grouping, private-chat state and shared menu/button/focus feedback. Keep `experience.css` and `experience.js`; `../experience_preview.py` runs last in the generator. Final screenshots, checked flows, responsive coverage and limitations are in `../experience-review/design-qa.md`. This pass remains local and has not changed the hosted showcase.
