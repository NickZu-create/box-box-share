from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from .services import throttle, client_ip
class AccountMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        if request.method=='POST' and request.path=='/admin/login/':
            try: throttle('admin-login:'+client_ip(request),10,300)
            except ValidationError: return HttpResponse('Too many login requests / 登入過於頻繁',status=429)
        if request.user.is_authenticated and hasattr(request.user,'profile') and request.user.profile.restricted:
            logout(request)
        return self.get_response(request)
