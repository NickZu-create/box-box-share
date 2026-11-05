import hashlib
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core import signing
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q, Avg, Count, F, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, time
from django.template.loader import render_to_string
from django.utils.html import format_html
from .templatetags.ui import chat_day
from django.views.decorators.http import require_GET, require_POST
from .models import *
from .forms import *
from .services import *
from .impact import impact_summary, METHOD_URL
from . import ai, social, i18n, recommendations, university, groups, payments, translate
from . import chatlines
from . import inbox as inbox_data

def feed_context(request,thread=None,group=None):
    # The Messages sidebar: one row per person, a filter, and one row for notifications.
    me=request.user
    tab=request.GET.get('tab')
    if tab not in inbox_data.FILTERS: tab='all'
    numbers=inbox_data.counts(me)
    person=(thread.second_id if thread.first_id==me.pk else thread.first_id) if thread else None
    return {'feed':inbox_data.tab_rows(inbox_data.feed_rows(me,request.lang),tab),'tab':tab,'tabs':inbox_data.tabs(request.lang,numbers,tab),'notes_row':inbox_data.notes_row(me,numbers) if tab=='all' else None,'current_thread':thread.pk if thread else None,'current_person':person,'current_group':group.pk if group else None}

def can_poll(user):
    if not user.is_authenticated or not hasattr(user,'profile') or not user.profile.verified or user.profile.restricted: return False
    try: valid_email(user.email)
    except ValidationError: return False
    return True

@require_GET
def notifications_poll(request):
    # 401 rather than a sign-in redirect: the page's script stops asking.
    if not can_poll(request.user): return JsonResponse({'error':'sign-in'},status=401)
    response=JsonResponse(inbox_data.poll(request.user,request.GET,request.lang))
    response['Cache-Control']='no-store'
    return response

@member
@require_GET
def inbox_feed(request):
    thread=group=None
    if request.GET.get('current','').isdigit(): thread=inbox_data.my_threads(request.user).filter(pk=int(request.GET['current'])).first()
    if request.GET.get('group','').isdigit(): group=BuddyGroup.objects.filter(pk=int(request.GET['group'])).first()
    response=render(request,'market/_message_feed.html',feed_context(request,thread,group))
    response['Cache-Control']='no-store'
    return response

@member
def notifications_page(request):
    me=request.user
    kind=request.POST.get('kind') if request.method=='POST' else request.GET.get('kind')
    if kind not in inbox_data.KINDS: kind=''
    rows=Notification.objects.filter(user=me,**({'kind':kind} if kind else {}))
    if request.method=='POST':
        rows.filter(read=False).update(read=True)
        return redirect(f'/notifications/?kind={kind}' if kind else '/notifications/')
    return render(request,'market/notifications.html',{'notes':rows.order_by('-created','-pk')[:inbox_data.FEED_NOTES],'kind':kind,'kinds':inbox_data.note_kinds(me,request.lang,kind),'has_unread':rows.filter(read=False).exists()})

@member
def friends_page(request):
    me=request.user
    friendships=Friendship.objects.filter(Q(sender=me)|Q(recipient=me)).select_related('sender__profile','recipient__profile').order_by('-created')
    friends=[(f,f.recipient if f.sender_id==me.pk else f.sender) for f in friendships if f.status=='accepted' and not social.is_blocked(f.sender,f.recipient)]
    return render(request,'market/friends.html',{'friends':friends,'blocked_users':User.objects.filter(pk__in=UserBlock.objects.filter(blocker=me).values('blocked_id')).select_related('profile'),'incoming':[f for f in friendships if f.status=='pending' and f.recipient_id==me.pk],'outgoing':[f for f in friendships if f.status=='pending' and f.sender_id==me.pk]})

@member
def notification_open(request,pk):
    note=get_object_or_404(Notification,pk=pk,user=request.user)
    if not note.read: Notification.objects.filter(pk=note.pk).update(read=True)
    # Older friend-request notes point at where that list used to be.
    if note.url=='/messages/#friends': return redirect('friends_page')
    return redirect(note.url if note.url.startswith('/') and not note.url.startswith('//') else '/messages/')

def newer_than(request):
    value=request.GET.get('after','')
    return int(value) if value.isdigit() else 0

def bubbles(request,rows,template,previous=None):
    # Rendered like the page itself, including a date line when the day turns over.
    parts=[]
    day=chat_day(previous.created) if previous else None
    for m in rows:
        if chat_day(m.created)!=day:
            day=chat_day(m.created)
            parts.append(format_html('<div class="day-sep"><span>{}</span></div>',day))
        parts.append(render_to_string(template,{'m':m},request=request))
    return ''.join(parts)

def recalled_lines(request,rows,template):
    # Messages recalled lately, so a page that is already open replaces them.
    since=timezone.now()-timedelta(minutes=15)
    return {str(m.pk):render_to_string(template,{'m':m},request=request) for m in rows.filter(recalled=True,recalled_at__gte=since)}

@member
@require_GET
def thread_new(request,pk):
    thread=get_object_or_404(Thread,pk=pk)
    me=request.user
    if me.pk not in (thread.first_id,thread.second_id): raise PermissionDenied()
    threads=chatlines.conversation_threads(me,thread.second_id if thread.first_id==me.pk else thread.first_id)
    visible=Message.objects.filter(thread__in=threads).select_related('sender__profile','reply_to__sender__profile')
    after=newer_than(request)
    rows=list(visible.filter(pk__gt=after).order_by('pk')[:100])
    inbox_data.mark_conversation_read(threads,me)
    response=JsonResponse({'html':bubbles(request,rows,'market/_bubble.html',visible.filter(pk=after).first()),'last':rows[-1].pk if rows else after,'recalled':recalled_lines(request,visible.filter(pk__lte=after),'market/_bubble.html'),'unread':inbox_data.counts(me)})
    response['Cache-Control']='no-store'
    return response

