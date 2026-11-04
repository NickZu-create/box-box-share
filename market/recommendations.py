"""Small deterministic Buddy ranker. Search interest is never enrolment evidence."""
import math
import re
import unicodedata
from collections import Counter
from datetime import timedelta
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import BuddyApplication, BuddyFeedback
from .university import AcademicContext


def normalized(text):
    return re.sub(r'[^\w\u3400-\u9fff]+', '', unicodedata.normalize('NFKC', text or '').casefold())


def contains(text, term):
    term = normalized(term)
    return bool(term) and term in normalized(text)


def post_text(post):
    return ' '.join([post.title, post.description, post.skills])


def course_query(query):
    match = re.fullmatch(r'([a-zA-Z]{2,5})[\s-]*(\d{4}[a-zA-Z]?)', query)
    return re.escape(match[1]) + r'[\s-]*' + re.escape(match[2]) if match else None


def remember_search(request, query):
    if not request.user.is_authenticated or not query:
        return
    history = request.session.get('buddy_searches', [])
    query = query[:100]
    request.session['buddy_searches'] = [query] + [s for s in history if s != query][:9]


def user_signals(user):
    if not user.is_authenticated:
        return {}, Counter(), set()
    feedback = dict(BuddyFeedback.objects.filter(user=user).values_list('post_id','dismissed'))
    # Accepted participation, not pending requests or inferred attendance.
    kinds = Counter(interest_group(kind) for kind in BuddyApplication.objects.filter(user=user,status='accepted')
                    .annotate(finish_at=Coalesce('post__ends','post__starts'))
                    .filter(finish_at__gte=timezone.now()-timedelta(days=180))
                    .values_list('post__kind',flat=True))
    joined = set(BuddyApplication.objects.filter(user=user,status__in=['pending','accepted']).values_list('post_id',flat=True))
    return feedback, kinds, joined


def interest_group(kind):
    return {'study':'learning','course':'learning','meal':'social','event':'social'}.get(kind,kind)


def rank_posts(posts, user, searches=(), academic=None, now=None):
    """Missing signals remove their weight. No-profile users keep useful defaults.

    Weights: courses 30, accepted interests 30, major 20, timetable 15,
    freshness 5; explicit recent search interests 10. Availability is never
    inferred from missing meetings/consent. Every fifth result explores a less
    familiar, unseen open post; exact search filters are applied before ranking.
    """
    posts = list(posts)
    if not posts:
        return posts
    now = now or timezone.now()
    academic = academic or AcademicContext()
    feedback, kinds, joined = user_signals(user)
    profile = getattr(user,'profile',None) if user.is_authenticated else None
    major = getattr(profile,'major','')
    searches = [s for s in searches if normalized(s)][:10]
    courses = academic.courses if academic.courses_authorized else ()
    meetings = academic.meetings if academic.timetable_authorized else ()
    scored = []
    for post in posts:
        text = post_text(post)
        signals = [(5, math.exp(-max(0,(now-post.created).total_seconds())/(30*86400)))]
        if courses:
            signals.append((30,float(any(contains(text,c.code) or contains(text,c.name) for c in courses))))
        if kinds:
            signals.append((30,kinds[interest_group(post.kind)]/max(kinds.values())))
        if normalized(major):
            signals.append((20,float(contains(text,major) or normalized(post.owner.profile.major)==normalized(major))))
        if searches:
            signals.append((10,sum(contains(text,s) or contains(post.owner.profile.major,s) for s in searches)/len(searches)))
        if academic.timetable_authorized and post.ends:
            conflicts = any(m.required and post.starts < m.ends and post.ends > m.starts for m in meetings)
            signals.append((15,0. if conflicts else 1.))
        score = sum(w*v for w,v in signals)/sum(w for w,_ in signals)
        if post.pk in feedback: score -= .12
        if post.pk in joined or (user.is_authenticated and post.owner_id==user.pk): score -= .25
        if feedback.get(post.pk): score -= 2.
        state = post.state(post.joined_count)
        scored.append((state!='open',bool(feedback.get(post.pk)), -score,post.starts,post.pk,post))
    scored.sort(key=lambda row:row[:-1])
    ordered = [row[-1] for row in scored]
    # Exploration never promotes full, dismissed or already joined posts.
    for index in range(4,len(ordered),5):
        candidates=[p for p in ordered[index:] if p.pk not in feedback and p.pk not in joined
                    and p.state(p.joined_count)=='open' and not kinds.get(interest_group(p.kind))]
        if candidates:
            chosen=max(candidates,key=lambda p:(p.created,-p.pk))
            ordered.remove(chosen);ordered.insert(index,chosen)
    return ordered
