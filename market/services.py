import hashlib, secrets, math, json
from datetime import timedelta
from decimal import Decimal
from functools import wraps
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import *

RULES = 'HKD; ceil(hours/24); offline payment; no escrow; bilateral handover and return confirmation. Cancellation before handover releases the reservation. Damage/overdue disputes require evidence and mutual agreement; no automatic fees.'
def member(view):
    @login_required
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not hasattr(request.user,'profile') or not request.user.profile.verified or request.user.profile.restricted:
            raise PermissionDenied('School email verification required / 須驗證學校郵箱')
        try: valid_email(request.user.email)
        except ValidationError: raise PermissionDenied('School email domain no longer allowed / 郵箱範圍不符')
        return view(request,*args,**kwargs)
    return wrapped

# ALLOWED_EMAIL_DOMAINS keeps working; enabling a University in admin adds its domains without a redeploy.
def allowed_domains():
    domains=set(settings.ALLOWED_EMAIL_DOMAINS)
    for school in University.objects.filter(enabled=True).only('email_domains'): domains.update(school.domains)
    return domains
def school_for(email):
    domain=email.rsplit('@',1)[-1].lower()
    return next((u for u in University.objects.filter(email_domains__icontains=domain) if domain in u.domains),None)

def valid_email(email):
    from django.core.validators import validate_email
    email = email.strip().lower()
    validate_email(email)
    if email.rsplit('@',1)[-1] not in allowed_domains():
        raise ValidationError('Only approved school email domains / 僅接受指定學校郵箱')
    return email

@transaction.atomic
def throttle(key,limit,seconds):
    now=timezone.now()
    key=hashlib.sha256(key.encode()).hexdigest()
    b,_=RateBucket.objects.select_for_update().get_or_create(key=key,defaults={'expires':now+timedelta(seconds=seconds)})
    if b.expires <= now: b.count=0; b.expires=now+timedelta(seconds=seconds)
    if b.count >= limit: raise ValidationError('Too many requests. Try later / 請稍後再試')
    b.count+=1; b.save()

def send_login(email,ip,origin):
    # Only trust the proxy's client-IP header when the app is reachable solely through that proxy.
    throttle('ip:'+ip,20,3600)
    email=valid_email(email)
    throttle('minute:'+email,1,60)
    throttle('email:'+email,5,3600)
    raw=secrets.token_urlsafe(32)
    token=LoginToken.objects.create(email=email,digest=hashlib.sha256(raw.encode()).hexdigest(),expires=timezone.now()+timedelta(minutes=15))
    url=origin+'/verify/'+raw+'/'
    try:
        send_mail('Box Box Share · 學校郵箱登入 / Sign in',f'登入連結 / Sign-in link (15 minutes, single use):\n{url}\n\n由 Box Box 營運，並非 CityUHK 官方平台。We never ask for your school password.',settings.DEFAULT_FROM_EMAIL,[email],fail_silently=False)
    except Exception:
        token.delete()
        raise ValidationError('Email service unavailable / 郵件服務暫時無法使用')

@transaction.atomic
def consume_token(raw):
    token=LoginToken.objects.select_for_update().filter(digest=hashlib.sha256(raw.encode()).hexdigest(),used=False,expires__gt=timezone.now()).first()
    if not token: raise ValidationError('Expired or used link / 連結過期或已使用')
    valid_email(token.email)
    user,_=User.objects.get_or_create(username=token.email,defaults={'email':token.email})
    p,_=Profile.objects.get_or_create(user=user)
    if p.restricted or not user.is_active: raise PermissionDenied()
    user.set_unusable_password(); user.save()
    p.verified=True
    if not p.university_id: p.university=school_for(token.email)
    p.save()
    token.used=True; token.save()
    return user

def clean_image(upload):
    if not upload: return None
    if upload.size>5*1024*1024: raise ValidationError('Max 5 MB / 圖片上限 5 MB')
    if upload.content_type not in ('image/jpeg','image/png','image/webp'): raise ValidationError('JPEG, PNG or WebP only / 僅接受 JPEG、PNG、WebP')
    try:
        with Image.open(upload) as im:
            if im.format not in ('JPEG','PNG','WEBP') or im.width*im.height>20_000_000: raise ValidationError('Invalid image / 圖片無效或過大')
            im.load(); im=im.convert('RGB'); im.thumbnail((1800,1800))
            out=BytesIO(); im.save(out,'JPEG',quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError): raise ValidationError('Invalid image / 圖片無效')
    # Re-encoding discards EXIF/location metadata and embedded payloads.
    return ContentFile(out.getvalue(),name=secrets.token_hex(16)+'.jpg')