@member
@require_GET
def group_new(request,pk):
    group=get_object_or_404(BuddyGroup.objects.select_related('post__owner__profile'),pk=pk)
    row=groups.membership(group,request.user)
    visible=groups.visible_messages(group,request.user,row).select_related('reply_to__sender__profile')
    after=newer_than(request)
    rows=list(visible.filter(pk__gt=after).order_by('pk')[:100])
    inbox_data.mark_group_read(group,request.user,row)
    response=JsonResponse({'html':bubbles(request,rows,'market/_group_bubble.html',visible.filter(pk=after).first()),'last':rows[-1].pk if rows else after,'recalled':recalled_lines(request,visible.filter(pk__lte=after),'market/_group_bubble.html'),'unread':inbox_data.counts(request.user)})
    response['Cache-Control']='no-store'
    return response

@member
@require_POST
def line_action(request,kind,pk):
    _,back=chatlines.find_line(kind,pk,request.user)
    try:
        if request.POST.get('action')!='recall': raise Http404()
        chatlines.recall(kind,pk,request.user)
    except ValidationError as exc: error(request,exc)
    return redirect(back)

@member
def line_forward(request,kind,pk):
    line,back=chatlines.find_line(kind,pk,request.user)
    if request.method=='POST':
        try: return redirect(chatlines.forward(kind,pk,request.user,request.POST.get('target','')))
        except ValidationError as exc:
            error(request,exc)
            return redirect(back)
    if line.recalled: raise Http404()
    return render(request,'market/forward.html',{'line':line,'back':back,'targets':inbox_data.forward_targets(request.user)})

def error(request,exc): messages.error(request,'; '.join(str(m) for m in exc.messages))
def safe_next(request,fallback='/'):
    target=request.POST.get('next') or request.GET.get('next') or ''
    return target if url_has_allowed_host_and_scheme(target,allowed_hosts={request.get_host()},require_https=request.is_secure()) else fallback
def home(request):
    tab=request.GET.get('tab','items'); q=request.GET.get('q','').strip(); category=request.GET.get('category','')
    wanted=tab=='wanted'
    rows=Wanted.objects.filter(active=True,owner__profile__restricted=False) if wanted else Item.objects.filter(status='listed',owner__profile__restricted=False)
    if q: rows=rows.filter(Q(title__icontains=q)|Q(description__icontains=q))
    if category: rows=rows.filter(category=category)
    intent=request.GET.get('intent','')
    if intent in (('borrow','buy') if wanted else ('rent','sale')): rows=rows.filter(intent=intent)
    else: intent=''
    maximum=request.GET.get('price','')
    if maximum:
        try:
            price=Decimal(maximum)
            if not price.is_finite() or price<0 or price>Decimal('9999999.99'): raise InvalidOperation
            rows=rows.filter(**{('budget__lte' if wanted else 'daily__lte'):price})
        except InvalidOperation: messages.error(request,'價格無效 / Invalid price'); rows=rows.none()
    dates=BookingForm(request.GET if request.GET.get('start') or request.GET.get('end') else None)
    if dates.is_bound:
        if dates.is_valid():
            start,end=dates.cleaned_data['start'],dates.cleaned_data['end']
            if wanted: rows=rows.filter(start__lt=end,end__gt=start)
            else:
                blocked=Order.objects.filter(status__in=Order.LOCKED,start__lt=end,end__gt=start).values('item_id')
                rows=rows.filter(available_start__lte=start,available_end__gte=end,max_days__gte=interval(start,end)).exclude(pk__in=blocked)
        else: rows=rows.none(); messages.error(request,'請輸入有效日期 / Enter valid dates')
    rows=rows.order_by('-created','-pk')
    has_filters=any(request.GET.get(key) for key in ('q','category','price','start','end','intent'))
    return render(request,'market/home.html',{'has_filters':has_filters,'rows':rows.select_related('owner__profile').prefetch_related('photos','owner__payment_codes')[:100] if not wanted else rows.select_related('owner__profile')[:100],'wanted':wanted,'intent':intent,'categories':CATEGORIES,'date_form':dates})

def start_session(request,user):
    login(request,user,backend='django.contrib.auth.backends.ModelBackend')
    request.session.set_expiry(settings.REMEMBER_DEVICE_SECONDS if request.POST.get('remember') else 0)

def signin(request):
    sent_to=''
    if request.method=='POST':
        try:
            send_login(request.POST.get('email',''),client_ip(request),request.build_absolute_uri('/').rstrip('/'),safe_next(request,''),request.lang)
            sent_to=request.POST.get('email','').strip().lower()
            messages.success(request,'驗證碼已發送，請查收。 / Code sent. Check your email.' if settings.MAIL_LIVE else '開發模式：登入郵件已寫入伺服器 dev-mail 目錄，未發送到學校郵箱。 / Development only: message saved to server dev-mail; not delivered.')
        except ValidationError as exc: error(request,exc)
    return render(request,'market/login.html',{'next':safe_next(request,''),'sent_to':sent_to})

@require_POST
def signin_code(request):
    email=request.POST.get('email','')
    try:
        user,target=consume_code(email,request.POST.get('code',''),client_ip(request))
        start_session(request,user)
        return redirect(target or 'home')
    except (ValidationError,PermissionDenied) as exc:
        if isinstance(exc,ValidationError): error(request,exc)
        else: messages.error(request,'此帳號無法登入 / This account cannot sign in')
    return render(request,'market/login.html',{'next':safe_next(request,''),'sent_to':email.strip().lower()})

def verify(request,raw):
    # Mail apps may open this in another browser, so bring the chosen language along.
    lang=request.GET.get('lang')
    if lang in i18n.CODES and lang!=request.lang:
        request.session['lang']=lang
        response=redirect(request.get_full_path())
        response.set_cookie(i18n.COOKIE,lang,max_age=31536000,samesite='Lax')
        return response
    # Already signed in as this person, the link only needs to take them on. A mail scanner is never signed in.
    if request.method=='GET' and request.user.is_authenticated:
        token=LoginToken.objects.filter(digest=hashlib.sha256(raw.encode()).hexdigest(),used=False,expires__gt=timezone.now(),email=request.user.email).first()
        if token:
            LoginToken.objects.filter(pk=token.pk).update(used=True)
            return redirect(token.next_url or 'home')
    if request.method=='POST':
        try:
            throttle('verify:'+client_ip(request),30,300)
            target=LoginToken.objects.filter(digest=hashlib.sha256(raw.encode()).hexdigest()).values_list('next_url',flat=True).first()
            user=consume_token(raw); start_session(request,user)
            return redirect(target or 'home')
        except ValidationError as exc: error(request,exc)
    return render(request,'market/verify.html')

