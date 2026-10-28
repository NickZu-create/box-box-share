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
from django.db.models import Q, Avg, Count, F, Value
from django.db.models.functions import Coalesce
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import *
from .forms import *
from .services import *
from .impact import impact_summary, METHOD_URL
from . import ai, social, i18n

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
    return render(request,'market/home.html',{'rows':rows.select_related('owner__profile').prefetch_related('photos')[:100] if not wanted else rows.select_related('owner__profile')[:100],'wanted':wanted,'categories':CATEGORIES,'date_form':dates})

def signin(request):
    if request.method=='POST':
        try:
            send_login(request.POST.get('email',''),client_ip(request),request.build_absolute_uri('/').rstrip('/'))
            messages.success(request,'已建立登入郵件，請查收。 / Sign-in email created. Check your inbox.' if settings.MAIL_LIVE else '開發模式：登入郵件已寫入伺服器 dev-mail 目錄，未發送到學校郵箱。 / Development only: message saved to server dev-mail; not delivered.')
        except ValidationError as exc: error(request,exc)
    return render(request,'market/login.html')

def verify(request,raw):
    if request.method=='POST':
        try:
            throttle('verify:'+client_ip(request),30,300)
            user=consume_token(raw); login(request,user,backend='django.contrib.auth.backends.ModelBackend')
            return redirect('home')
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

@member
def item_edit(request,pk=None):
    item=get_object_or_404(Item,pk=pk,owner=request.user) if pk else None
    form=ItemForm(request.POST or None,request.FILES or None,instance=item)
    context={'form':form,'title':'發布／編輯借出物品 / List or edit an item','ai':ai.enabled() and not item,'ai_provider':settings.AI_PROVIDER_LABEL}
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            if item:
                Item.objects.select_for_update().get(pk=item.pk)
                if Order.objects.filter(item=item,status__in=Order.LOCKED).filter(Q(start__lt=form.cleaned_data['available_start'])|Q(end__gt=form.cleaned_data['available_end'])).exists():
                    form.add_error(None,'保留已接受預約的可借日期 / Keep availability for accepted bookings')
                    return render(request,'market/form.html',context)
            obj=form.save(commit=False); obj.owner=request.user; obj.save()
            for photo in form.cleaned_data.get('remove_photos',[]):
                storage,name=photo.image.storage,photo.image.name
                photo.delete()
                transaction.on_commit(lambda storage=storage,name=name: storage.delete(name))
            if form.cleaned_data['photo']: ItemPhoto.objects.create(item=obj,image=form.cleaned_data['photo'])
        return redirect('item',pk=obj.pk)
    return render(request,'market/form.html',context)

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
        if not request.user.is_authenticated: return redirect('login')
        if not request.user.profile.verified or request.user.profile.restricted: raise PermissionDenied()
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
                    o=apply(item.pk,request.user,form.cleaned_data['start'],form.cleaned_data['end'],expected=expected); return redirect('order',pk=o.pk)
            except ValidationError as exc: form.add_error(None,exc)
    return render(request,'market/item.html',{'item':item,'form':form,'quote':quote,'quote_token':quote_token})

@member
def wanted_edit(request,pk=None):
    obj=get_object_or_404(Wanted,pk=pk,owner=request.user) if pk else None
    form=WantedForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False); obj.owner=request.user; obj.save(); return redirect('wanted',pk=obj.pk)
    return render(request,'market/form.html',{'form':form,'title':'發布／編輯尋物 / Post or edit a request'})

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
        if obj.owner_id==request.user.pk or not obj.active: raise PermissionDenied()
        text=request.POST.get('text','').strip()
        if len(text)>1000: raise PermissionDenied()
        Offer.objects.create(wanted=obj,item=item,text=text)
        notify(obj.owner,'收到尋物回應 / New offer',f'/wanted/{obj.pk}/')
        return redirect('wanted',pk=pk)
    return render(request,'market/wanted.html',{'wanted':obj,'items':items})

