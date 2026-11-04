# Student profile and recommendation review — 2026-11-03

## Delivered

- Existing Django Profile/Buddy extended; original UI, approval/contact rules and multilingual rendering retained. Migration 0007 adds four optional profile fields, a server-owned null identity timestamp and one BuddyFeedback table.
- Existing Buddy search handles major, course name and spaced/hyphenated course codes. Signed-in member search appears on the same Buddy page. Lightweight weights use accepted participation, optional major, recent session searches, freshness and viewed/dismissed feedback. Unknown academic data does not contribute a zero score.
- University identity and separately authorized course/timetable contracts are disabled. No real SSO route or school-password input. No academic sync, no fabricated free-time badges.
- Static showcase includes the same optional fields and illustrates course/major search, ranking and dismissal using clearly synthetic metadata. Existing joined study example supplies its accepted activity signal. This client-side illustration is not production security or persistence.

## Validation

- Full Django test suite: 100 passed, including 13 new tests for optional/clearable fields, identity escalation rejection, guest privacy, escaped data, major/course search, blocked members, ranking and missing-data fallback, stronger accepted-participation signals, view/dismiss/restore, separate course/timetable consent, exploration, all three languages and old-profile migration.
- Migration dry-run: no changes detected. Migration applied only to a new isolated output/student-review/preview.sqlite3. Original data.sqlite3 and all online databases were not migrated.
- Existing static marketplace rule checks: 14 passed; JavaScript syntax checks pass.
- Real Django local browser flow on :8013: synthetic mailbox sign-in written to a local file, manual verification confirmation, Profile save and reload retaining Electrical Engineering, MA1201 search returning the matching study post. No email sent over a network.
- Static browser flow on :8012: MA1201 search, optional profile save/reload, related-major sample member result, studying interest ranking, dismissal moving the study post below other recommendations.
- Responsive checks at actual 360, 768 and 1280px: both Django Buddy/Profile and static Buddy/Traditional Profile have document content width at or below viewport width. No console errors in the checked session.
- Visual evidence: buddy-desktop.png, profile-desktop.png, buddy-mobile.png. Desktop Buddy preserves existing illustration, colors, horizontal recruitment rows and navigation; additions occupy a small second filter row.

## Remaining boundaries

- No real university account is marked verified; existing email-access verification keeps its prior limited meaning.
- No real course or timetable import exists. Integration approval, assertion validation, scoped consent, revocation, retention and current-term synchronization are future work. The backend ranker has a separately consented interval input, but receives an empty context now.
- Accepted joining is not proof of attendance. Only accepted records influence activity-category interest, not an invented attendance history.
- Cross-language programme synonyms/official course catalogs are not inferred. Text search uses supplied titles, descriptions, skills and self-reported major. No AI or background infrastructure added.
- Backend source stays local. Only the existing independent synthetic Sites showcase may be published under the user's explicit authorization. Render is untouched.

## Mobile More navigation repair

Reproduced on English Lost & Found: the legacy stylesheet supplied nav{overflow-x:auto}, computing both overflow axes as auto. The upward menu was open in the DOM but clipped; a menu click hit the lost-item publish button underneath. Scoped .mobile-primary{overflow:visible} fixes the fixed navigation without changing scrollable desktop navigation. Verified real hit-testing now targets My activity, and successive navigation to My activity, Profile, Impact and Lost & Found succeeds after refreshing older cached documents. Screenshot: more-fixed-mobile.png. The independent Sites archive contains this repair.