@require_POST
def signout(request): logout(request); return redirect('home')
@require_POST
def language(request):
    # Back to the same page (query string and all); lang.js restores unsent form text and scroll position.
    lang=request.POST.get('lang')
    if lang not in i18n.CODES: lang='zh'
    request.session['lang']=lang
    response=redirect(safe_next(request))
    response.set_cookie(i18n.COOKIE,lang,max_age=365*86400,samesite='Lax',secure=request.is_secure(),httponly=True)
    return response

@require_POST
def translate_content(request):
    try: return JsonResponse(translate.fulfil(request.POST.getlist('ref'),request.user,request.lang,client_ip(request)))
    except ValidationError as exc: return JsonResponse({'error':'; '.join(exc.messages),'translations':{},'retry':[],'failed':True},status=429)

@member
def item_edit(request,pk=None):
    item=get_object_or_404(Item,pk=pk,owner=request.user) if pk else None
    form=ItemForm(request.POST or None,request.FILES or None,instance=item,initial={'intent':'sale'} if not item and request.GET.get('intent')=='sale' else None)
    context={'form':form,'kind':'item','item':item,'title':'發布／編輯物品 / List or edit an item','ai':ai.enabled() and not item,'ai_provider':settings.AI_PROVIDER_LABEL}
    if item and item.status=='sold':
        messages.error(request,'已售出的物品不能編輯 / A sold item cannot be edited')
        return redirect('item',pk=item.pk)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            if item:
                Item.objects.select_for_update().get(pk=item.pk)
                if Order.objects.filter(item=item,status__in=Order.LOCKED).filter(Q(start__lt=form.cleaned_data['available_start'])|Q(end__gt=form.cleaned_data['available_end'])).exists():
                    form.add_error(None,'保留已接受預約的可借日期 / Keep availability for accepted bookings')
                    return render(request,'market/publish.html',context)
            obj=form.save(commit=False); obj.owner=request.user; obj.save()
            for photo in form.cleaned_data.get('remove_photos',[]):
                storage,name=photo.image.storage,photo.image.name
                photo.delete()
                transaction.on_commit(lambda storage=storage,name=name: storage.delete(name))
            if form.cleaned_data['photo']: ItemPhoto.objects.create(item=obj,image=form.cleaned_data['photo'])
        return redirect('item',pk=obj.pk)
    return render(request,'market/publish.html',context)

@member
@require_POST
def item_ai_draft(request):
    if not ai.enabled(): raise Http404()
    try:
        photo=clean_image(request.FILES.get('photo'))
        if not photo: raise ValidationError('請先選擇照片 / Choose a photo first')
        throttle('ai:'+str(request.user.pk),20,86400)
        return JsonResponse({'draft':ai.draft_listing(photo)})
    except ValidationError as exc: return JsonResponse({'error':'; '.join(exc.messages)},status=400)

def item_detail(request,pk):
    item=get_object_or_404(Item.objects.select_related('owner__profile'),pk=pk)
    if (item.status!='listed' or item.owner.profile.restricted) and request.user.pk!=item.owner_id and not request.user.is_staff: raise Http404()
    form=BookingForm(request.POST or None)
    quote=None
    quote_token=None
    if request.method=='POST':
        if not request.user.is_authenticated: return redirect(f'/login/?next=/items/{item.pk}/')
        if not request.user.profile.verified or request.user.profile.restricted: raise PermissionDenied()
        if item.is_sale: return redirect('item',pk=item.pk)
        if form.is_valid():
            try:
                days=availability(item,form.cleaned_data['start'],form.cleaned_data['end'])
                quote={'days':days,'rent':item.daily*days,'deposit':item.deposit}
                payload={'item':item.pk,'start':form.cleaned_data['start'].isoformat(),'end':form.cleaned_data['end'].isoformat(),'fingerprint':terms_fingerprint(item)}
                quote_token=signing.dumps(payload,salt='booking-quote')
                if request.POST.get('action')=='apply':
                    try: expected=signing.loads(request.POST.get('quote_token',''),salt='booking-quote',max_age=900)
                    except signing.BadSignature: raise ValidationError('Check price again before applying / 請先重新計算費用')
                    if expected['item']!=item.pk or expected['start']!=payload['start'] or expected['end']!=payload['end']: raise ValidationError('Dates changed. Check price again / 日期已更改，請重新計算費用')
                    o=apply(item.pk,request.user,form.cleaned_data['start'],form.cleaned_data['end'],expected=expected); email_owner_about_request(o,request.build_absolute_uri('/').rstrip('/')); return redirect('order',pk=o.pk)
            except ValidationError as exc: form.add_error(None,exc)
    return render(request,'market/item.html',{'item':item,'form':form,'quote':quote,'quote_token':quote_token,'calendar':booking_calendar(item) if not item.is_sale else ''})

@member
def item_buy(request,pk):
    item=get_object_or_404(Item.objects.select_related('owner__profile'),pk=pk,intent='sale',status='listed',owner__profile__restricted=False)
    if item.owner_id==request.user.pk or social.is_blocked(request.user,item.owner): return redirect('item',pk=item.pk)
    if request.method=='POST':
        try:
            o=buy(item.pk,request.user)
            return redirect('order_payment',pk=o.pk) if o.total>0 else redirect('order',pk=o.pk)
        except ValidationError as exc: error(request,exc); return redirect('home')
    return render(request,'market/buy_confirm.html',{'item':item})

@member
def wanted_edit(request,pk=None):
    obj=get_object_or_404(Wanted,pk=pk,owner=request.user) if pk else None
    form=WantedForm(request.POST or None,instance=obj,initial={'intent':'buy'} if not obj and request.GET.get('intent')=='buy' else None)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False); obj.owner=request.user; obj.save(); return redirect('wanted',pk=obj.pk)
    return render(request,'market/publish.html',{'form':form,'kind':'wanted','item':obj,'title':'發布／編輯需求 / Post or edit a request'})

