# Buddy opt-in group chat

Implemented locally without replacing pairwise Thread/Message, Buddy approval, item sharing, or existing authentication. No school integration or realtime infrastructure is introduced.

## Rules

- Only the recruitment owner may create its group, after at least one accepted application. A OneToOne constraint and post-row locking ensure one group per post even under simultaneous requests. Repeat creation opens the same group without resetting history or duplicating invitations.
- The host joins at creation. Accepted applicants receive an in-app invitation and choose to join; subsequent approvals give the same join eligibility. Pending, declined, withdrawn and removed applicants cannot join. Knowing a group URL is insufficient.
- Joining snapshots the group's highest existing message ID while holding the same post lock used by sending and Buddy withdrawal/removal. Only messages above that boundary can be read or reported. Repeated join while active preserves the boundary. Rejoining after leaving records a new boundary and hides all earlier messages, including the member's own earlier messages.
- Leaving a group leaves Buddy membership unchanged. Withdrawing from Buddy or host removal sets group membership inactive in the same transaction. Every read/write rechecks current approval rather than relying on a stale active-membership row. Closing recruitment or passing the activity date leaves existing group chat usable.
- The host retains its membership and management link. Host removal of a participant uses the existing Buddy removal confirmation, revoking team and group membership together. There is no new parallel team-management system.
- Group messages never unlock private contact details. Pairwise messaging/contact policies are unchanged. Mutual user-block edges hide the corresponding peer messages; blocking the host prevents joining/access to that host's group. Other members can continue using their group.
- Reports target specific visible group messages. Current membership and current history boundary are required; ordinary members cannot report an unknown pre-join message by guessing its ID. Moderator read-only target pages preserve the reported content. No group-report or membership controls are publicly writable.

## Minimal additions

Migration 0008 adds BuddyGroup, BuddyGroupMember and BuddyGroupMessage and extends the Report kind choices. Old profiles, applications, private messages, items and orders are not rewritten. Group messages store their sender separately from the reusable membership row, so a rejoin cannot alter old authorship.

Services are in market/groups.py. The post → group lock order serializes create/join/leave/send against the existing Buddy application decisions. Existing in-app Notification and shared message throttling are reused. Three new routes: POST /buddy/<post>/group/, GET/POST /messages/groups/<group>/, and the existing report route with kind=group_message. The existing Buddy and inbox pages gain small group entry sections; one group conversation template is added.

The group page includes the recruitment context, members, a report link per visible message, a leave confirmation, and explicit manual refresh. Reads show the most recent 300 messages within the current join window. No unread counter, realtime status, or contact-unlock behavior is fabricated.

## Preview and testing

- Real Django preview: http://127.0.0.1:8014/ with output.group_review_settings, using a new synthetic-only output/group-review/preview.sqlite3 and local-file mail. Original data.sqlite3 and online databases are untouched.
- Static synthetic demo: http://127.0.0.1:8012/hans/buddy/1/ demonstrates host creation. /hans/buddy/2/ demonstrates an accepted member choosing to join a pre-existing sample group. /hans/buddy/3/ remains pending and has no join action. New group routes use the existing Messages layout. All state stays in the tab; simulation tools never contact anyone.
- Run: python manage.py test market --noinput (use an isolated SQLITE_TEST_PATH); python manage.py makemigrations --check --dry-run. Apply 0008 to a backed-up real target only in an authorized backend deployment.

No Render deployment, Sites publication or Git push is part of this local implementation. The hosted showcase remains on its previously published version until a separate publication step.

The subsequent local interaction/layout pass compacts group entry and conversation controls, groups Profile fields, and fixes mobile More navigation. It preserves the rules above. Final screenshots and validation: [experience review](output/experience-review/design-qa.md).
