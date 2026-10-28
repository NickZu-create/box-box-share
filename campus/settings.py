import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, unquote
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DEBUG', '1') == '1'
SECRET_KEY = os.getenv('SECRET_KEY', 'local-only-change-before-deployment')
# 32+ random characters; Render's dashboard "Generate" button produces exactly 32.
if not DEBUG and (SECRET_KEY == 'local-only-change-before-deployment' or SECRET_KEY.startswith('REPLACE') or len(SECRET_KEY)<32):
    raise ImproperlyConfigured('Set SECRET_KEY')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if x]
# Render provides the service's public hostname.
if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME']); CSRF_TRUSTED_ORIGINS.append('https://'+os.environ['RENDER_EXTERNAL_HOSTNAME'])
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','market']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','market.middleware.SecurityHeadersMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','market.middleware.AccountMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'campus.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[], 'APP_DIRS':True,'OPTIONS':{'builtins':['market.templatetags.ui'],'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','market.context.ui']}}]
WSGI_APPLICATION = 'campus.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'data.sqlite3','OPTIONS':{'timeout':30,'transaction_mode':'IMMEDIATE'},'TEST':{'NAME':os.getenv('SQLITE_TEST_PATH',str(BASE_DIR/'test.sqlite3'))}}}
if os.getenv('POSTGRES_HOST'):
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','HOST':os.environ['POSTGRES_HOST'],'NAME':os.environ['POSTGRES_DB'],'USER':os.environ['POSTGRES_USER'],'PASSWORD':os.environ['POSTGRES_PASSWORD'],'PORT':os.getenv('POSTGRES_PORT','5432')}}
# Hosted PostgreSQL (e.g. Neon) gives one connection string: postgresql://user:password@host/db?sslmode=require
if os.getenv('DATABASE_URL'):
    url = urlsplit(os.environ['DATABASE_URL'])
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','HOST':url.hostname,'PORT':str(url.port or 5432),'NAME':unquote(url.path.lstrip('/')),'USER':unquote(url.username or ''),'PASSWORD':unquote(url.password or ''),'OPTIONS':dict(parse_qsl(url.query)),'CONN_MAX_AGE':60,'CONN_HEALTH_CHECKS':True}}
LANGUAGE_CODE = 'zh-hant'
TIME_ZONE = 'Asia/Hong_Kong'
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR/'staticfiles'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR/'private-media')))
# MEDIA_STORAGE=db keeps photos in the database, for hosts without a persistent disk.
STORAGES = {'default': {'BACKEND':'market.dbstorage.DatabaseStorage' if os.getenv('MEDIA_STORAGE')=='db' else 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage' if DEBUG else 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
# Resend's HTTPS API when RESEND_API_KEY is set (for hosts that block SMTP), otherwise SMTP, otherwise local files.
RESEND_API_KEY = os.getenv('RESEND_API_KEY','')
EMAIL_BACKEND = 'market.mail.ResendBackend' if RESEND_API_KEY else 'django.core.mail.backends.smtp.EmailBackend' if os.getenv('EMAIL_HOST') else 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = BASE_DIR/'dev-mail'
EMAIL_HOST = os.getenv('EMAIL_HOST','')
EMAIL_PORT = int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS','1') == '1'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL','Box Box Share <noreply@localhost>')
MAIL_LIVE = bool(RESEND_API_KEY or EMAIL_HOST)
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
if not DEBUG and not MAIL_LIVE:
    raise ImproperlyConfigured('Production requires RESEND_API_KEY or SMTP EMAIL_HOST; local file mail is development only')

TRUST_PROXY_IP = os.getenv('TRUST_PROXY_IP','0') == '1'
# Header the trusted proxy overwrites with the real client IP (X-Real-IP behind our Caddy). Never a header clients can set.
CLIENT_IP_HEADER = 'HTTP_'+os.getenv('CLIENT_IP_HEADER','X-Real-IP').upper().replace('-','_')

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
# GPA proof files are deleted this many days after a reviewer decides (cleanup_auth runs the purge).
GPA_PROOF_RETENTION_DAYS = int(os.getenv('GPA_PROOF_RETENTION_DAYS','14'))
EMAIL_TIMEOUT = 15

SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
# same-origin, not no-referrer: no-referrer makes browsers send "Origin: null" on form POSTs, which fails Django's CSRF check.
SECURE_REFERRER_POLICY = "same-origin"