def wanted_detail(request,pk):
    obj=get_object_or_404(Wanted.objects.select_related('owner__profile'),pk=pk)
    if (not obj.active or obj.owner.profile.restricted) and obj.owner_id!=request.user.pk and not request.user.is_staff: raise Http404()
    items=Item.objects.filter(owner=request.user,status='listed') if request.user.is_authenticated else []
    if request.method=='POST':
        if not request.user.is_authenticated: return redirect('login')
        if not request.user.profile.verified or request.user.profile.restricted: raise PermissionDenied()
        selected=request.POST.get('item','')
        if not selected.isdigit(): raise Http404()
        item=get_object_or_404(Item,pk=selected,owner=request.user,status='listed')
        if obj.owner_id==request.user.pk or not obj.active or social.is_blocked(request.user,obj.owner): raise PermissionDenied()
        text=request.POST.get('text','').strip()
        if len(text)>1000: raise PermissionDenied()
        Offer.objects.create(wanted=obj,item=item,text=text)
        notify(obj.owner,'收到尋物回應 / New offer',f'/wanted/{obj.pk}/')
        return redirect('wanted',pk=pk)
    return render(request,'market/wanted.html',{'wanted':obj,'items':items})

@member
@require_POST
def wanted_contact(request,pk):
    obj=get_object_or_404(Wanted,pk=pk,active=True,owner__profile__restricted=False)
    if obj.owner_id==request.user.pk or social.is_blocked(request.user,obj.owner): raise PermissionDenied()
    thread,_=Thread.objects.get_or_create(wanted=obj,first=request.user,second=obj.owner,order=None,item=None,buddy=None,lostfound=None)
    return redirect('thread',pk=thread.pk)

@member
def dashboard(request):
    orders=Order.objects.filter(Q(borrower=request.user)|Q(item__owner=request.user)).select_related('item','borrower__profile','item__owner__profile').order_by('-created')
    # Buddy stays in its own section; it never mixes with lending and borrowing orders.
    posts=BuddyPost.objects.filter(owner=request.user).annotate(joined_count=Count('applications',filter=Q(applications__status='accepted')),pending_count=Count('applications',filter=Q(applications__status='pending'))).order_by('-created')
    applications=BuddyApplication.objects.filter(user=request.user).select_related('post').order_by('-created')
    return render(request,'market/dashboard.html',{'orders':orders,'items':Item.objects.filter(owner=request.user),'wanted_rows':Wanted.objects.filter(owner=request.user),
        'lostfound_posts':LostFoundPost.objects.filter(owner=request.user).order_by('-created'),'buddy_posts':[(p,p.state(p.joined_count)) for p in posts],'buddy_applications':[a for a in applications if a.status!='accepted'],'buddy_joined':[a for a in applications if a.status=='accepted']})

@member
def order_detail(request,pk):
    o=get_object_or_404(Order.objects.select_related('item__owner__profile','borrower__profile'),pk=pk)
    if request.user.pk not in (o.item.owner_id,o.borrower_id): raise PermissionDenied()
    if request.method=='POST':
        try:
            new_end=None
            if request.POST.get('action')=='extend':
                field=forms.DateTimeField(input_formats=['%Y-%m-%dT%H:%M'])
                new_end=field.clean(request.POST.get('new_end'))
            photo=clean_image(request.FILES.get('photo'))
            action=request.POST.get('action')
            # An owner cancelling a request they have not accepted is declining it.
            decided='accept' if action=='accept' else 'decline' if action=='decline' or (action=='cancel' and o.status=='pending' and request.user.pk==o.item.owner_id and not o.is_purchase) else None
            result=act(o.pk,request.user,action,new_end,photo)
            origin=request.build_absolute_uri('/').rstrip('/')
            if decided: email_order_result(o,decided=='accept',origin)
            for closed in result.closed_requests: email_order_result(closed,False,origin,taken=True)
            messages.success(request,'操作已記錄 / Confirmation recorded')
        except ValidationError as exc: error(request,exc)
        return redirect('order',pk=pk)
    # Seeing the order is seeing what its notifications were about.
    Notification.objects.filter(user=request.user,url__startswith=f'/orders/{pk}/',read=False).update(read=True)
    return render(request,'market/order.html',{'order':o,'owner':request.user.pk==o.item.owner_id,'reviewed':Review.objects.filter(order=o,author=request.user).exists(),'survey':o.surveys.first() if request.user.pk==o.borrower_id else None,'payable':o.status in payments.PAYABLE,'has_payment_codes':PaymentCode.objects.filter(owner_id=o.item.owner_id).exists(),'extension_rent':Decimal(o.snapshot['daily'])*interval(o.start,o.extension_end) if o.extension_end else None})

@member
def order_payment(request,pk):
    o=get_object_or_404(Order.objects.select_related('item__owner__profile','borrower__profile'),pk=pk)
    if request.user.pk not in (o.item.owner_id,o.borrower_id): raise PermissionDenied()
    if request.user.pk!=o.borrower_id or o.status not in payments.PAYABLE: return redirect('order',pk=pk)
    codes=payments.available_codes(o.item.owner)
    alipay=[codes[channel] for channel in ('alipay_cn','alipay_hk') if channel in codes]
    return render(request,'market/order_payment.html',{'order':o,'amount':str(o.total),'wechat':codes.get('wechat'),'alipay':alipay,'fps':codes.get('fps'),'currencies':payments.currencies_for(codes),**payments.confirmation_context(o)})

@member
def fx_rates(request):
    data=payments.hkd_rates()
    if not data: return JsonResponse({'error':'unavailable'},status=503)
    return JsonResponse(data)

@member
def payment_settings(request):
    if request.method=='POST':
        channel=request.POST.get('channel')
        if channel not in dict(PAYMENT_CHANNELS): raise Http404()
        try:
            if request.POST.get('action')=='remove':
                payments.remove_code(request.user,channel)
                messages.success(request,'已移除收款碼 / Payment code removed')
            else:
                image=clean_image(request.FILES.get('photo'))
                if not image: raise ValidationError('請先選擇圖片 / Choose an image first')
                payments.save_code(request.user,channel,image)
                messages.success(request,'已儲存收款碼 / Payment code saved')
        except ValidationError as exc: error(request,exc)
        return redirect('payment_settings')
    codes={code.channel:code for code in request.user.payment_codes.all()}
    return render(request,'market/payment_settings.html',{'rows':[{'channel':channel,'label':label,'code':codes.get(channel)} for channel,label in PAYMENT_CHANNELS]})

