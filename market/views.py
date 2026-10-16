import hashlib
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core import signing
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q, Avg
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import *
from .forms import *
from .services import *
from .impact import impact_summary, METHOD_URL
from . import ai

def error(request,exc): messages.error(request,'; '.join(exc.messages))
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
    request.session['lang']='en' if request.POST.get('lang')=='en' else 'zh'
    return redirect('home')

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
    return render(request,'market/dashboard.html',{'orders':orders,'items':Item.objects.filter(owner=request.user),'wanted_rows':Wanted.objects.filter(owner=request.user)})

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
    threads=Thread.objects.filter(Q(first=request.user)|Q(second=request.user)).select_related('item','order__item','first__profile','second__profile')
    notifications=Notification.objects.filter(user=request.user).order_by('-created')[:100]
    if request.method=='POST': Notification.objects.filter(user=request.user).update(read=True); return redirect('inbox')
    return render(request,'market/inbox.html',{'threads':threads,'notifications':notifications})

@member
@require_POST
def contact(request,pk):
    item=get_object_or_404(Item,pk=pk,status='listed',owner__profile__restricted=False)
    if item.owner_id==request.user.pk: raise PermissionDenied()
    thread,_=Thread.objects.get_or_create(item=item,first=request.user,second=item.owner,order=None)
    return redirect('thread',pk=thread.pk)

@member
def chat(request,pk):
    thread=get_object_or_404(Thread.objects.select_related('first__profile','second__profile','item','order__item'),pk=pk)
    if request.user.pk not in (thread.first_id,thread.second_id): raise PermissionDenied()
    if request.method=='POST':
        text=request.POST.get('text','').strip()
        try:
            throttle('message:'+str(request.user.pk),30,60)
            if not text or len(text)>2000: raise ValidationError('1–2000 characters / 請輸入 1–2000 字')
            Message.objects.create(thread=thread,sender=request.user,text=text)
            other=thread.second if thread.first_id==request.user.pk else thread.first
            notify(other,'收到新訊息 / New message',f'/messages/{thread.pk}/')
        except ValidationError as exc: error(request,exc)
        return redirect('thread',pk=pk)
    return render(request,'market/chat.html',{'thread':thread,'chat_messages':list(reversed(thread.messages.select_related('sender__profile').order_by('-created','-pk')[:300]))})

@member
def profile_edit(request):
    form=ProfileForm(request.POST or None,request.FILES or None,instance=request.user.profile)
    if request.method=='POST' and form.is_valid(): form.save(); return redirect('person',pk=request.user.pk)
    return render(request,'market/form.html',{'form':form,'title':'個人資料 / Profile'})

def person(request,pk):
    person=get_object_or_404(Profile.objects.select_related('user'),user_id=pk,restricted=False)
    reviews=Review.objects.filter(recipient_id=pk).select_related('author__profile').order_by('-created')
    return render(request,'market/person.html',{'person':person,'reviews':reviews,'average':reviews.aggregate(a=Avg('rating'))['a']})

@member
def report(request,kind,pk):
    model={'item':Item,'user':User,'order':Order}.get(kind)
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