def interval(start,end):
    if not start or not end or end<=start: raise ValidationError('End must be after start / 結束時間須晚於開始時間')
    return math.ceil((end-start).total_seconds()/86400)

def availability(item,start,end,exclude=None):
    days=interval(start,end)
    if item.status!='listed' or start<item.available_start or end>item.available_end or days>item.max_days:
        raise ValidationError('Outside availability / 超出可借日期或最長期限')
    if Order.objects.filter(item=item,status__in=Order.LOCKED,start__lt=end,end__gt=start).exclude(pk=exclude).exists():
        raise ValidationError('Reservation overlaps / 與已接受預約重疊')
    return days

def notify(user,text,url): Notification.objects.create(user=user,text=text,url=url)
# Busy group chats: one unread notification per conversation is enough.
def notify_once(user,text,url):
    if not Notification.objects.filter(user=user,url=url,read=False).exists(): notify(user,text,url)
def event(order,actor,action,data=None):
    Audit.objects.create(order=order,actor=actor,action=action,data=data or {})
    other=order.borrower if actor.pk==order.item.owner_id else order.item.owner
    notify(other,action,f'/orders/{order.pk}/')

def item_terms(item):
    return {'title':item.title,'daily':str(item.daily),'deposit':str(item.deposit),'condition':item.condition,'location':item.location,'rules':RULES,'max_days':item.max_days}
def terms_fingerprint(item): return hashlib.sha256(json.dumps(item_terms(item),sort_keys=True).encode()).hexdigest()

@transaction.atomic
def apply(item_id,user,start,end,expected=None):
    item=Item.objects.select_for_update().get(pk=item_id)
    if item.owner.profile.restricted or not item.owner.is_active: raise ValidationError('Lender unavailable / 物主帳號受限')
    if not user.profile.verified or user.profile.restricted: raise PermissionDenied()
    valid_email(user.email)
    if item.owner_id==user.pk: raise ValidationError('Cannot borrow your own item / 不可申請自己的物品')
    if start<timezone.now(): raise ValidationError('Start must be in the future / 開始時間須在未來')
    days=availability(item,start,end)
    if expected and expected['fingerprint']!=terms_fingerprint(item): raise ValidationError('Listing terms changed. Check the new quote / 物品價格或條款已更改，請重新確認費用')
    o=Order.objects.create(item=item,borrower=user,start=start,end=end,rent=item.daily*days,deposit=item.deposit,snapshot={**item_terms(item),'days':days})
    Thread.objects.create(order=o,first=user,second=item.owner)
    event(o,user,'申請借用 / Application submitted')
    return o

@transaction.atomic
def act(order_id,user,action,new_end=None,photo=None):
    # Global lock order: item, then order. Shared by accept, cancel and extensions.
    item_id=Order.objects.values_list('item_id',flat=True).get(pk=order_id)
    item=Item.objects.select_for_update().get(pk=item_id)
    o=Order.objects.select_for_update().get(pk=order_id)
    if user.pk not in (o.borrower_id,item.owner_id): raise PermissionDenied()
    owner=user.pk==item.owner_id
    side='owner' if owner else 'borrower'
    data={}
    if action=='accept':
        if not owner or o.status!='pending': raise ValidationError('Invalid action / 操作不適用')
        if o.start<timezone.now(): raise ValidationError('Application start has passed / 開始時間已過')
        availability(item,o.start,o.end,exclude=o.pk); o.status='accepted'
    elif action=='cancel':
        if o.status not in ('pending','accepted') or o.hand_owner or o.hand_borrower: raise ValidationError('After handover starts, open a dispute / 交接開始後請提出糾紛')
        o.status='cancelled'
    elif action=='handover':
        if o.status!='accepted': raise ValidationError('Accept first / 請先接受申請')
        setattr(o,'hand_'+side,True)
        if o.hand_owner and o.hand_borrower: o.status='active'
    elif action=='return':
        if o.status not in ('active','return_pending','disputed'): raise ValidationError('Invalid return / 歸還狀態不適用')
        setattr(o,'return_'+side,True)
        disputed=o.status=='disputed'
        if not disputed: o.status='return_pending'
        if o.return_owner and o.return_borrower:
            if not disputed: o.status='completed'
            if not o.actual_return: o.actual_return=timezone.now()
    elif action in ('rent','deposit','refund'):
        if o.status not in ('accepted','active','return_pending','completed','disputed'): raise ValidationError('Invalid payment confirmation / 狀態不適用')
        setattr(o,action+'_'+side,True)
    elif action=='extend':
        if owner or o.status not in ('accepted','active') or not new_end or new_end<=o.end: raise ValidationError('Invalid extension / 延期不適用')
        if new_end>item.available_end or interval(o.start,new_end)>o.snapshot['max_days']: raise ValidationError('Outside availability / 超出期限')
        o.extension_end=new_end; data={'requested_end':new_end.isoformat()}
    elif action=='approve_extension':
        if not owner or o.status not in ('accepted','active') or not o.extension_end: raise ValidationError('No extension request / 沒有待審延期')
        availability(item,o.start,o.extension_end,exclude=o.pk)
        data={'old_end':o.end.isoformat(),'new_end':o.extension_end.isoformat(),'old_rent':str(o.rent)}
        o.end=o.extension_end; o.extension_end=None
        o.rent=Decimal(o.snapshot['daily'])*interval(o.start,o.end)
    elif action=='reject_extension':
        if not owner or not o.extension_end: raise ValidationError('No extension request / 沒有待審延期')
        o.extension_end=None
    elif action=='dispute':
        if o.status not in Order.LOCKED: raise ValidationError('Invalid dispute / 狀態不適用')
        o.status='disputed'
    else: raise ValidationError('Unknown action / 操作無效')
    if photo:
        if action not in ('handover','return','dispute'): raise ValidationError('Photo not applicable / 此操作不接受照片')
        Evidence.objects.create(order=o,actor=user,image=photo,phase=action)
    o.save(); event(o,user,action,data)
    return o