@member
@require_POST
def review(request,pk):
    o=get_object_or_404(Order.objects.select_related('item'),pk=pk)
    if request.user.pk not in (o.item.owner_id,o.borrower_id): raise PermissionDenied()
    try:
        with transaction.atomic():
            o=Order.objects.select_for_update().get(pk=pk)
            if o.status!='completed' or Review.objects.filter(order=o,author=request.user).exists(): raise ValidationError('Review only once after completion / 完成訂單後可評價一次')
            recipient=o.borrower if request.user.pk==o.item.owner_id else o.item.owner
            r=Review(order=o,author=request.user,recipient=recipient,rating=request.POST.get('rating'),text=request.POST.get('text',''))
            r.full_clean(); r.save(); notify(recipient,'收到新評價 / New review',f'/people/{recipient.pk}/','system')
    except ValidationError as exc: error(request,exc)
    return redirect('order',pk=pk)

@member
@require_POST
def survey(request,pk):
    o=get_object_or_404(Order,pk=pk)
    if request.user.pk!=o.borrower_id: raise PermissionDenied()
    try:
        with transaction.atomic():
            o=Order.objects.select_for_update().get(pk=pk)
            if o.status!='completed' or o.surveys.exists(): raise ValidationError('完成訂單後可回答一次 / Answer once after completion')
            s=Survey(order=o,answer=request.POST.get('answer','')); s.full_clean(); s.save()
        messages.success(request,'多謝回答 / Thanks for answering')
    except ValidationError as exc: error(request,exc)
    return redirect('order',pk=pk)

@member
def inbox(request):
    return render(request,'market/inbox.html',feed_context(request))

@member
@require_POST
def contact(request,pk):
    item=get_object_or_404(Item,pk=pk,status='listed',owner__profile__restricted=False)
    if item.owner_id==request.user.pk or social.is_blocked(request.user,item.owner): raise PermissionDenied()
    thread,_=Thread.objects.get_or_create(item=item,first=request.user,second=item.owner,order=None,buddy=None,lostfound=None,wanted=None)
    return redirect('thread',pk=thread.pk)

@member
def chat(request,pk):
    thread=get_object_or_404(Thread.objects.select_related('first__profile','second__profile','item','order__item','buddy','lostfound','wanted'),pk=pk)
    if request.user.pk not in (thread.first_id,thread.second_id): raise PermissionDenied()
    other=thread.second if thread.first_id==request.user.pk else thread.first
    threads=list(chatlines.conversation_threads(request.user,other.pk).select_related('item','order__item','buddy','lostfound','wanted').order_by('-pk'))
    send_to=chatlines.writable_thread(threads,thread,request.user)
    if request.method=='POST':
        try:
            if send_to is None: raise ValidationError('此對話已關閉 / This conversation is closed')
            image=clean_image(request.FILES.get('image'))
            if image: chatlines.check_image_quota(request.user)
            chatlines.post_private(send_to,request.user,request.POST.get('text',''),image,chatlines.reply_target(request.POST.get('reply_to'),send_to,request.user))
        except ValidationError as exc: error(request,exc)
        return redirect('thread',pk=pk)
    inbox_data.mark_conversation_read(threads,request.user)
    chat_messages=chatlines.timeline(threads,request.user)
    # The top card follows what the conversation is currently about.
    about=thread if thread.order_id or thread.item_id else next((t for t in threads if t.order_id or t.item_id),thread)
    return render(request,'market/chat.html',{**feed_context(request,thread),'thread':thread,'open':send_to is not None,'other':other,'contacts':social.contact_state(thread,request.user),'card':inbox_data.chat_card(about,request.user,request.lang),'last_message_id':max((m.pk for m in chat_messages if not m.__class__ is Order),default=0),
        'blocked':social.is_blocked(request.user,other),'blocked_by_me':UserBlock.objects.filter(blocker=request.user,blocked=other).exists(),
        'chat_messages':chat_messages})

@member
def profile_edit(request):
    form=ProfileForm(request.POST if request.method=='POST' else None,request.FILES or None,instance=request.user.profile)
    if request.method=='POST' and form.is_valid():
        form.save(); messages.success(request,'個人資料已儲存 / Profile saved'); return redirect('profile')
    return render(request,'market/profile.html',{'form':form,'profile':request.user.profile})

@member
@require_POST
def buddy_group_action(request,pk):
    post=get_object_or_404(BuddyPost,pk=pk)
    try:
        if request.POST.get('action')=='create': group=groups.create(pk,request.user)
        elif request.POST.get('action')=='join':
            group=get_object_or_404(BuddyGroup,post=post)
            groups.join(group.pk,request.user)
        else: raise Http404()
        return redirect('group_chat',pk=group.pk)
    except ValidationError as exc:
        error(request,exc);return redirect('buddy',pk=pk)

@member
def group_chat(request,pk):
    group=get_object_or_404(BuddyGroup.objects.select_related('post__owner__profile'),pk=pk)
    row=groups.membership(group,request.user)
    if request.method=='POST':
        try:
            if request.POST.get('action')=='leave':
                groups.leave(pk,request.user);return redirect('buddy',pk=group.post_id)
            elif request.POST.get('action')=='send':
                image=clean_image(request.FILES.get('image'))
                if image: chatlines.check_image_quota(request.user)
                groups.send(pk,request.user,request.POST.get('text',''),image=image,reply_to=chatlines.group_reply_target(request.POST.get('reply_to'),group,request.user,row))
            else: raise Http404()
        except ValidationError as exc: error(request,exc)
        return redirect('group_chat',pk=pk)
    roster=[r for r in group.memberships.filter(left_at__isnull=True).select_related('user__profile') if groups.eligible(group,r.user)]
    inbox_data.mark_group_read(group,request.user,row)
    chat_messages=list(reversed(groups.visible_messages(group,request.user,row).select_related('reply_to__sender__profile').order_by('-pk')[:300]))
    return render(request,'market/group_chat.html',{**feed_context(request,group=group),'group':group,'membership':row,'roster':roster,'last_message_id':max((m.pk for m in chat_messages),default=0),
        'chat_messages':chat_messages})

