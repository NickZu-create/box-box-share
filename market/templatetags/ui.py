from django import template
from market import i18n
register=template.Library()
@register.simple_tag(takes_context=True)
def tr(context,zh,en): return i18n.tr(zh,en,context.get('lang'))
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
