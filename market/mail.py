import json
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

# Resend's HTTPS API, for hosts that block outbound SMTP ports (Render free blocks 25/465/587).
class ResendBackend(BaseEmailBackend):
    def send_messages(self,email_messages):
        sent=0
        for message in email_messages:
            body={'from':message.from_email,'to':message.to,'subject':message.subject,'text':message.body}
            req=Request('https://api.resend.com/emails',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+settings.RESEND_API_KEY,'Content-Type':'application/json','User-Agent':'box-box-share'},method='POST')
            try:
                with urlopen(req,timeout=settings.EMAIL_TIMEOUT) as response: response.read()
                sent+=1
            except Exception:
                if not self.fail_silently: raise
        return sent