@member
def dashboard(request):
    orders=Order.objects.filter(Q(borrower=request.user)|Q(item__owner=request.user)).select_related('item','borrower__profile','item__owner__profile').order_by('-created')
    # Buddy stays in its own section; it never mixes with lending and borrowing orders.
    posts=BuddyPost.objects.filter(owner=request.user).annotate(joined_count=Count('applications',filter=Q(applications__status='accepted')),pending_count=Count('applications',filter=Q(applications__status='pending'))).order_by('-created')
    applications=BuddyApplication.objects.filter(user=request.user).select_related('post').order_by('-created')
    return render(request,'market/dashboard.html',{'orders':orders,'items':Item.objects.filter(owner=request.user),'wanted_rows':Wanted.objects.filter(owner=request.user),
        'buddy_posts':[(p,p.state(p.joined_count)) for p in posts],'buddy_applications':[a for a in applications if a.status!='accepted'],'buddy_joined':[a for a in applications if a.status=='accepted']})

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
            act(o.pk,request.user,request.POST.get('action'),new_end,photo)
            messages.success(request,'操作已記錄 / Confirmation recorded')
        except ValidationError as exc: error(request,exc)
        return redirect('order',pk=pk)
    return render(request,'market/order.html',{'order':o,'owner':request.user.pk==o.item.owner_id,'reviewed':Review.objects.filter(order=o,author=request.user).exists(),'survey':o.surveys.first() if request.user.pk==o.borrower_id else None,'extension_rent':Decimal(o.snapshot['daily'])*interval(o.start,o.extension_end) if o.extension_end else None})

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
            r.full_clean(); r.save(); notify(recipient,'收到新評價 / New review',f'/people/{recipient.pk}/')
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
    me=request.user
    threads=Thread.objects.filter(Q(first=me)|Q(second=me)).select_related('item','order__item','buddy','first__profile','second__profile').order_by('-pk')
    notifications=Notification.objects.filter(user=me).order_by('-created')[:100]
    if request.method=='POST': Notification.objects.filter(user=me).update(read=True); return redirect('inbox')
    friendships=Friendship.objects.filter(Q(sender=me)|Q(recipient=me)).select_related('sender__profile','recipient__profile').order_by('-created')
    friends=[(f,f.recipient if f.sender_id==me.pk else f.sender) for f in friendships if f.status=='accepted']
    return render(request,'market/inbox.html',{'threads':threads,'notifications':notifications,'friends':friends,
        'incoming':[f for f in friendships if f.status=='pending' and f.recipient_id==me.pk],'outgoing':[f for f in friendships if f.status=='pending' and f.sender_id==me.pk]})

@member
@require_POST
def contact(request,pk):
    item=get_object_or_404(Item,pk=pk,status='listed',owner__profile__restricted=False)
    if item.owner_id==request.user.pk: raise PermissionDenied()
    thread,_=Thread.objects.get_or_create(item=item,first=request.user,second=item.owner,order=None)
    return redirect('thread',pk=thread.pk)

@member
def chat(request,pk):
    thread=get_object_or_404(Thread.objects.select_related('first__profile','second__profile','item','order__item','buddy'),pk=pk)
    if request.user.pk not in (thread.first_id,thread.second_id): raise PermissionDenied()
    open_=social.can_message(thread,request.user)
    if request.method=='POST':
        text=request.POST.get('text','').strip()
        try:
            if not open_: raise ValidationError('此對話已關閉 / This conversation is closed')
            throttle('message:'+str(request.user.pk),30,60)
            if not text or len(text)>2000: raise ValidationError('1–2000 characters / 請輸入 1–2000 字')
            Message.objects.create(thread=thread,sender=request.user,text=text)
            other=thread.second if thread.first_id==request.user.pk else thread.first
            # One unread notification per conversation, however many messages arrive.
            if not Notification.objects.filter(user=other,url=f'/messages/{thread.pk}/',read=False).exists(): notify(other,'收到新訊息 / New message',f'/messages/{thread.pk}/')
        except ValidationError as exc: error(request,exc)
        return redirect('thread',pk=pk)
    return render(request,'market/chat.html',{'thread':thread,'open':open_,'other':thread.second if thread.first_id==request.user.pk else thread.first,'chat_messages':list(reversed(thread.messages.select_related('sender__profile').order_by('-created','-pk')[:300]))})

@member
def profile_edit(request):
    form=ProfileForm(request.POST if request.method=='POST' else None,request.FILES or None,instance=request.user.profile)
    if request.method=='POST' and form.is_valid():
        form.save(); messages.success(request,'個人資料已儲存 / Profile saved'); return redirect('profile')
    return render(request,'market/profile.html',{'form':form,'profile':request.user.profile})

