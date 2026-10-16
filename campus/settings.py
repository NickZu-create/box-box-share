import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DEBUG', '1') == '1'
SECRET_KEY = os.getenv('SECRET_KEY', 'local-only-change-before-deployment')
if not DEBUG and (SECRET_KEY == 'local-only-change-before-deployment' or SECRET_KEY.startswith('REPLACE') or len(SECRET_KEY)<40):
    raise ImproperlyConfigured('Set SECRET_KEY')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if x]
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','market']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','market.middleware.AccountMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'campus.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[], 'APP_DIRS':True,'OPTIONS':{'builtins':['market.templatetags.ui'],'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','market.context.ui']}}]
WSGI_APPLICATION = 'campus.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'data.sqlite3','OPTIONS':{'timeout':30,'transaction_mode':'IMMEDIATE'},'TEST':{'NAME':os.getenv('SQLITE_TEST_PATH',str(BASE_DIR/'test.sqlite3'))}}}
if os.getenv('POSTGRES_HOST'):
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','HOST':os.environ['POSTGRES_HOST'],'NAME':os.environ['POSTGRES_DB'],'USER':os.environ['POSTGRES_USER'],'PASSWORD':os.environ['POSTGRES_PASSWORD'],'PORT':os.getenv('POSTGRES_PORT','5432')}}
LANGUAGE_CODE = 'zh-hant'
TIME_ZONE = 'Asia/Hong_Kong'
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR/'staticfiles'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR/'private-media')))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' if os.getenv('EMAIL_HOST') else 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = BASE_DIR/'dev-mail'
EMAIL_HOST = os.getenv('EMAIL_HOST','')
EMAIL_PORT = int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS','1') == '1'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL','Box Box Share <noreply@localhost>')
ALLOWED_EMAIL_DOMAINS = os.getenv('ALLOWED_EMAIL_DOMAINS','my.cityu.edu.hk').lower().split(',')
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 60*60*24*7
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 8*1024*1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024*1024
if not DEBUG and not EMAIL_HOST:
    raise ImproperlyConfigured('Production requires SMTP EMAIL_HOST; local file mail is development only')

TRUST_PROXY_IP = os.getenv('TRUST_PROXY_IP','0') == '1'

# AI listing drafts (Zhipu GLM-4.6V-Flash by default; any OpenAI-style chat/completions API). Disabled when AI_API_KEY is empty.
AI_API_KEY = os.getenv('AI_API_KEY','')
AI_BASE_URL = os.getenv('AI_BASE_URL','https://open.bigmodel.cn/api/paas/v4').rstrip('/')
AI_MODEL = os.getenv('AI_MODEL','glm-4.6v-flash')
AI_TIMEOUT = int(os.getenv('AI_TIMEOUT','60'))
# Zhipu's docs send raw base64; most other OpenAI-style providers expect a data: URI (set 1).
AI_IMAGE_DATA_URI = os.getenv('AI_IMAGE_DATA_URI','0') == '1'
# Shown to users before they upload, because photos leave this server.
AI_PROVIDER_LABEL = os.getenv('AI_PROVIDER_LABEL','智譜 AI（中國內地） / Zhipu AI (mainland China)')
CARBON_AVOIDED_PURCHASE_RATE = os.getenv('CARBON_AVOIDED_PURCHASE_RATE','0.25')
EMAIL_TIMEOUT = 15

SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
# same-origin, not no-referrer: no-referrer makes browsers send "Origin: null" on form POSTs, which fails Django's CSRF check.
SECURE_REFERRER_POLICY = "same-origin"
