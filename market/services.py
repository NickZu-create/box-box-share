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

def valid_email(email):
    from django.core.validators import validate_email
    email = email.strip().lower()
    validate_email(email)
    if email.rsplit('@',1)[-1] not in settings.ALLOWED_EMAIL_DOMAINS:
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
    p.verified=True; p.save()
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


def client_ip(request):
    return request.META.get(settings.CLIENT_IP_HEADER,request.META.get('REMOTE_ADDR','unknown')) if settings.TRUST_PROXY_IP else request.META.get('REMOTE_ADDR','unknown')