@transaction.atomic
def resolve_dispute(order_id,admin_user,outcome):
    if not admin_user.is_staff or not admin_user.has_perm('market.change_order'): raise PermissionDenied()
    item_id=Order.objects.values_list('item_id',flat=True).get(pk=order_id)
    Item.objects.select_for_update().get(pk=item_id)
    o=Order.objects.select_for_update().get(pk=order_id)
    if o.status!='disputed': raise ValidationError('Not disputed / 並非糾紛訂單')
    if outcome=='completed':
        if not (o.return_owner and o.return_borrower): raise ValidationError('Both parties must confirm return / 須雙方確認歸還')
    elif outcome=='cancelled':
        if o.hand_owner or o.hand_borrower: raise ValidationError('Handover started; require return / 已開始交接，須先歸還')
    else: raise ValidationError('Invalid outcome')
    o.status=outcome; o.save()
    Audit.objects.create(order=o,actor=admin_user,action='管理員解決糾紛 / Moderator resolution',data={'outcome':outcome})
    for person in (o.item.owner,o.borrower): notify(person,'糾紛已處理 / Dispute resolved',f'/orders/{o.pk}/')

# Friends and crushes only between people who actually met here: a borrow that got past pending, or the same accepted buddy activity.
def met_ids(user):
    ids=set()
    for pair in Order.objects.exclude(status__in=['pending','cancelled']).filter(Q(borrower=user)|Q(item__owner=user)).values_list('item__owner_id','borrower_id'): ids.update(pair)
    buddies=BuddyJoin.objects.filter(status='accepted').filter(Q(user=user)|Q(buddy__owner=user)).values_list('buddy_id',flat=True)
    for pair in BuddyJoin.objects.filter(status='accepted',buddy_id__in=list(buddies)).values_list('buddy__owner_id','user_id'): ids.update(pair)
    ids.discard(user.pk)
    return ids
def blocked(a,b): return Block.objects.filter(Q(blocker=a,blocked=b)|Q(blocker=b,blocked=a)).exists()
def mutual(a,b,kind): return Connection.objects.filter(Q(sender=a,recipient=b)|Q(sender=b,recipient=a),kind=kind).count()==2
def direct_thread(a,b):
    first,second=sorted((a,b),key=lambda u:u.pk)
    return Thread.objects.get_or_create(first=first,second=second,item=None,order=None,buddy=None)[0]
def in_thread(thread,user):
    if thread.team_id: return TeamMember.objects.filter(team_id=thread.team_id,user_id=user.pk).exists()
    return user.pk in (thread.first_id,thread.second_id)
def can_message(thread,user):
    if thread.team_id: return thread.team.status!='disbanded' and in_thread(thread,user)
    other=thread.second if thread.first_id==user.pk else thread.first
    if thread.order_id: return True
    if blocked(user,other) or other.profile.restricted: return False
    # Buddy chats close once the joiner leaves or the host declines; the joiner is always `first`.
    if thread.buddy_id: return BuddyJoin.objects.filter(buddy_id=thread.buddy_id,user_id=thread.first_id).exclude(status='declined').exists()
    return bool(thread.item_id) or mutual(user,other,'friend') or mutual(user,other,'crush')

