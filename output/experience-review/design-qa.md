# Box Box Share — interaction and layout review

Reviewed locally on 2026-11-04. This pass refines the approved existing interface; it does not replace the brand, Buddy approval, authentication, sharing, or message privacy rules. Render, the published Sites showcase, and production data were not changed.

## Evidence-led changes

1. **Buddy → group entry: crowded → clear.** The previous full-width group panel displaced the activity. The group entry now sits directly below its title as a compact contextual strip. Host creation, accepted-member opt-in, and pending eligibility retain their existing rules. [Before](01-buddy-before.jpg) · [After](11-buddy-after.jpg).
2. **Group conversation: noisy and fragile → compact and stable.** A smaller header retains recruitment context and a member roster. Leave and reporting actions use secondary menus and confirmations. New static messages append without replacing the conversation, preserving composer focus and open disclosure state. Long conversations scroll inside a bounded pane; the latest-message menu opens upward when necessary. [Desktop before](02-chat-before.jpg) · [Desktop after](12-final-desktop.jpg) · [Mobile before](03-mobile-before.jpg) · [Mobile after](13-final-mobile.jpg).
3. **Profile: long undifferentiated form → four sections.** Identity/basic information, Buddy preferences, contact details, and optional student information are grouped without changing field names, values, validation, or help links. Django retains native fields, upload support, errors and CSRF; its mobile save action remains reachable. [Before](04-profile-before.jpg) · [Static after](07-profile-after.jpg) · [Django mobile after](10-backend-nav-after.jpg).
4. **Mobile navigation and feedback: clipped controls → reachable actions.** The real Django navigation now has Explore, Seeking, Buddy, Messages and More; secondary destinations remain in More. Lost & Found → More → Profile was verified. Shared buttons, cards and menus have restrained hover/press/open feedback, visible focus, outside-click/Escape dismissal and reduced-motion guards. The original logo, button palette, warm textures and existing page flows remain.

## Checks completed

- Full Django suite after the final mobile-navigation change: **114 tests passed**; system check reported no issues. Tests used a disposable test database. The expected simulated AI timeout case logs an error while its test passes.
- Additional agent-run navigation/render checks: 17 passed. Existing pure demo rules: **14 passed**. Syntax checks for 9 maintained JavaScript files passed.
- Final static build completed. **311 HTML pages, 17,236 local references, zero missing local targets**. CSS asset URLs were also checked. All three language Profile pages retain 14 controls, four sections, four student-grid fields and save/status hooks.
- Browser document-width sweep: **24 page/viewport checks**, at actual widths 360, 768 and 1280. Pages included Explore, Seeking, Buddy, group chat, Traditional Chinese Profile, English publishing, Django group chat and Django Profile. No document-level horizontal overflow was found. Additional 390px mobile and 1024px desktop chat checks were performed.
- Static purchase: guest purchase → demo login → original item confirmation → awaiting-handover synthetic order. The chained-dialog close race no longer dismisses the purchase dialog.
- Static private chat: send and simulated reply; contact disclosure remains open across message updates; saved Profile changes persist in the tab. Contact-unlock rules remain unchanged.
- Static group chat: repeated sends preserve composer focus; Ctrl/Cmd+Enter; empty/whitespace report validation; successful report focus; leave cancellation; member menu; outside/Escape dismissal; late-message menu positioning; long-thread scroll/composer containment. Synthetic tools never contact another person.
- Real local Django: synthetic group send, member/leave controls and Profile rendering. After restarting the preview, More → Lost & Found → More → Profile worked; the five-item navigation had equal client/scroll widths at the checked mobile size.
- Checked browser error log was empty. The nested public-demo repository remains clean; no publishing or Git push was performed.

## Implementation

- Django presentation: market/templates/market/base.html, group_chat.html, group_controls.html and profile.html; market/static/market/experience.css and experience.js. Existing Lucide icons and their upstream license are retained.
- Static preview: group-demo.css/js, market-demo.js, experience.css/js; output/group_preview.py and experience_preview.py, integrated through build_preview_v3.py.
- No model, migration, authentication, approval, history-boundary or contact-access changes were introduced by this polish pass. The earlier group feature's migration remains a separate local implementation.

## Local previews and limits

- Interactive synthetic preview: http://127.0.0.1:8012/hans/buddy/2/; group conversation: http://127.0.0.1:8012/hans/messages/groups/2/. Demo identity/messages are sessionStorage state in the current tab.
- Real Django preview: http://127.0.0.1:8014/en/ using output.group_review_settings and the isolated synthetic output/group-review/preview.sqlite3. Local-file email is enabled; no real delivery was used.
- Messages still require manual refresh. No real-time delivery, typing or presence indicators are implied.
- Storage-failure handling now preserves input and rolls back failed synthetic saves. That failure branch was reviewed in code; browser storage exhaustion was not deliberately simulated.
- Responsive testing used a desktop browser viewport, not physical iOS/Android devices or their on-screen keyboards. Reduced-motion guards were reviewed in code; this is not a full accessibility or screen-reader compliance audit.
- Screenshots 06, 08 and 09 are intermediate captures, excluded from final layout evidence. Final group captures are 12 and 13; final real mobile navigation is 10.
- Loopback preview links work only on this computer. The existing hosted showcase remains on its previously published version.