@member
def people_search(request):
    # POST, so the address searched for stays out of URLs and logs.
    email,found,searched,count='',None,False,0
    if request.method=='POST':
        email=request.POST.get('email','').strip()[:254]
        try:
            throttle('people-search:'+str(request.user.pk),30,3600)
            searched=True
            found=find_member_by_email(email,request.user)
            if found: count=Item.objects.filter(owner=found.user,status='listed').count()
        except ValidationError as exc: error(request,exc)
    return render(request,'market/people_search.html',{'email':email,'found':found,'searched':searched,'item_count':count})

def person(request,pk):
    person=get_object_or_404(Profile.objects.select_related('user'),user_id=pk,restricted=False)
    reviews=Review.objects.filter(recipient_id=pk).select_related('author__profile').order_by('-created')
    me=request.user
    member=me.is_authenticated and hasattr(me,'profile') and me.profile.verified
    posts=BuddyPost.objects.filter(owner_id=pk,status='open').annotate(finish_at=Coalesce('ends','starts')).filter(finish_at__gt=timezone.now()).order_by('starts')[:6]
    # What they list is public on the site anyway; someone blocked in either direction does not see it here.
    items=[] if social.is_blocked(me,person.user) else Item.objects.filter(owner_id=pk,status='listed').prefetch_related('photos').order_by('-created')[:24]
    return render(request,'market/person.html',{'items':items,'person':person,'reviews':reviews,'average':reviews.aggregate(a=Avg('rating'))['a'],'member':member,'friendship':social.friendship(me,person.user) if member and me.pk!=pk else None,'posts':posts,'blocked':social.is_blocked(me,person.user),'blocked_by_me':UserBlock.objects.filter(blocker_id=me.pk,blocked=person.user).exists() if me.is_authenticated else False})

@member
@require_POST
def friend(request,pk):
    other=get_object_or_404(User,pk=pk,profile__restricted=False)
    action=request.POST.get('action','')
    try:
        if action=='request':
            f=social.request_friend(request.user,other)
            messages.success(request,'你們已成為好友 / You are now friends' if f.status=='accepted' else '已送出好友申請 / Friend request sent')
        elif action in ('accept','decline'):
            f=social.friendship(request.user,other)
            if not f: raise ValidationError('找不到好友申請 / Friend request not found')
            social.respond(request.user,f.pk,action=='accept')
        elif action=='cancel':
            f=social.friendship(request.user,other)
            if not f: raise ValidationError('找不到好友申請 / Friend request not found')
            social.cancel_request(request.user,f.pk)
        elif action=='remove': social.remove_friend(request.user,other)
        elif action=='chat':
            if not social.are_friends(request.user,other): raise PermissionDenied()
            return redirect('thread',pk=social.direct_thread(request.user,other).pk)
        else: raise Http404()
    except ValidationError as exc: error(request,exc)
    return redirect(safe_next(request,f'/people/{pk}/'))

BUDDY_WHEN={'today':1,'week':7,'month':30}
def buddy_list(request):
    p=request.GET; q=p.get('q','').strip()[:100]; major=p.get('major','').strip()[:160]; category=p.get('category',''); kind=p.get('kind',''); when=p.get('when',''); state=p.get('state','')
    now=timezone.now()
    member_search=request.user.is_authenticated and hasattr(request.user,'profile') and request.user.profile.verified
    if not member_search: major=''
    rows=BuddyPost.objects.filter(owner__profile__restricted=False).annotate(joined_count=Count('applications',filter=Q(applications__status='accepted')),finish_at=Coalesce('ends','starts'))
    if q:
        pattern=recommendations.course_query(q)
        match=Q(title__icontains=q)|Q(description__icontains=q)|Q(location__icontains=q)|Q(skills__icontains=q)
        if member_search: match |= Q(owner__profile__major__icontains=q)
        if pattern: match |= Q(title__iregex=pattern)|Q(description__iregex=pattern)|Q(skills__iregex=pattern)
        rows=rows.filter(match)
    if major: rows=rows.filter(owner__profile__major__icontains=major)
    if request.user.is_authenticated:
        blocked=UserBlock.objects.filter(Q(blocker=request.user)|Q(blocked=request.user))
        ids={r.blocked_id if r.blocker_id==request.user.pk else r.blocker_id for r in blocked}
        rows=rows.exclude(owner_id__in=ids)
    else: ids=set()
    if category in KINDS_BY_CATEGORY: rows=rows.filter(category=category)
    if kind in dict(BUDDY_KINDS): rows=rows.filter(kind=kind)
    if when in BUDDY_WHEN: rows=rows.filter(starts__lt=now+timedelta(days=BUDDY_WHEN[when]),finish_at__gt=now)
    active=rows.filter(status='open',finish_at__gt=now)
    rows={'open':active.filter(joined_count__lt=F('capacity')),'full':active.filter(joined_count__gte=F('capacity')),'closed':rows.filter(status='closed'),'ended':rows.filter(status='open',finish_at__lte=now),'all':rows}.get(state,active)
    rows=rows.select_related('owner__profile').order_by('-starts' if state in ('closed','ended','all') else 'starts','pk')
    recommendations.remember_search(request,q or major)
    if p.get('sort')!='time' and state not in ('closed','ended','all'):
        rows=recommendations.rank_posts(rows,request.user,request.session.get('buddy_searches',[]),university.academic_context(request.user.pk) if request.user.is_authenticated else None)[:100]
    else: rows=list(rows[:100])
    people=Profile.objects.none()
    if member_search and (major or q):
        people=Profile.objects.filter(verified=True,restricted=False,major__icontains=major or q).exclude(user_id__in=ids|{request.user.pk}).select_related('user').order_by('nickname','pk')[:8]
    return render(request,'market/buddies.html',{'rows':[(row,row.state(row.joined_count)) for row in rows],'people':people,'categories':BUDDY_CATEGORIES,'kinds':BUDDY_KINDS,'kinds_by_category':KINDS_BY_CATEGORY,'states':BuddyPost.STATES})