@transaction.atomic
def connect(sender,recipient,kind):
    # Lock both profiles in a fixed order so two simultaneous requests still see each other.
    profiles={p.user_id:p for p in Profile.objects.select_for_update().filter(user__in=[sender,recipient]).order_by('pk')}
    mine,theirs=profiles.get(sender.pk),profiles.get(recipient.pk)
    if kind not in ('friend','crush') or sender.pk==recipient.pk or not theirs or theirs.restricted or not recipient.is_active: raise ValidationError('Invalid request / 請求無效')
    if blocked(sender,recipient): raise ValidationError('Unavailable / 無法連結')
    if recipient.pk not in met_ids(sender): raise ValidationError('Meet through a borrow or buddy activity first / 先透過借物或搭子活動認識對方')
    if kind=='friend' and not (mine.social and theirs.social): raise ValidationError('Both people need to be open to new friends / 雙方須開放交友')
    if kind=='crush' and not mine.dating: raise ValidationError('Turn on dating in your profile first / 請先在個人資料開放心動配對')
    throttle('connect:'+str(sender.pk),30,86400)
    _,created=Connection.objects.get_or_create(sender=sender,recipient=recipient,kind=kind)
    matched=Connection.objects.filter(sender=recipient,recipient=sender,kind=kind).exists() and (kind=='friend' or theirs.dating)
    if created and matched:
        direct_thread(sender,recipient)
        text='你們互相心動了 / It’s a match' if kind=='crush' else '你們已成為好友 / You are now friends'
        notify(sender,text,f'/people/{recipient.pk}/'); notify(recipient,text,f'/people/{sender.pk}/')
    elif created and kind=='friend': notify(recipient,'有人想加你為好友 / New friend request','/friends/')
    return matched

def disconnect(user,other,kind):
    # Unfriending or declining a request clears both sides; withdrawing a crush only removes your own.
    rows=Connection.objects.filter(sender=user,recipient=other,kind=kind)
    if kind=='friend': rows=Connection.objects.filter(Q(sender=user,recipient=other)|Q(sender=other,recipient=user),kind='friend')
    rows.delete()

@transaction.atomic
def block(user,other):
    if user.pk==other.pk: raise ValidationError('Invalid request / 請求無效')
    Block.objects.get_or_create(blocker=user,blocked=other)
    Connection.objects.filter(Q(sender=user,recipient=other)|Q(sender=other,recipient=user)).delete()
    BuddyJoin.objects.filter(Q(user=user,buddy__owner=other)|Q(user=other,buddy__owner=user)).update(status='declined')
    # Existing teammates stay (the leader can remove them); pending applications between the two are turned down.
    TeamApplication.objects.filter(Q(user=user,team__leader=other)|Q(user=other,team__leader=user),status='pending').update(status='rejected',decided=timezone.now())

@transaction.atomic
def join_buddy(buddy_id,user,text):
    b=Buddy.objects.select_for_update().select_related('owner__profile').get(pk=buddy_id)
    if b.owner_id==user.pk or not b.active or b.when<=timezone.now(): raise ValidationError('Not open for joining / 活動不開放報名')
    if b.owner.profile.restricted or blocked(user,b.owner): raise ValidationError('Unavailable / 無法報名')
    if len(text)>300: raise ValidationError('Up to 300 characters / 留言上限 300 字')
    if BuddyJoin.objects.filter(buddy=b,user=user).exists(): raise ValidationError('Already asked to join / 已報名')
    throttle('join:'+str(user.pk),20,86400)
    j=BuddyJoin.objects.create(buddy=b,user=user,text=text)
    thread,_=Thread.objects.get_or_create(buddy=b,first=user,second=b.owner,item=None,order=None)
    if text: Message.objects.create(thread=thread,sender=user,text=text)
    notify(b.owner,'有人想做你的搭子 / New buddy request',f'/buddies/{b.pk}/')
    return j

@transaction.atomic
def answer_join(join_id,owner,accept):
    buddy_id=BuddyJoin.objects.values_list('buddy_id',flat=True).get(pk=join_id)
    b=Buddy.objects.select_for_update().get(pk=buddy_id)
    j=BuddyJoin.objects.select_for_update().get(pk=join_id)
    if b.owner_id!=owner.pk: raise PermissionDenied()
    if j.status!='pending': raise ValidationError('Already answered / 已處理')
    if accept and b.joins.filter(status='accepted').count()>=b.spots: raise ValidationError('No spots left / 名額已滿')
    j.status='accepted' if accept else 'declined'; j.save()
    notify(j.user,'搭子報名已獲接受 / You’re in' if accept else '搭子報名未獲接受 / Buddy request declined',f'/buddies/{b.pk}/')
    return j

def client_ip(request):
    return request.META.get(settings.CLIENT_IP_HEADER,request.META.get('REMOTE_ADDR','unknown')) if settings.TRUST_PROXY_IP else request.META.get('REMOTE_ADDR','unknown')
