from datetime import timedelta
from django import template
from django.utils import timezone
from django.forms.utils import flatatt
from django.utils.html import format_html
from market import ai, i18n, translate
register=template.Library()
@register.simple_tag(takes_context=True)
def tr(context,zh,en): return i18n.tr(zh,en,context.get('lang'))
def chat_day(value):
    day=timezone.localtime(value).date()
    today=timezone.localdate()
    if day==today: return i18n.loc('今天 / Today')
    if day==today-timedelta(days=1): return i18n.loc('昨天 / Yesterday')
    return f'{day.year}/{day.month:02d}/{day.day:02d}' if day.year!=today.year else f'{day.month}/{day.day}'
register.filter('chat_day',chat_day)
@register.filter
def chat_time(value):
    # Today shows the time, like a phone's chat list; anything older shows the day.
    return timezone.localtime(value).strftime('%H:%M') if timezone.localtime(value).date()==timezone.localdate() else chat_day(value)
# For system text stored or defined as "繁中 / English": choice labels, notifications, flash messages.
@register.filter
def loc(text): return i18n.loc(text)
@register.filter
def action_label(text):
    from market.services import ORDER_ACTIONS
    return i18n.loc(ORDER_ACTIONS.get(text,text))

@register.filter
def get_item(mapping,key): return mapping.get(key) if hasattr(mapping,'get') else None

@register.simple_tag(takes_context=True)
def query_with(context,**changes):
    params=context['request'].GET.copy()
    for key,value in changes.items():
        if value: params[key]=value
        else: params.pop(key,None)
    encoded=params.urlencode()
    return '/?'+encoded if encoded else '/'

def _tx_memo(context):
    request=context.get('request')
    if request is None: return {}
    if not hasattr(request,'tx_memo'): request.tx_memo={}
    return request.tx_memo

@register.simple_tag(takes_context=True)
def tx_prime(context,rows):
    translate.prime(rows,context.get('lang') or 'zh',_tx_memo(context))
    return ''

# A field a member wrote, in the reader's language. plain=True is for attributes and <title>.
@register.simple_tag(takes_context=True)
def tx(context,obj,field,truncate=0,lines=False,plain=False):
    text=getattr(obj,field) or ''
    shown,state=translate.display(text,context.get('lang') or 'zh',_tx_memo(context))
    shown=translate.clip(shown,truncate)
    if plain: return shown
    attrs={}
    if lines: attrs['class']='tx-lines'
    if state=='pending':
        attrs['data-tx']=f'{translate.KINDS[type(obj)]}:{obj.pk}:{field}'
        if truncate: attrs['data-tx-max']=truncate
    elif state=='machine':
        attrs['data-tx-machine']=''
        attrs['data-tx-original']=translate.clip(text,truncate)
    return format_html('<span{}>{}</span>',flatatt(attrs),shown) if attrs else shown

# "Translate" under a chat message, when translating it would change anything.
@register.simple_tag(takes_context=True)
def tx_message(context,message,kind='message'):
    lang=context.get('lang') or 'zh'
    target=translate.target_of(message.text,lang)
    if (target and not ai.enabled()) or (not target and translate.converted(message.text,lang)==message.text): return ''
    return format_html('<button class="bubble-translate" type="button" data-tx-msg="{}:{}">{}</button>',kind,message.pk,i18n.tr('翻譯','Translate',lang))
