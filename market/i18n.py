import re
from contextvars import ContextVar
from functools import lru_cache
from django.utils import translation

# Three interface languages on top of the existing mechanism: {% tr '繁中' 'English' %} in templates and
# "繁中 / English" strings in Python. Simplified Chinese is generated from the Traditional text with OpenCC,
# so every page, form, message and notification gets it without a third copy of each string.
# User-written content is never passed through here.
LANGUAGES = [('en','English'),('zh','繁體中文'),('hans','简体中文')]
CODES = {code for code,_ in LANGUAGES}
HTML_LANG = {'en':'en','zh':'zh-Hant','hans':'zh-Hans'}
DJANGO_LANG = {'en':'en','zh':'zh-hant','hans':'zh-hans'}
COOKIE = 'lang'
current = ContextVar('ui_lang',default=None)
CJK = re.compile(r'[㐀-鿿豈-﫿]')
# OpenCC converts characters and phrases; these swap Hong Kong wording for the usual mainland terms.
WORDING = [('讯息','消息'),('帐号','账号'),('帐户','账户'),('暱称','昵称'),('登入','登录'),('登出','退出登录'),('连结','链接'),('预设','默认'),('储存','保存'),('设定','设置'),('搜寻','搜索'),('伺服器','服务器'),('网路','网络'),('档案','文件'),('重新整理','刷新'),('资讯','信息'),('程式','程序'),('支援','支持'),('透过','通过'),('社群','社区'),('介面','界面'),('选单','菜单')]

@lru_cache(maxsize=1)
def _converter():
    import opencc
    return opencc.OpenCC('hk2s')

@lru_cache(maxsize=8192)
def hans(text):
    out = _converter().convert(text)
    for old, new in WORDING: out = out.replace(old, new)
    return out

def zh(text, lang):
    return hans(text) if lang=='hans' else text

def tr(zh_text, en_text, lang=None):
    lang = lang or current.get() or 'zh'
    return en_text if lang=='en' else zh(zh_text, lang)

def pick(text, lang=None):
    # "繁中 / English" in either order -> the side for this language. Anything else passes through
    # (converted for Simplified). With no language active (migrations, admin, shell) text is unchanged.
    lang = lang or current.get()
    if lang is None or text is None: return text
    text = str(text)
    parts = text.split(' / ')
    if len(parts)==2 and bool(CJK.search(parts[0]))!=bool(CJK.search(parts[1])):
        chinese, english = (parts[0], parts[1]) if CJK.search(parts[0]) else (parts[1], parts[0])
        return english if lang=='en' else zh(chinese, lang)
    return text if lang=='en' else zh(text, lang)

def loc(text, lang=None):
    # Several errors are joined with "; " (see views.error); localise each one.
    if text is None: return text
    return '; '.join(pick(part, lang) for part in str(text).split('; '))

def language_of(request):
    lang = request.session.get('lang') or request.COOKIES.get(COOKIE)
    return lang if lang in CODES else 'zh'

class LanguageMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        lang = language_of(request)
        request.lang = lang
        # The admin keeps its bilingual labels; everything else renders in the chosen language.
        token = current.set(None if request.path.startswith('/admin/') else lang)
        translation.activate(DJANGO_LANG[lang])
        try: return self.get_response(request)
        finally:
            current.reset(token)
            translation.deactivate()
