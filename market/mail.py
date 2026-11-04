import json, logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

log = logging.getLogger(__name__)

# Resend's HTTPS API, for hosts that block outbound SMTP ports (Render free blocks 25/465/587).
class ResendBackend(BaseEmailBackend):
    def send_messages(self,email_messages):
        sent=0
        for message in email_messages:
            body={'from':message.from_email,'to':message.to,'subject':message.subject,'text':message.body}
            for content,mimetype in getattr(message,'alternatives',[]):
                if mimetype=='text/html': body['html']=content
            req=Request('https://api.resend.com/emails',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+settings.RESEND_API_KEY,'Content-Type':'application/json','User-Agent':'box-box-share'},method='POST')
            try:
                with urlopen(req,timeout=settings.EMAIL_TIMEOUT) as response: response.read()
                sent+=1
            except Exception as exc:
                # Never log the exception itself in the general case: some repeat the Authorization header.
                if isinstance(exc,HTTPError): log.error('Resend rejected the email: HTTP %s %s',exc.code,exc.read(500).decode(errors='replace'))
                elif isinstance(exc,URLError): log.error('Could not reach Resend: %s',exc.reason)
                else: log.error('Could not send through Resend: %s',type(exc).__name__)
                if not self.fail_silently: raise
        return sent
