"""Payment codes, the borrower's payment page and the reference exchange-rate endpoint."""
import json, shutil, tempfile, time
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Item, Notification, Order, PaymentCode, StoredFile
from .services import act, apply
from .tests import DB_STORAGE, make_item, make_user, photo

RATES = {'result':'success','base_code':'HKD','time_last_update_unix':1793750551,'time_next_update_unix':int(time.time())+3600,'rates':{'HKD':1,'CNY':0.85192,'USD':0.128}}

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
        for lang,text in (('en','Order charges'),('zh','訂單費用總額'),('hans','订单费用总额')):
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
    def test_existing_confirmations_do_not_become_an_outstanding_balance(self):
        self.code();self.accept();self.b.post('/language/',{'lang':'en'})
        for user in (self.owner,self.borrower):
            for action in ('rent','deposit'): act(self.order.pk,user,action)
        fields=('status','rent_owner','rent_borrower','deposit_owner','deposit_borrower')
        before=Order.objects.filter(pk=self.order.pk).values(*fields).get()
        page=self.b.get(self.url)
        self.assertTrue(page.context['both_payment_confirmations'])
        self.assertContains(page,'Order charges');self.assertNotContains(page,'Total to pay')
        self.assertContains(page,'data-pay-confirmed');self.assertContains(page,'avoid duplicate payments')
        self.assertContains(page,'Both confirmed (self-reported)',count=2)
        # QR viewing remains available without changing self-reported confirmations or order state.
        self.assertContains(page,'data-pay-qr')
        self.assertEqual(Order.objects.filter(pk=self.order.pk).values(*fields).get(),before)
    def test_one_sided_confirmation_identifies_each_party_without_subtraction(self):
        self.code();self.accept();self.b.post('/language/',{'lang':'en'})
        act(self.order.pk,self.borrower,'rent');act(self.order.pk,self.owner,'deposit')
        page=self.b.get(self.url)
        self.assertFalse(page.context['both_payment_confirmations'])
        self.assertContains(page,'Borrower confirmed; lender has not confirmed')
        self.assertContains(page,'Lender confirmed; borrower has not confirmed')
        self.assertEqual(page.context['amount'],str(self.order.total))
        self.assertNotContains(page,'data-pay-confirmed')
    def test_extension_keeps_confirmation_context_without_claiming_remaining_due(self):
        self.code();self.accept();self.b.post('/language/',{'lang':'en'})
        for user in (self.owner,self.borrower):
            for action in ('rent','deposit'): act(self.order.pk,user,action)
        old_total=self.order.total
        act(self.order.pk,self.borrower,'extend',new_end=self.order.end+timedelta(days=1))
        act(self.order.pk,self.owner,'approve_extension');self.order.refresh_from_db()
        page=self.b.get(self.url)
        self.assertGreater(self.order.total,old_total)
        self.assertEqual(page.context['amount'],str(self.order.total))
        self.assertTrue(page.context['both_payment_confirmations'])
        self.assertContains(page,'extra rent from extensions')
        self.assertContains(page,'does not record amounts paid or calculate the remaining balance')

@override_settings(STORAGES=DB_STORAGE)
class DatabasePaymentCodes(PaymentBase):
    def test_private_database_storage_upload_view_replace_remove(self):
        self.a.post('/profile/payment/',{'channel':'fps','photo':photo()})
        code=PaymentCode.objects.get(owner=self.owner,channel='fps');old_name=code.image.name
        self.assertTrue(StoredFile.objects.filter(name=old_name).exists())
        self.accept()
        response=self.b.get(f'/media/payment/{code.pk}/')
        self.assertEqual(response.status_code,200);self.assertTrue(response.getvalue())
        self.assertEqual(response['Cache-Control'],'private, no-store')
        with self.captureOnCommitCallbacks(execute=True):
            self.a.post('/profile/payment/',{'channel':'fps','photo':photo()})
        code.refresh_from_db();self.assertNotEqual(old_name,code.image.name)
        self.assertFalse(StoredFile.objects.filter(name=old_name).exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.a.post('/profile/payment/',{'channel':'fps','action':'remove'})
        self.assertFalse(PaymentCode.objects.exists());self.assertFalse(StoredFile.objects.exists())

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
    def test_wrong_base_and_invalid_rates_use_the_failure_fallback(self):
        invalid=[{**RATES,'base_code':'USD'},{**RATES,'rates':{'HKD':2,'CNY':1}}]
        invalid += [{**RATES,'rates':{'HKD':1,'CNY':value}} for value in ('NaN','Infinity','not-a-rate','1E9999','1E-9999',0,-1)]
        for body in invalid:
            with self.subTest(body=body):
                cache.clear()
                with mock.patch('market.payments.urlopen',return_value=Response(body)) as request:
                    self.assertEqual(self.b.get('/fx/hkd/').status_code,503)
                    self.assertEqual(self.b.get('/fx/hkd/').status_code,503)
                self.assertEqual(request.call_count,1)
    def test_invalid_update_timestamps_never_escape_as_server_errors(self):
        invalid=[{**RATES,'time_next_update_unix':value} for value in ('invalid',None,float('inf'),0)]
        invalid += [{**RATES,'time_last_update_unix':value} for value in ('invalid',None,int(time.time())+10000)]
        for body in invalid:
            with self.subTest(body=body):
                cache.clear()
                with mock.patch('market.payments.urlopen',return_value=Response(body)):
                    self.assertEqual(self.b.get('/fx/hkd/').status_code,503)