@member
@require_POST
def buddy_feedback(request,pk):
    post=get_object_or_404(BuddyPost,pk=pk,owner__profile__restricted=False)
    action=request.POST.get('action')
    if action not in ('dismiss','restore'): raise Http404()
    BuddyFeedback.objects.update_or_create(user=request.user,post=post,defaults={'dismissed':action=='dismiss'})
    return redirect(safe_next(request,'/buddy/'))

@member
def buddy_edit(request,pk=None):
    post=get_object_or_404(BuddyPost,pk=pk,owner=request.user) if pk else None
    form=BuddyForm(request.POST if request.method=='POST' else None,instance=post,joined=post.joined() if post else 0,initial=None if post else {'category':request.GET.get('category') if request.GET.get('category') in KINDS_BY_CATEGORY else 'buddy'})
    if request.method=='POST' and form.is_valid():
        try:
            if not post: throttle('buddy-post:'+str(request.user.pk),10,86400)
            with transaction.atomic():
                if post: social.lock_post(post.pk)
                obj=form.save(commit=False); obj.owner=request.user; obj.save()
            messages.success(request,'招募已儲存 / Post saved'); return redirect('buddy',pk=obj.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'market/buddy_form.html',{'form':form,'post':post})

def buddy_detail(request,pk):
    post=get_object_or_404(BuddyPost.objects.select_related('owner__profile'),pk=pk)
    me=request.user
    if post.owner.profile.restricted and me.pk!=post.owner_id and not me.is_staff: raise Http404()
    if request.method=='POST':
        if not me.is_authenticated: return redirect('login')
        if not hasattr(me,'profile') or not me.profile.verified or me.profile.restricted: raise PermissionDenied()
        action=request.POST.get('action','')
        application=request.POST.get('application','')
        try:
            if action=='apply':
                social.apply(post.pk,me,request.POST.get('message','').strip()); messages.success(request,'已送出申請，等待發起人審核 / Application sent. Waiting for the host.')
            elif action=='withdraw': social.withdraw(post.pk,me); messages.success(request,'已撤回 / Withdrawn')
            elif action in ('accept','decline','remove'):
                if not application.isdigit(): raise Http404()
                if action=='remove': social.remove_member(post.pk,me,int(application))
                else: social.decide(post.pk,me,int(application),action=='accept')
            elif action in ('close','reopen'): social.set_open(post.pk,me,action=='reopen')
            else: raise Http404()
        except ValidationError as exc: error(request,exc)
        return redirect('buddy',pk=pk)
    applications=list(post.applications.select_related('user__profile').order_by('created'))
    members=[a for a in applications if a.status=='accepted']
    mine=next((a for a in applications if a.user_id==me.pk),None) if me.is_authenticated else None
    host=me.pk==post.owner_id
    if me.is_authenticated and hasattr(me,'profile') and me.profile.verified and not host:
        BuddyFeedback.objects.get_or_create(user=me,post=post)
    threads={t.first_id:t for t in post.threads.all()} if host or (mine and mine.status=='accepted') else {}
    group=BuddyGroup.objects.filter(post=post).first()
    return render(request,'market/buddy.html',{'post':post,'state':post.state(len(members)),'joined':len(members),'left':max(post.capacity-len(members),0),'host':host,'mine':mine,
        'pending':[a for a in applications if a.status=='pending'] if host else [],'members':members if host or (mine and mine.status=='accepted') else [],
        'threads':threads,'my_thread':threads.get(me.pk) if mine and mine.status=='accepted' else None,
        'dismissed':BuddyFeedback.objects.filter(user=me,post=post,dismissed=True).exists() if me.is_authenticated else False,
        'buddy_group':group,'group_joined':group.memberships.filter(user=me,left_at__isnull=True).exists() if group and me.is_authenticated else False,
        'group_eligible':groups.eligible(group,me) if group else host})

@member
def report(request,kind,pk):
    model={'item':Item,'user':User,'order':Order,'buddy':BuddyPost,'lostfound':LostFoundPost,'thread':Thread,'group_message':BuddyGroupMessage}.get(kind)
    if not model: raise Http404()
    obj=get_object_or_404(model,pk=pk)
    if kind=='order' and request.user.pk not in (obj.borrower_id,obj.item.owner_id): raise PermissionDenied()
    if kind=='thread' and request.user.pk not in (obj.first_id,obj.second_id): raise PermissionDenied()
    if kind=='group_message':
        row=groups.membership(obj.group,request.user)
        if not groups.visible_messages(obj.group,request.user,row).filter(pk=obj.pk).exists(): raise PermissionDenied()
    if request.method=='POST':
        reason=request.POST.get('reason','').strip()
        if 5<=len(reason)<=2000:
            try: throttle('report:'+str(request.user.pk),10,3600)
            except ValidationError as exc:
                error(request,exc)
                return render(request,'market/report.html',{'kind':kind,'target':pk})
            Report.objects.create(reporter=request.user,kind=kind,target=pk,reason=reason)
            messages.success(request,'已提交舉報 / Report submitted'); return redirect('dashboard')
        messages.error(request,'請輸入 5–2000 字 / Enter 5–2000 characters')
    return render(request,'market/report.html',{'kind':kind,'target':pk})

def media(request,kind,pk):
    if kind=='item':
        photo=get_object_or_404(ItemPhoto.objects.select_related('item__owner__profile'),pk=pk)
        if (photo.item.status!='listed' or photo.item.owner.profile.restricted) and request.user.pk!=photo.item.owner_id and not request.user.is_staff: raise Http404()
        file=photo.image
    elif kind=='lostfound':
        post=get_object_or_404(LostFoundPost.objects.select_related('owner__profile'),pk=pk)
        if post.owner.profile.restricted and request.user.pk!=post.owner_id and not request.user.is_staff: raise Http404()
        file=post.photo
    elif kind=='avatar': file=get_object_or_404(Profile,user_id=pk,restricted=False).avatar
    elif kind=='payment':
        code=get_object_or_404(PaymentCode.objects.select_related('owner__profile'),pk=pk)
        if not payments.can_view(code,request.user): raise PermissionDenied()
        file=code.image
    elif kind=='evidence':
        photo=get_object_or_404(Evidence.objects.select_related('order__item'),pk=pk)
        if not request.user.is_authenticated or (request.user.pk not in (photo.order.borrower_id,photo.order.item.owner_id) and not request.user.is_staff): raise PermissionDenied()
        file=photo.image
    elif kind in ('message','groupmessage'):
        if not request.user.is_authenticated: raise PermissionDenied()
        line,_=chatlines.find_line('message' if kind=='message' else 'group',pk,request.user)
        if line.recalled: raise Http404()
        file=line.image
    else: raise Http404()
    if not file: raise Http404()
    response=FileResponse(file.open('rb'),content_type='image/jpeg')
    response['Cache-Control']='private, no-store'
    response['Content-Security-Policy']="default-src 'none'"
    return response

