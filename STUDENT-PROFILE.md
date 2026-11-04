# Optional student profile and Buddy recommendations

Phase 1 is implemented in the Django project. No school service is connected.

## Data and access

Migration `0007_student_profile_recommendations` adds four optional strings to Profile: university, major, academic_year and faculty. Empty defaults preserve old registrations. Existing users can edit or clear these fields in the existing Profile form. They appear on member profiles only for signed-in members; guests cannot search private host-major values to infer them. There is no student directory page.

`verified` continues to mean verified mailbox access. It is not a university identity assertion. Only a non-null server-owned `university_verified_at` may show University Account Verified. Neither field is accepted by ProfileForm. All current users receive null for the new identity field. Manual major/year/faculty values are explicitly self-reported, even if the account eventually receives an identity verification badge.

BuddyFeedback stores one viewed/dismissed record per member/post, without message or schedule content. The detail view records a first view; its small secondary action dismisses or restores that post. Search interests are at most ten recent terms in the user's session, not enrolment records. Existing accepted BuddyApplication records supply activity-category interest; pending/declined applications do not. Acceptance is evidence of joining, not proof of attendance. Blocking excludes the other person's posts and member-search results.

## Ranking

Existing title, description, skills, host major, categories, dates and accepted membership records are reused. Course codes tolerate spaces and hyphens (MA1201 matches MA 1201). Course names use ordinary text search. A small optional major filter shows related members within the existing Buddy page and filters hosts' posts. Existing apply → host approval → accepted-member contact rules are unchanged.

Available weights are normalized: authorized course content 30, accepted participation category 30, optional major 20, authorized timetable fit 15, freshness 5; recent explicit search interests add a lighter 10. Missing signals remove their weight instead of contributing zeros. A view subtracts .12, own/already applied posts .25 and dismissal 2. Open posts precede full posts. Every fifth result can introduce an unseen, non-dismissed open activity outside existing categories. Explicit search/type/date filters are applied first; exploration never escapes them. Users may choose activity-time ordering.

Time fit requires separate timetable authorization and an activity end time. Overlaps use half-open intervals, so touching endpoints do not conflict. Unknown end time does not imply availability. No timetable is displayed or returned to templates.

## Future integrations (phase 2 reserved only)

`market/university.py` defines independent IdentityProvider and CourseDataProvider contracts. AcademicContext distinguishes courses_authorized from timetable_authorized. The only current provider returns an empty, unauthorized context. There are no SSO routes, login mockups, school URLs, password inputs or background network requests.

After institutional approval, an identity adapter must validate the official assertion, bind its stable subject securely, then map only released attributes to the optional profile fields. Do not infer enrolment or academic attributes from mailbox verification. Missing attributes stay optional; users can continue editing self-reported fields. Set university_verified_at only after real validated identity verification. Do not expose an endpoint that accepts a client-supplied identity object or verification timestamp.

A separately authorized course adapter may return current-term Course(code, name, term) records and private, dated ClassMeeting intervals. Expand approved weekly patterns into timezone-aware occurrences before returning the context; honor consent, revocation and scope independently of SSO. Store/import nothing until the real provider's contract, retention and permissions are approved. No additional database tables for course management are introduced now.

## Local validation and rollout

Run `python manage.py makemigrations --check --dry-run` and `python manage.py test market --noinput` in the existing environment. Migration checks run against a temporary test database, including migration from 0006 with old profile content and mailbox verification preserved. Apply the additive migration to a backed-up target database only as part of an explicitly approved backend rollout. This task does not deploy Django or modify Render data.

The separate static showcase synchronizes the optional fields, major/course search and lightweight ordering as a tab-local demonstration. Its member majors/course associations are clearly synthetic. Its accepted study-activity seed comes from the existing joined sample activity, not a real user's history. It does not share a database or enforce real authentication/privacy. UI demo code is in `output/student_preview.py` and `output/design-preview/student-demo.js`; the authoritative production ranker is `market/recommendations.py`.
