"""Members' written content in the reader's language.

Traditional and Simplified Chinese are converted locally and never leave the server. Chinese and English go
through the model in ai.py. Public text is cached by a hash of its source, so editing a post simply asks again.
Private messages are never stored here: the reader's browser keeps them for the session.
"""
import hashlib, logging, re
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils.text import Truncator
from . import ai, groups, i18n, social
from .models import BuddyGroupMessage, BuddyPost, ContentTranslation, Item, LostFoundPost, Message, Offer, Review, Wanted
from .services import throttle

log = logging.getLogger(__name__)
BATCH = 12
MAX_CHARS = 6000
# A place code such as "AC1" or a number has nothing to translate into Chinese.
LATIN_WORD = re.compile(r'[A-Za-z]{3}')
FIELDS = {
    'item':(Item,('title','description','condition','location')),
    'wanted':(Wanted,('title','description','location')),
    'lostfound':(LostFoundPost,('title','description','location','color')),
    'buddy':(BuddyPost,('title','description','location','skills','languages')),
    'offer':(Offer,('text',)),
    'review':(Review,('text',)),
}
KINDS = {spec[0]:kind for kind,spec in FIELDS.items()}
# What the public Buddy list shows; the full post is for signed-in members.
BUDDY_PUBLIC_LENGTH = 120

def hash_of(text): return hashlib.sha256(text.encode()).hexdigest()
def model_language(lang): return 'en' if lang=='en' else 'zh'

def target_of(text,lang):
    """The language the model must produce, or None when local conversion is enough."""
    if not text: return None
    if lang=='en': return 'en' if i18n.CJK.search(text) else None
    return 'zh' if LATIN_WORD.search(text) and not i18n.CJK.search(text) else None

def converted(text,lang):
    if lang=='hans': return i18n.hans(text)
    return i18n.hant(text) if lang=='zh' else text

def finish(translated,lang): return i18n.hans(translated) if lang=='hans' else translated

def clip(text,limit): return Truncator(text).chars(limit) if limit else text

def remember(memo,texts,lang):
    missing={hash_of(text) for text in texts if target_of(text,lang)}-memo.keys()
    if not missing: return
    memo.update(dict.fromkeys(missing))
    memo.update(ContentTranslation.objects.filter(source_hash__in=missing,lang=model_language(lang)).values_list('source_hash','text'))

def prime(rows,lang,memo):
    # One query for a whole list. Rows may be objects or (object, extra) pairs.
    texts=[]
    for row in rows:
        obj=row[0] if isinstance(row,(tuple,list)) else row
        spec=FIELDS.get(KINDS.get(type(obj)))
        if spec: texts+=[getattr(obj,field) or '' for field in spec[1]]
    remember(memo,texts,lang)

def display(text,lang,memo):
    """(text to show, state): 'same', 'machine' (model translation) or 'pending' (the browser can ask for it)."""
    if target_of(text,lang) is None: return converted(text,lang),'same'
    key=hash_of(text)
    if key not in memo: remember(memo,[text],lang)
    if memo[key]: return finish(memo[key],lang),'machine'
    return text,('pending' if ai.enabled() else 'same')

def is_member(user):
    return user.is_authenticated and hasattr(user,'profile') and user.profile.verified and not user.profile.restricted

def _visible(owner,user,published=True):
    if user.is_authenticated and (user.pk==owner.pk or user.is_staff): return True
    return published and not owner.profile.restricted

def _public(kind,pk,field,user):
    # The same rules as the pages that show this text. Returns (text, length limit) or None.
    spec=FIELDS.get(kind)
    if not spec or field not in spec[1]: return None
    related={'offer':'wanted__owner__profile','review':'recipient__profile'}.get(kind,'owner__profile')
    obj=spec[0].objects.select_related(related).filter(pk=pk).first()
    if obj is None: return None
    limit=0
    if kind=='item': allowed=_visible(obj.owner,user,obj.status=='listed')
    elif kind=='wanted': allowed=_visible(obj.owner,user,obj.active)
    elif kind=='lostfound': allowed=_visible(obj.owner,user)
    elif kind=='offer': allowed=_visible(obj.wanted.owner,user,obj.wanted.active)
    elif kind=='review': allowed=not obj.recipient.profile.restricted
    else:
        allowed=_visible(obj.owner,user) and not social.is_blocked(user,obj.owner)
        if not is_member(user):
            if field=='skills': allowed=False
            if field=='description': limit=BUDDY_PUBLIC_LENGTH
    return (getattr(obj,field) or '',limit) if allowed else None

def _private(kind,pk,user):
    if not is_member(user): return None
    if kind=='message':
        message=Message.objects.select_related('thread').filter(pk=pk).first()
        return message.text if message and user.pk in (message.thread.first_id,message.thread.second_id) else None
    message=BuddyGroupMessage.objects.select_related('group__post__owner__profile').filter(pk=pk).first()
    if message is None: return None
    try: row=groups.membership(message.group,user)
    except PermissionDenied: return None
    return message.text if groups.visible_messages(message.group,user,row).filter(pk=pk).exists() else None

def source(ref,user):
    """Text only ever comes from a reference to content this reader may see, so this is no open translator."""
    parts=ref.split(':')
    if len(parts)==2 and parts[0] in ('message','groupmessage') and parts[1].isdigit():
        text=_private(parts[0],int(parts[1]),user)
        return None if text is None else (text,0,True)
    if len(parts)==3 and parts[1].isdigit():
        found=_public(parts[0],int(parts[1]),parts[2],user)
        return None if found is None else (found[0],found[1],False)
    return None

def _fit(rows):
    # At least one row per call, so a long post cannot block the queue.
    used=0
    for count,row in enumerate(rows):
        used+=len(row[1])
        if used>MAX_CHARS and count: return rows[:count],rows[count:]
    return rows,[]

def fulfil(refs,user,lang,client):
    results={}
    rows=[]
    for ref in dict.fromkeys(refs[:BATCH]):
        found=source(ref,user)
        if not found: continue
        text,limit,private=found
        if target_of(text,lang) is None: results[ref]=clip(converted(text,lang),limit)
        else: rows.append((ref,text,limit,private))
    memo={}
    remember(memo,[text for _,text,_,private in rows if not private],lang)
    missing=[]
    for row in rows:
        cached=None if row[3] else memo.get(hash_of(row[1]))
        if cached: results[row[0]]=clip(finish(cached,lang),row[2])
        else: missing.append(row)
    if not missing: return {'translations':results,'retry':[],'failed':False}
    if not ai.enabled(): return {'translations':results,'retry':[],'failed':True}
    throttle('translate:'+(f'user:{user.pk}' if user.is_authenticated else f'ip:{client}'),settings.TRANSLATE_HOURLY_LIMIT,3600)
    throttle('translate:everyone',settings.TRANSLATE_DAILY_LIMIT,86400)
    batch,later=_fit(missing)
    texts=list(dict.fromkeys(row[1] for row in batch))
    target=model_language(lang)
    try: done=dict(zip(texts,ai.translate_texts(texts,target)))
    except Exception as exc:
        log.warning('Translation failed: %r',exc)
        return {'translations':results,'retry':[],'failed':True}
    public={row[1] for row in batch if not row[3]}
    ContentTranslation.objects.bulk_create([ContentTranslation(source_hash=hash_of(text),lang=target,text=done[text]) for text in texts if text in public],ignore_conflicts=True)
    for ref,text,limit,_ in batch: results[ref]=clip(finish(done[text],lang),limit)
    return {'translations':results,'retry':[row[0] for row in later],'failed':False}
