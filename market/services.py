import hashlib, secrets, math, json, re
from datetime import timedelta
from decimal import Decimal
from functools import wraps
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
import hmac, logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db import transaction
from django.utils import timezone
from .models import *

log = logging.getLogger(__name__)
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

def send_email(subject,text,template,context,to):
    message=EmailMultiAlternatives(subject,text,settings.DEFAULT_FROM_EMAIL,[to])
    message.attach_alternative(render_to_string(template,context),'text/html')
    message.send(fail_silently=False)

def code_digest(email,code): return hmac.new(settings.SECRET_KEY.encode(),f'{email}:{code}'.encode(),hashlib.sha256).hexdigest()

def send_login(email,ip,origin,next_url='',lang=''):
    # Only trust the proxy's client-IP header when the app is reachable solely through that proxy.
    throttle('ip:'+ip,20,3600)
    email=valid_email(email)
    throttle('minute:'+email,1,60)
    throttle('email:'+email,5,3600)
    raw=secrets.token_urlsafe(32)
    code=f'{secrets.randbelow(1000000):06d}'
    token=LoginToken.objects.create(email=email,digest=hashlib.sha256(raw.encode()).hexdigest(),expires=timezone.now()+timedelta(minutes=15),next_url=next_url[:300],code_digest=code_digest(email,code))
    # The language travels with the link, because the mail app may open it in another browser.
    url=origin+'/verify/'+raw+'/'+(f'?lang={lang}' if lang else '')
    try:
        send_email(f'{code} 是你的 Box Box Share 驗證碼 / is your sign-in code',f'在登入頁輸入驗證碼 / Enter this code on the sign-in page: {code}\n\n在另一部裝置上，可用這條連結登入 / On another device, sign in with this link (15 minutes, single use):\n{url}\n\n由 Box Box 營運，並非 CityUHK 官方平台。We never ask for your school password.','market/email_login.html',{'url':url,'code':code},email)
    except Exception:
        token.delete()
        raise ValidationError('Email service unavailable / 郵件服務暫時無法使用')

@transaction.atomic
def consume_token(raw):
    token=LoginToken.objects.select_for_update().filter(digest=hashlib.sha256(raw.encode()).hexdigest(),used=False,expires__gt=timezone.now()).first()
    if not token: raise ValidationError('Expired or used link / 連結過期或已使用')
    return finish_login(token)

def consume_code(email,code,ip):
    # Returns (user, where to go next). Five wrong tries end this code; the attempt survives the error below.
    throttle('code:'+ip,30,300)
    email=email.strip().lower()
    code=''.join(code.split())
    with transaction.atomic():
        token=LoginToken.objects.select_for_update().filter(email=email,used=False,expires__gt=timezone.now()).exclude(code_digest='').order_by('-pk').first()
        if token and hmac.compare_digest(token.code_digest,code_digest(email,code)): return finish_login(token),token.next_url
        if token:
            token.code_attempts+=1
            if token.code_attempts>=5: token.used=True
            token.save(update_fields=['code_attempts','used'])
    raise ValidationError('驗證碼不正確或已過期 / Wrong or expired code')

def finish_login(token):
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

def notification_kind(url):
    if url.startswith('/orders/'): return 'request'
    if url.startswith(('/wanted/','/items/','/lost-found/')): return 'item'
    if url.startswith(('/buddy/','/messages/','/people/')): return 'friend'
    return 'system'
def notify(user,text,url,kind=None,detail=''): Notification.objects.create(user=user,text=text,url=url,kind=kind or notification_kind(url),detail=detail[:200])
# Order steps are recorded by key; people see a label in their language (old notifications hold the bare key).
ORDER_ACTIONS={'accept':'物主已接受申請 / Application accepted','cancel':'預約已取消 / Booking cancelled','decline':'物主未接受申請 / Application declined','handover':'已確認交接 / Handover confirmed','return':'已確認歸還 / Return confirmed','rent':'已確認租金 / Rent confirmed','deposit':'已確認押金 / Deposit confirmed','refund':'已確認退還押金 / Deposit refund confirmed','extend':'申請延期 / Extension requested','approve_extension':'已批准延期 / Extension approved','reject_extension':'已拒絕延期 / Extension declined','dispute':'已提出糾紛 / Dispute opened','buy':'有人購買了你的物品 / Your item was purchased'}
def event(order,actor,action,data=None,detail=''):
    Audit.objects.create(order=order,actor=actor,action=action,data=data or {})
    other=order.borrower if actor.pk==order.item.owner_id else order.item.owner
    # Once accepted, the borrower's next step is paying the lender directly.
    url=f'/orders/{order.pk}/pay/' if action=='accept' and order.total>0 else f'/orders/{order.pk}/'
    notify(other,ORDER_ACTIONS.get(action,action),url,'item' if order.is_purchase else 'request',detail)

