from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from .services import throttle, client_ip
# Same headers Caddy adds in the Docker deployment, for hosts where Django faces the platform proxy directly.
CSP="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
class SecurityHeadersMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        response=self.get_response(request)
        response.headers.setdefault('Content-Security-Policy',CSP)
        response.headers.setdefault('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        return response
class AccountMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        if request.method=='POST' and request.path=='/admin/login/':
            try: throttle('admin-login:'+client_ip(request),10,300)
            except ValidationError: return HttpResponse('Too many login requests / 登入過於頻繁',status=429)
        if request.user.is_authenticated and hasattr(request.user,'profile') and request.user.profile.restricted:
            logout(request)
        return self.get_response(request)
