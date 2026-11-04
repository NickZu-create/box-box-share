"""Direct borrower-to-lender payment by the lender's QR codes, plus a reference HKD converter."""
import json, time
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from .models import Order, PaymentCode

# Orders the borrower can still pay for: from acceptance until the return is fully confirmed.
PAYABLE = ('accepted','active','return_pending')
# Currencies offered by the converter for each channel; the dropdown is the union of the lender's channels.
CHANNEL_CURRENCIES = {'wechat':('CNY','HKD'),'alipay_cn':('CNY',),'alipay_hk':('HKD',),'fps':('HKD','CNY')}
CURRENCY_ORDER = ('HKD','CNY')
RATES_KEY = 'payments:hkd-rates'
FAILURE_SECONDS = 300
MAX_RATES_SECONDS = 86400

def available_codes(owner):
    if owner.profile.restricted: return {}
    return {code.channel:code for code in PaymentCode.objects.filter(owner=owner)}

def currencies_for(channels):
    wanted={currency for channel in channels for currency in CHANNEL_CURRENCIES[channel]}
    return [currency for currency in CURRENCY_ORDER if currency in wanted]

def can_view(code,user):
    if user.is_staff or user.pk==code.owner_id: return True
    if not user.is_authenticated or code.owner.profile.restricted: return False
    return Order.objects.filter(item__owner_id=code.owner_id,borrower_id=user.pk,status__in=PAYABLE).exists()

def save_code(owner,channel,image):
    with transaction.atomic():
        code=PaymentCode.objects.select_for_update().filter(owner=owner,channel=channel).first()
        if not code: return PaymentCode.objects.create(owner=owner,channel=channel,image=image)
        old=code.image.name
        code.image=image; code.save()
        storage=code.image.storage
        transaction.on_commit(lambda: storage.delete(old))
    return code

def remove_code(owner,channel):
    with transaction.atomic():
        code=PaymentCode.objects.select_for_update().filter(owner=owner,channel=channel).first()
        if not code: return
        storage,name=code.image.storage,code.image.name
        code.delete()
        transaction.on_commit(lambda: storage.delete(name))

def fetch_rates():
    req=Request(settings.FX_URL,headers={'User-Agent':'box-box-share'})
    with urlopen(req,timeout=settings.FX_TIMEOUT) as response: body=json.load(response)
    if body['result']!='success': raise ValueError('rates unavailable')
    rates={currency:str(body['rates'][currency]) for currency in CURRENCY_ORDER}
    return {'rates':rates,'updated':body['time_last_update_unix']},body['time_next_update_unix']

def hkd_rates():
    """Rates per 1 HKD, or None. Cached until the provider's next update; failures are retried after 5 minutes."""
    cached=cache.get(RATES_KEY)
    if cached is not None: return cached or None
    try: data,next_update=fetch_rates()
    except (OSError,ValueError,KeyError,TypeError):
        cache.set(RATES_KEY,False,FAILURE_SECONDS)
        return None
    cache.set(RATES_KEY,data,max(60,min(int(next_update-time.time()),MAX_RATES_SECONDS)))
    return data