def derive_title(description):
    # The first sentence of the description, so a listing only needs a price and a description.
    text=(description or '').strip()
    return re.split(r'[\n。！？.!?]',text,maxsplit=1)[0].strip()[:100] or text[:100]

def item_terms(item):
    return {'intent':item.intent,'title':item.title,'daily':str(item.daily),'deposit':str(item.deposit),'condition':item.condition,'location':item.location,'rules':RULES,'max_days':item.max_days}
def terms_fingerprint(item): return hashlib.sha256(json.dumps(item_terms(item),sort_keys=True).encode()).hexdigest()

@transaction.atomic
def apply(item_id,user,start,end,expected=None):
    item=Item.objects.select_for_update().get(pk=item_id)
    from .social import is_blocked
    if is_blocked(user,item.owner): raise PermissionDenied()
    if item.owner.profile.restricted or not item.owner.is_active: raise ValidationError('Lender unavailable / 物主帳號受限')
    if not user.profile.verified or user.profile.restricted: raise PermissionDenied()
    valid_email(user.email)
    if item.owner_id==user.pk: raise ValidationError('Cannot borrow your own item / 不可申請自己的物品')
    if item.is_sale: raise ValidationError('This item is for sale / 此物品只供出售')
    if start<timezone.now(): raise ValidationError('Start must be in the future / 開始時間須在未來')
    days=availability(item,start,end)
    if expected and expected['fingerprint']!=terms_fingerprint(item): raise ValidationError('Listing terms changed. Check the new quote / 物品價格或條款已更改，請重新確認費用')
    o=Order.objects.create(item=item,borrower=user,start=start,end=end,rent=item.daily*days,deposit=item.deposit,snapshot={**item_terms(item),'days':days})
    Thread.objects.create(order=o,first=user,second=item.owner)
    event(o,user,'申請借用 / Application submitted',detail=f'{user.profile.nickname} · {item.title}')
    return o

def email_owner_about_request(order,origin):
    # A reminder only: its failure never fails the request, and its links only open pages, because mail
    # scanners follow links. Capped so one applicant cannot flood an owner or use up the day's mail.
    owner=order.item.owner
    if not owner.profile.request_emails: return False
    try:
        throttle(f'request-email:{order.borrower_id}:{owner.pk}',1,600)
        throttle('request-email:everyone',80,86400)
    except ValidationError: return False
    title=' '.join((order.snapshot.get('title') or order.item.title).split())[:60]
    context={'applicant':order.borrower.profile.nickname,'title':title,'total':order.total,'start':timezone.localtime(order.start).strftime('%Y-%m-%d %H:%M'),'end':timezone.localtime(order.end).strftime('%Y-%m-%d %H:%M'),'order_url':f'{origin}/orders/{order.pk}/','chat_url':f'{origin}/messages/{order.thread.pk}/','profile_url':f'{origin}/profile/'}
    text=f"{context['applicant']} 想借用你的物品 / wants to borrow your item: {title}\n{context['start']} – {context['end']} · HK$ {order.total}\n\n查看並處理申請 / Review the request:\n{context['order_url']}\n\n與申請人聊天 / Chat with the applicant:\n{context['chat_url']}\n\n連結只會打開頁面，不會自動接受或拒絕。/ Links only open the page; nothing is accepted or declined automatically.\n不想再收到？在個人資料關閉 / Turn these emails off in your profile: {context['profile_url']}"
    try:
        send_email(f'Box Box Share · 新借用申請 / New borrow request: {title}',text,'market/email_request.html',context,owner.email)
        return True
    except Exception as exc:
        log.error('Borrow request email failed for order %s: %s',order.pk,type(exc).__name__)
        return False