def rules(request): return render(request,'market/rules.html')
def impact(request): return render(request,'market/impact.html',{'impact':impact_summary(),'method_url':METHOD_URL})


# Lost & Found is separate from borrowing requests: direct contextual contact, no friend approval.
def lostfound_list(request):
    params=request.GET
    kind=params.get('kind','found')
    if kind not in dict(LOSTFOUND_KINDS): kind='found'
    rows=LostFoundPost.objects.filter(kind=kind,owner__profile__restricted=False).select_related('owner__profile')
    q=params.get('q','').strip()
    if q: rows=rows.filter(Q(title__icontains=q)|Q(description__icontains=q)|Q(color__icontains=q)|Q(location__icontains=q))
    category=params.get('category','')
    if category in dict(LOSTFOUND_CATEGORIES): rows=rows.filter(category=category)
    location=params.get('location','').strip()
    if location: rows=rows.filter(location__icontains=location)
    since=params.get('since','')
    today=timezone.localdate()
    cutoff={'today':today,'week':today-timedelta(days=7),'month':today-timedelta(days=30)}.get(since)
    if cutoff is None and since:
        try: cutoff=parse_date(since)
        except ValueError: cutoff=None
    if cutoff: rows=rows.filter(occurred_at__gte=timezone.make_aware(datetime.combine(cutoff,time.min)))
    status=params.get('status','open')
    if status in ('open','resolved'): rows=rows.filter(status=status)
    if request.user.is_authenticated:
        blocked=UserBlock.objects.filter(Q(blocker=request.user)|Q(blocked=request.user))
        excluded=[b.blocked_id if b.blocker_id==request.user.pk else b.blocker_id for b in blocked]
        rows=rows.exclude(owner_id__in=excluded)
    return render(request,'market/lostfound_list.html',{'rows':rows.order_by('-occurred_at','-pk')[:100],'categories':LOSTFOUND_CATEGORIES,'kinds':LOSTFOUND_KINDS,'kind':kind})

@member
def lostfound_edit(request,pk=None):
    post=get_object_or_404(LostFoundPost,pk=pk,owner=request.user) if pk else None
    initial={'kind':request.GET.get('kind') if request.GET.get('kind') in dict(LOSTFOUND_KINDS) else 'found'}
    form=LostFoundForm(request.POST if request.method=='POST' else None,request.FILES or None,instance=post,initial=initial if not post else None)
    if request.method=='POST' and form.is_valid():
        try:
            if not post: throttle('lostfound-post:'+str(request.user.pk),20,86400)
            obj=form.save(commit=False);obj.owner=request.user;obj.save()
            messages.success(request,'失物招領已儲存 / Lost and found post saved')
            return redirect('lostfound',pk=obj.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'market/lostfound_form.html',{'form':form,'post':post})

def lostfound_detail(request,pk):
    post=get_object_or_404(LostFoundPost.objects.select_related('owner__profile'),pk=pk)
    if post.owner.profile.restricted and request.user.pk!=post.owner_id and not request.user.is_staff: raise Http404()
    if request.method=='POST':
        if not request.user.is_authenticated: return redirect('login')
        if not hasattr(request.user,'profile') or not request.user.profile.verified or request.user.profile.restricted: raise PermissionDenied()
        if request.user.pk!=post.owner_id: raise PermissionDenied()
        action=request.POST.get('action')
        if action not in ('resolve','reopen'): raise Http404()
        post.status='resolved' if action=='resolve' else 'open';post.save(update_fields=['status'])
        return redirect('lostfound',pk=pk)
    blocked=social.is_blocked(request.user,post.owner)
    by_me=UserBlock.objects.filter(blocker_id=request.user.pk,blocked=post.owner).exists() if request.user.is_authenticated else False
    eligible=request.user.is_authenticated and hasattr(request.user,'profile') and request.user.profile.verified and not request.user.profile.restricted
    return render(request,'market/lostfound_detail.html',{'post':post,'blocked':blocked,'blocked_by_me':by_me,
        'can_contact':eligible and request.user.pk!=post.owner_id and not blocked and post.status=='open'})

@member
@require_POST
@transaction.atomic
def lostfound_contact(request,pk):
    post=get_object_or_404(LostFoundPost.objects.select_for_update().select_related('owner__profile'),pk=pk)
    list(Profile.objects.select_for_update().filter(user__in=[request.user,post.owner]).order_by('pk'))
    if post.owner_id==request.user.pk or post.status!='open' or post.owner.profile.restricted or not post.owner.is_active or social.is_blocked(request.user,post.owner): raise PermissionDenied()
    thread=Thread.objects.filter(lostfound=post,first=request.user,second=post.owner,item=None,order=None,buddy=None).first()
    if thread is None:
        throttle('lostfound-contact:'+str(request.user.pk),30,86400)
        thread=Thread.objects.create(lostfound=post,first=request.user,second=post.owner)
    return redirect('thread',pk=thread.pk)

@member
@require_POST
def user_block(request,pk):
    if pk==request.user.pk: raise PermissionDenied()
    other=get_object_or_404(User,pk=pk)
    action=request.POST.get('action')
    try:
        if action=='block':
            social.block_user(request.user,other)
            messages.success(request,'已封鎖對方，雙方不能再發送新訊息 / Blocked. Neither person can send new messages.')
        elif action=='unblock':
            social.unblock_user(request.user,other)
            messages.success(request,'已解除封鎖 / Unblocked')
        else: raise Http404()
    except ValidationError as exc: error(request,exc)
    return redirect(safe_next(request,'/messages/'))
