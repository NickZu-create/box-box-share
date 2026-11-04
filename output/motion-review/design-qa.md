# Borrow / Seeking original hero and motion review

final result: passed

Scope: local synthetic preview only, 2026-11-02. This records the confirmed Borrow/Seeking iteration, not production integration or a universal aesthetic assessment.

## Delivered behavior

- Borrow reuses the existing public showcase hero markup, original copy, layered diagonal pink background, camera/books/backpack SVG, orbit/sticker details and CTA. Lower search, filters and inventory retain the new collection layout.
- Original primary color #d2234a, hover #b72755 and hero heading #96202e are restored. These are existing project colors, not a claim of verified official CityUHK color specifications.
- Borrow and Seeking share a 480 ms bidirectional route transition. The panel changes bounds while content fades without vertically stretching typography/artwork. Browsers without the native transition API use height animation with a content fade.
- Borrow scrolls from its full promotional form into a compact form and expands when scrolling back. A stable outer slot and sticky child keep the panel bottom and slot bottom aligned during collapse; no layout-height feedback loop is introduced.
- Direct Seeking entry contains compact markup only. It does not briefly construct the expanded Borrow hero.
- Original #discover CTA now targets the new collection tabs. Choosing Home/Borrow clears the hash and returns to the expanded top state.
- Links remain valid without enhancement. Failed route fetching falls back to normal navigation. Fetched scripts are never adopted. Rapid route requests are canceled, including a newer #discover action.

## Verification

- Generator completed successfully; Node syntax checks passed for preview.js and collection-motion.js.
- Six collection pages across en, zh and hans: 378 local link/asset references resolved, with zero missing targets.
- Eighteen browser geometry checks: two routes x three languages x 320/390/1280 CSS-pixel widths. No document, filter, hero-copy or CTA horizontal overflow. See responsive-results.json.
- Actual mobile and desktop screenshots were inspected. At 320 px the initial 33 px title broke into four fragmented lines; a narrow-screen type adjustment restores two complete Chinese phrases. The original hero remains fully illustrated on phones.
- Actual browser native route mode observed running and settled, in both directions. Revised snapshot clipping/fades avoid the initial stretched-artwork defect. Evidence: borrow-to-seeking-animation.png and seek-to-borrow-animation.png.
- Fallback mode exercised through an unlinked /__qa/motion-fallback/ fixture disabling only the native API. Borrow-to-Seeking settled at 154 px; reverse expansion executed. Evidence: fallback-animation.png. This is a forced branch check in the current browser, not cross-browser certification.
- Scroll: desktop intermediate progress about 0.287, endpoint compact, and return-to-top expanded all observed. Mobile compact endpoint 111.57 px. Slot/hero bottom gap was approximately 0.00005 px, within subpixel rounding. Evidence: borrow-mid-scroll.png, borrow-mobile-scroll.png.
- #discover scroll target remains below the sticky header. Home from #discover changes the URL to /hans/; reload retains y=0 and expanded state.
- Filter history: microphone query returns one visible wanted tile; switching to Borrow and Back restores /hans/seeking/?q=microphone, the query and one result. Same-page hash/filter Back restoration was also checked.
- Reduced-motion guards remove route animation and scroll-driven collapse in code/CSS. OS-level reduced-motion emulation and physical-device gestures were not available in this browser tool and are not claimed tested.

## Evidence

- borrow-desktop.png, seeking-desktop.png
- borrow-mobile-expanded.png, seeking-mobile.png
- borrow-mobile-320.png
- borrow-mid-scroll.png, borrow-mobile-scroll.png
- borrow-to-seeking-animation.png, seek-to-borrow-animation.png, fallback-animation.png

Screenshots are actual browser captures. The capture tool may return a scaled raster relative to the requested CSS viewport.

## Remaining boundaries

This iteration changes only the isolated preview generator and preview assets. All inventory, messages and orders are synthetic. Other page designs remain the prior preview version. Django integration, real accounts, real reservations, real-time messaging, production profile-service investigation and deployment are outside this scoped preview iteration. No real user message, transaction, Git push or deployment was performed. The pre-existing backend worktree edits were preserved.

No unresolved P0/P1/P2 defect was observed in the tested scope. Other browser engines, physical touch devices and assistive technologies still need their own verification before production release.