@transaction.atomic
def buy(item_id,user):
    # The price is fixed, so a purchase needs no approval. The row lock lets only one buyer win.
    item=Item.objects.select_for_update().get(pk=item_id)
    from .social import is_blocked
    if is_blocked(user,item.owner): raise PermissionDenied()
    if item.owner.profile.restricted or not item.owner.is_active: raise ValidationError('Seller unavailable / 賣家帳號受限')
    if not user.profile.verified or user.profile.restricted: raise PermissionDenied()
    valid_email(user.email)
    if not item.is_sale: raise ValidationError('This item is not for sale / 此物品不設出售')
    if item.owner_id==user.pk: raise ValidationError('Cannot buy your own item / 不可購買自己的物品')
    if item.status!='listed': raise ValidationError('This item is no longer available / 此物品已不可購買')
    now=timezone.now()
    o=Order.objects.create(kind='purchase',item=item,borrower=user,start=now,end=now+timedelta(days=30),status='accepted',rent=item.daily,deposit=0,snapshot={**item_terms(item),'days':0})
    item.status='sold'; item.save(update_fields=['status'])
    Thread.objects.create(order=o,first=user,second=item.owner)
    event(o,user,'buy',detail=f'{user.profile.nickname} · {item.title}')
    return o

def release_sale(order,item):
    if order.is_purchase and item.status=='sold':
        item.status='listed'; item.save(update_fields=['status'])

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
    elif action=='decline':
        if not owner or o.status!='pending': raise ValidationError('Invalid action / 操作不適用')
        o.status='cancelled'
    elif action=='cancel':
        if o.status not in ('pending','accepted') or o.hand_owner or o.hand_borrower: raise ValidationError('After handover starts, open a dispute / 交接開始後請提出糾紛')
        o.status='cancelled'; release_sale(o,item)
    elif action=='handover':
        # A disputed sale can still record its handover, the step an administrator needs in order to close it.
        disputed_sale=o.is_purchase and o.status=='disputed'
        if o.status!='accepted' and not disputed_sale: raise ValidationError('Accept first / 請先接受申請')
        setattr(o,'hand_'+side,True)
        # A sale ends at handover; there is nothing to return.
        if o.hand_owner and o.hand_borrower and not disputed_sale: o.status='completed' if o.is_purchase else 'active'
    elif action=='return':
        if o.is_purchase: raise ValidationError('Nothing to return for a purchase / 購買訂單無需歸還')
        if o.status not in ('active','return_pending','disputed'): raise ValidationError('Invalid return / 歸還狀態不適用')
        setattr(o,'return_'+side,True)
        disputed=o.status=='disputed'
        if not disputed: o.status='return_pending'
        if o.return_owner and o.return_borrower:
            if not disputed: o.status='completed'
            if not o.actual_return: o.actual_return=timezone.now()
    elif action in ('rent','deposit','refund'):
        if o.is_purchase and action!='rent': raise ValidationError('No deposit on a purchase / 購買訂單沒有押金')
        if o.status not in ('accepted','active','return_pending','completed','disputed'): raise ValidationError('Invalid payment confirmation / 狀態不適用')
        setattr(o,action+'_'+side,True)
    elif action=='extend':
        if o.is_purchase or owner or o.status not in ('accepted','active') or not new_end or new_end<=o.end: raise ValidationError('Invalid extension / 延期不適用')
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
        if o.is_purchase:
            if not (o.hand_owner and o.hand_borrower): raise ValidationError('Both parties must confirm handover / 須雙方確認交接')
        elif not (o.return_owner and o.return_borrower): raise ValidationError('Both parties must confirm return / 須雙方確認歸還')
    elif outcome=='cancelled':
        if o.hand_owner or o.hand_borrower: raise ValidationError('Handover started; require return / 已開始交接，須先歸還')
    else: raise ValidationError('Invalid outcome')
    o.status=outcome; o.save()
    if outcome=='cancelled': release_sale(o,o.item)
    Audit.objects.create(order=o,actor=admin_user,action='管理員解決糾紛 / Moderator resolution',data={'outcome':outcome})
    for person in (o.item.owner,o.borrower): notify(person,'糾紛已處理 / Dispute resolved',f'/orders/{o.pk}/','system')


def client_ip(request):
    return request.META.get(settings.CLIENT_IP_HEADER,request.META.get('REMOTE_ADDR','unknown')) if settings.TRUST_PROXY_IP else request.META.get('REMOTE_ADDR','unknown')
