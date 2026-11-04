"""Payment codes, the borrower's payment page and the reference exchange-rate endpoint."""
import json, shutil, tempfile, time
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Item, Notification, Order, PaymentCode
from .services import act, apply
from .tests import make_item, make_user, photo

RATES = {'result':'success','time_last_update_unix':1793750551,'time_next_update_unix':int(time.time())+3600,'rates':{'HKD':1,'CNY':0.85192,'USD':0.128}}

class Response:
    def __init__(self,body): self.body=json.dumps(body).encode()
    def read(self,*a): return self.body
    def __enter__(self): return self
    def __exit__(self,*a): return False

class PaymentBase(TestCase):
    def setUp(self):
        self.tmp=tempfile.mkdtemp(); self.media=override_settings(MEDIA_ROOT=self.tmp); self.media.enable()
        self.addCleanup(shutil.rmtree,self.tmp); self.addCleanup(self.media.disable)
        cache.clear()
        self.owner=make_user('pay-owner'); self.borrower=make_user('pay-borrower'); self.other=make_user('pay-other')
        self.a,self.b,self.c=Client(),Client(),Client()
        self.a.force_login(self.owner); self.b.force_login(self.borrower); self.c.force_login(self.other)
        self.item=make_item(self.owner)
        self.start=(timezone.now()+timedelta(days=2)).replace(second=0,microsecond=0)
        self.order=apply(self.item.pk,self.borrower,self.start,self.start+timedelta(hours=25))
        self.url=f'/orders/{self.order.pk}/pay/'
    def code(self,channel='wechat',owner=None):
        return PaymentCode.objects.create(owner=owner or self.owner,channel=channel,image=ContentFile(b'qr',name='qr.jpg'))
    def accept(self): act(self.order.pk,self.owner,'accept'); self.order.refresh_from_db()