def person(request,pk):
    person=get_object_or_404(Profile.objects.select_related('user'),user_id=pk,restricted=False)
    reviews=Review.objects.filter(recipient_id=pk).select_related('author__profile').order_by('-created')
    me=request.user
    member=me.is_authenticated and hasattr(me,'profile') and me.profile.verified
    posts=BuddyPost.objects.filter(owner_id=pk,status='open').annotate(finish_at=Coalesce('ends','starts')).filter(finish_at__gt=timezone.now()).order_by('starts')[:6]
    return render(request,'market/person.html',{'person':person,'reviews':reviews,'average':reviews.aggregate(a=Avg('rating'))['a'],'member':member,'friendship':social.friendship(me,person.user) if member and me.pk!=pk else None,'posts':posts})

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
    p=request.GET; q=p.get('q','').strip(); category=p.get('category',''); kind=p.get('kind',''); when=p.get('when',''); state=p.get('state','')
    now=timezone.now()
    rows=BuddyPost.objects.filter(owner__profile__restricted=False).annotate(joined_count=Count('applications',filter=Q(applications__status='accepted')),finish_at=Coalesce('ends','starts'))
    if q: rows=rows.filter(Q(title__icontains=q)|Q(description__icontains=q)|Q(location__icontains=q)|Q(skills__icontains=q))
    if category in KINDS_BY_CATEGORY: rows=rows.filter(category=category)
    if kind in dict(BUDDY_KINDS): rows=rows.filter(kind=kind)
    if when in BUDDY_WHEN: rows=rows.filter(starts__lt=now+timedelta(days=BUDDY_WHEN[when]),finish_at__gt=now)
    active=rows.filter(status='open',finish_at__gt=now)
    rows={'open':active.filter(joined_count__lt=F('capacity')),'full':active.filter(joined_count__gte=F('capacity')),'closed':rows.filter(status='closed'),'ended':rows.filter(status='open',finish_at__lte=now),'all':rows}.get(state,active)
    rows=rows.select_related('owner__profile').order_by('-starts' if state in ('closed','ended','all') else 'starts','pk')[:100]
    return render(request,'market/buddies.html',{'rows':[(row,row.state(row.joined_count)) for row in rows],'categories':BUDDY_CATEGORIES,'kinds':BUDDY_KINDS,'kinds_by_category':KINDS_BY_CATEGORY,'states':BuddyPost.STATES})

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
    threads={t.first_id:t for t in post.threads.all()} if host or (mine and mine.status=='accepted') else {}
    return render(request,'market/buddy.html',{'post':post,'state':post.state(len(members)),'joined':len(members),'left':max(post.capacity-len(members),0),'host':host,'mine':mine,
        'pending':[a for a in applications if a.status=='pending'] if host else [],'members':members if host or (mine and mine.status=='accepted') else [],
        'threads':threads,'my_thread':threads.get(me.pk) if mine and mine.status=='accepted' else None})

@member
def report(request,kind,pk):
    model={'item':Item,'user':User,'order':Order,'buddy':BuddyPost}.get(kind)
    if not model: raise Http404()
    obj=get_object_or_404(model,pk=pk)
    if kind=='order' and request.user.pk not in (obj.borrower_id,obj.item.owner_id): raise PermissionDenied()
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
    elif kind=='avatar': file=get_object_or_404(Profile,user_id=pk,restricted=False).avatar
    elif kind=='evidence':
        photo=get_object_or_404(Evidence.objects.select_related('order__item'),pk=pk)
        if not request.user.is_authenticated or (request.user.pk not in (photo.order.borrower_id,photo.order.item.owner_id) and not request.user.is_staff): raise PermissionDenied()
        file=photo.image
    else: raise Http404()
    if not file: raise Http404()
    response=FileResponse(file.open('rb'),content_type='image/jpeg')
    response['Cache-Control']='private, no-store'
    response['Content-Security-Policy']="default-src 'none'"
    return response

def rules(request): return render(request,'market/rules.html')
def impact(request): return render(request,'market/impact.html',{'impact':impact_summary(),'method_url':METHOD_URL})