class PaymentSettings(PaymentBase):
    def upload(self,channel='wechat',file=None): return self.a.post('/profile/payment/',{'channel':channel,'photo':file or photo()})
    def test_upload_replace_remove(self):
        self.assertEqual(self.upload().status_code,302)
        code=PaymentCode.objects.get(owner=self.owner,channel='wechat');first=code.image.name;storage=code.image.storage
        self.assertTrue(storage.exists(first))
        with self.captureOnCommitCallbacks(execute=True): self.upload()
        code.refresh_from_db();self.assertNotEqual(code.image.name,first);self.assertFalse(storage.exists(first))
        self.assertEqual(PaymentCode.objects.filter(owner=self.owner).count(),1)
        current=code.image.name
        with self.captureOnCommitCallbacks(execute=True): self.a.post('/profile/payment/',{'channel':'wechat','action':'remove'})
        self.assertFalse(PaymentCode.objects.exists());self.assertFalse(storage.exists(current))
    def test_rejects_bad_files_and_channels(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.upload(file=SimpleUploadedFile('x.svg',b'<svg/>',content_type='image/svg+xml'))
        self.assertFalse(PaymentCode.objects.exists())
        self.a.post('/profile/payment/',{'channel':'wechat'});self.assertFalse(PaymentCode.objects.exists())
        self.assertEqual(self.upload(channel='paypal').status_code,404)
    def test_page_requires_sign_in_and_shows_only_own_codes(self):
        self.assertEqual(Client().get('/profile/payment/').status_code,302)
        mine=self.code('fps');theirs=self.code('fps',self.other)
        page=self.a.get('/profile/payment/')
        self.assertContains(page,f'/media/payment/{mine.pk}/');self.assertNotContains(page,f'/media/payment/{theirs.pk}/')

class PaymentPage(PaymentBase):
    def test_roles_and_states(self):
        self.assertEqual(self.b.get(self.url).status_code,302)
        self.accept()
        self.assertEqual(self.b.get(self.url).status_code,200)
        self.assertRedirects(self.a.get(self.url),f'/orders/{self.order.pk}/')
        self.assertEqual(self.c.get(self.url).status_code,403)
        self.assertEqual(Client().get(self.url).status_code,302)
        act(self.order.pk,self.owner,'cancel')
        self.assertRedirects(self.b.get(self.url),f'/orders/{self.order.pk}/')
    def test_amount_is_rent_plus_deposit_and_follows_extension(self):
        self.code();self.accept()
        page=self.b.get(self.url);total=self.order.rent+self.order.deposit
        self.assertEqual(page.context['amount'],str(total));self.assertContains(page,f'data-amount="{total}"')
        Order.objects.filter(pk=self.order.pk).update(rent=self.order.rent+10)
        self.assertEqual(self.b.get(self.url).context['amount'],str(total+10))
    def test_free_order_needs_no_payment(self):
        self.code();self.accept();Order.objects.filter(pk=self.order.pk).update(rent=0,deposit=0)
        page=self.b.get(self.url)
        self.assertNotContains(page,'data-pay-qr');self.assertNotContains(page,'data-pay-converter')
        self.assertNotContains(self.b.get(f'/orders/{self.order.pk}/'),self.url)
    def test_no_codes_shows_empty_state(self):
        self.accept();page=self.b.get(self.url)
        self.assertContains(page,'pay-empty');self.assertNotContains(page,'pay-button');self.assertNotContains(page,'data-pay-converter')
    def test_only_enabled_channels_render(self):
        self.code('wechat');self.accept();page=self.b.get(self.url)
        self.assertContains(page,'pay-wechat');self.assertNotContains(page,'class="pay-button pay-alipay"');self.assertNotContains(page,'class="pay-button pay-fps"')
        self.assertEqual(page.context['currencies'],['HKD','CNY'])
    def test_alipay_menu_lists_only_enabled_options(self):
        hk=self.code('alipay_hk');self.accept();page=self.b.get(self.url)
        self.assertContains(page,'class="pay-button pay-alipay"');self.assertContains(page,'pay-sub-hk');self.assertNotContains(page,'pay-sub-cn')
        self.assertContains(page,f'/media/payment/{hk.pk}/');self.assertEqual(page.context['currencies'],['HKD'])
        self.code('alipay_cn');page=self.b.get(self.url)
        self.assertContains(page,'pay-sub-cn');self.assertContains(page,'pay-sub-hk');self.assertEqual(page.context['currencies'],['HKD','CNY'])
    def test_restricted_lender_offers_nothing(self):
        self.code();self.accept();self.owner.profile.restricted=True;self.owner.profile.save()
        self.assertContains(self.b.get(self.url),'pay-empty')
    def test_three_languages(self):
        self.code();self.accept()
        for lang,text in (('en','WeChat Pay'),('zh','應付總額'),('hans','应付总额')):
            self.b.post('/language/',{'lang':lang})
            self.assertContains(self.b.get(self.url),text)
    def test_order_page_links_and_lender_reminder(self):
        self.accept()
        self.assertContains(self.b.get(f'/orders/{self.order.pk}/'),self.url)
        self.assertContains(self.a.get(f'/orders/{self.order.pk}/'),'/profile/payment/')
        self.code();self.assertNotContains(self.a.get(f'/orders/{self.order.pk}/'),'/profile/payment/')
    def test_acceptance_notifies_borrower_with_payment_link(self):
        self.accept()
        self.assertTrue(Notification.objects.filter(user=self.borrower,url=self.url).exists())
    def test_rules_page_explains_direct_payment(self):
        self.b.post('/language/',{'lang':'en'})
        self.assertContains(self.b.get('/rules/'),'does not verify whether a payment was made')

class PaymentCodeAccess(PaymentBase):
    def setUp(self):
        super().setUp();self.qr=self.code();self.path=f'/media/payment/{self.qr.pk}/'
    def status(self,client):
        response=client.get(self.path);status=response.status_code
        if status==200: response.getvalue()
        return status
    def test_pending_borrower_cannot_see_code(self):
        self.assertEqual(self.status(self.b),403)
    def test_access(self):
        self.accept()
        self.assertEqual(self.status(self.a),200);self.assertEqual(self.status(self.b),200)
        self.assertEqual(self.status(self.c),403);self.assertEqual(self.status(Client()),403)
        response=self.b.get(self.path);self.assertEqual(response['Cache-Control'],'private, no-store');response.getvalue()
    def test_closed_orders_lose_access(self):
        self.accept();act(self.order.pk,self.owner,'cancel')
        self.assertEqual(self.status(self.b),403);self.assertEqual(self.status(self.a),200)
    def test_completed_order_loses_access(self):
        self.accept();Order.objects.filter(pk=self.order.pk).update(status='completed')
        self.assertEqual(self.status(self.b),403)
    def test_restricted_lender_code_hidden(self):
        self.accept();self.owner.profile.restricted=True;self.owner.profile.save()
        self.assertEqual(self.status(self.b),403)

class ExchangeRates(PaymentBase):
    def test_requires_sign_in(self):
        self.assertEqual(Client().get('/fx/hkd/').status_code,302)
    def test_success_is_filtered_and_cached(self):
        with mock.patch('market.payments.urlopen',return_value=Response(RATES)) as request:
            first=self.b.get('/fx/hkd/');second=self.c.get('/fx/hkd/')
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json(),{'rates':{'HKD':'1','CNY':'0.85192'},'updated':1793750551})
        self.assertEqual(second.json(),first.json());self.assertEqual(request.call_count,1)
    def test_failure_returns_503_and_is_not_retried_immediately(self):
        with mock.patch('market.payments.urlopen',side_effect=OSError('down')) as request:
            self.assertEqual(self.b.get('/fx/hkd/').status_code,503)
            self.assertEqual(self.b.get('/fx/hkd/').status_code,503)
        self.assertEqual(request.call_count,1)
    def test_bad_payloads_count_as_failure(self):
        for body in ({'result':'error'},{'result':'success','rates':{'HKD':1}}):
            cache.clear()
            with mock.patch('market.payments.urlopen',return_value=Response(body)):
                self.assertEqual(self.b.get('/fx/hkd/').status_code,503)
