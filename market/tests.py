import re, tempfile, shutil, base64, json
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from threading import Barrier
from PIL import Image
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.core import mail
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction, IntegrityError, close_old_connections
from django.utils import timezone
from .models import *
from .services import *
from .impact import impact_summary
from . import social, i18n
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

def make_user(name,verified=True):
    u=User.objects.create_user(name+'@my.cityu.edu.hk',email=name+'@my.cityu.edu.hk')
    u.set_unusable_password();u.save()
    Profile.objects.create(user=u,nickname=name,verified=verified)
    return u

def make_item(user):
    return Item.objects.create(owner=user,title='Campus camera',category='tech',description='A real test listing',condition='Good',daily=Decimal('18.50'),deposit=100,available_start=timezone.now(),available_end=timezone.now()+timedelta(days=60),max_days=30,location='AC1 entrance')

def photo():
    b=BytesIO(); Image.new('RGB',(30,30),'green').save(b,'PNG')
    return SimpleUploadedFile('photo.png',b.getvalue(),content_type='image/png')

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CampusFlow(TestCase):
    def setUp(self):
        self.owner=make_user('owner'); self.borrower=make_user('borrower'); self.other=make_user('outsider')
        self.item=make_item(self.owner); self.start=(timezone.now()+timedelta(days=2)).replace(second=0,microsecond=0); self.end=self.start+timedelta(hours=25)
        self.a=Client();self.b=Client();self.c=Client()
        self.a.force_login(self.owner);self.b.force_login(self.borrower);self.c.force_login(self.other)
        self.tmp=tempfile.mkdtemp(); self.media=override_settings(MEDIA_ROOT=self.tmp);self.media.enable()
    def tearDown(self): self.media.disable();shutil.rmtree(self.tmp)
    def booking(self): return apply(self.item.pk,self.borrower,self.start,self.end)
    def test_two_account_email_to_review_http(self):
        # No force_login: both normal accounts authenticate via their own delivered test message.
        clients=[]
        for n in ('alice','bob'):
            c=Client();r=c.post('/login/',{'email':n+'@my.cityu.edu.hk'})
            self.assertEqual(r.status_code,200)
            path=re.search(r'http://testserver(/verify/[^\s]+)',mail.outbox[-1].body).group(1)
            self.assertEqual(c.get(path).status_code,200)
            self.assertEqual(c.post(path).status_code,302)
            clients.append(c)
        a,b=clients
        d={'title':'Tripod','category':'creative','description':'Shared tripod','condition':'Good','daily':'0','deposit':'50','available_start':self.start.strftime('%Y-%m-%dT%H:%M'),'available_end':(self.end+timedelta(days=10)).strftime('%Y-%m-%dT%H:%M'),'max_days':'7','location':'AC2','status':'listed','photo':photo()}
        self.assertEqual(a.post('/items/new/',d).status_code,302)
        item=Item.objects.get(title='Tripod');self.assertTrue(item.photos.exists())
        dates={'start':self.start.strftime('%Y-%m-%dT%H:%M'),'end':self.end.strftime('%Y-%m-%dT%H:%M'),'action':'quote'}
        response=b.post(f'/items/{item.pk}/',dates)
        self.assertContains(response,'HK$ 0')
        dates['quote_token']=re.search(r'name="quote_token" value="([^"]+)"',response.content.decode()).group(1)
        dates['action']='apply';self.assertEqual(b.post(f'/items/{item.pk}/',dates).status_code,302)
        order=Order.objects.get(item=item); url=f'/orders/{order.pk}/'
        self.assertEqual(a.post(url,{'action':'accept'}).status_code,302)
        # A second overlapping pending request is deliberately created before acceptance in other tests.
        for client in (a,b): self.assertEqual(client.post(url,{'action':'handover','photo':photo()}).status_code,302)
        order.refresh_from_db();self.assertEqual(order.status,'active')
        b.post(url,{'action':'return','photo':photo()});order.refresh_from_db();self.assertEqual(order.status,'return_pending')
        a.post(url,{'action':'return'});order.refresh_from_db();self.assertEqual(order.status,'completed');self.assertIsNotNone(order.actual_return)
        for client in (a,b): self.assertEqual(client.post(url+'review/',{'rating':5,'text':'Great experience'}).status_code,302)
        self.assertEqual(order.reviews.count(),2)
        self.assertFalse(User.objects.get(email='alice@my.cityu.edu.hk').has_usable_password())
    def test_domain_and_unverified_blocked(self):
        c=Client();self.assertContains(c.post('/login/',{'email':'x@evilmy.cityu.edu.hk'}),'僅接受指定學校郵箱')
        self.assertEqual(LoginToken.objects.count(),0)
        u=make_user('unverified',False);c.force_login(u)
        self.assertEqual(c.get('/items/new/').status_code,403)
        self.assertEqual(c.get('/wanted/new/').status_code,403)
        self.assertEqual(c.post(f'/items/{self.item.pk}/',{'action':'apply'}).status_code,403)
    def test_email_single_use_expiry_scanner_safe(self):
        c=Client();c.post('/login/',{'email':'new@my.cityu.edu.hk'})
        path=re.search(r'http://testserver(/verify/[^\s]+)',mail.outbox[-1].body).group(1)
        c.get(path);self.assertFalse(LoginToken.objects.get().used)
        c.post(path);self.assertTrue(LoginToken.objects.get().used)
        self.assertContains(Client().post(path),'連結過期或已使用')
        raw=secrets.token_urlsafe(32)
        LoginToken.objects.create(email='old@my.cityu.edu.hk',digest=hashlib.sha256(raw.encode()).hexdigest(),expires=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError): consume_token(raw)
    def test_email_rate_limit(self):
        c=Client();c.post('/login/',{'email':'new@my.cityu.edu.hk'})
        self.assertContains(c.post('/login/',{'email':'new@my.cityu.edu.hk'}),'請稍後再試')
        self.assertEqual(len(mail.outbox),1)
    def test_overlap_adjacency_cancel_release(self):
        first=self.booking();second=self.booking()
        act(first.pk,self.owner,'accept')
        with self.assertRaises(ValidationError): act(second.pk,self.owner,'accept')
        next_order=apply(self.item.pk,self.borrower,self.end,self.end+timedelta(days=1));act(next_order.pk,self.owner,'accept')
        act(first.pk,self.owner,'cancel');act(second.pk,self.owner,'accept')
        second.refresh_from_db();self.assertEqual(second.status,'accepted')
    def test_changed_quote_cannot_silently_change_price(self):
        dates={'start':self.start.strftime('%Y-%m-%dT%H:%M'),'end':self.end.strftime('%Y-%m-%dT%H:%M'),'action':'quote'}
        response=self.b.post(f'/items/{self.item.pk}/',dates)
        dates['quote_token']=re.search(r'name="quote_token" value="([^"]+)"',response.content.decode()).group(1)
        Item.objects.filter(pk=self.item.pk).update(daily=30)
        dates['action']='apply'
        self.assertContains(self.b.post(f'/items/{self.item.pk}/',dates),'物品價格或條款已更改')
        self.assertFalse(Order.objects.exists())
    def test_admin_order_evidence_and_report_pages(self):
        o=self.booking();admin=User.objects.create_superuser('admin','operator@example.org','platform-admin-only')
        c=Client();c.force_login(admin)
        self.assertEqual(c.get(f'/admin/market/order/{o.pk}/change/').status_code,200)
        report=Report.objects.create(reporter=self.borrower,kind='order',target=o.pk,reason='Please inspect')
        self.assertContains(c.get(f'/admin/market/report/{report.pk}/change/'),'Open target')
    def test_partial_handover_cannot_cancel(self):
        o=self.booking();act(o.pk,self.owner,'accept');act(o.pk,self.owner,'handover')
        with self.assertRaises(ValidationError): act(o.pk,self.borrower,'cancel')
    def test_database_rejects_bypass_overlap(self):
        a=self.booking();b=self.booking();act(a.pk,self.owner,'accept')
        with self.assertRaises(IntegrityError):
            with transaction.atomic(): Order.objects.filter(pk=b.pk).update(status='accepted')
    def test_snapshot_daily_and_terms_immutable(self):
        o=self.booking();snapshot=dict(o.snapshot)
        Item.objects.filter(pk=self.item.pk).update(daily=999,deposit=999)
        act(o.pk,self.owner,'accept');o.refresh_from_db()
        self.assertEqual(o.rent,Decimal('37.00'));self.assertEqual(o.deposit,100);self.assertEqual(o.snapshot,snapshot)
        act(o.pk,self.borrower,'extend',self.end+timedelta(days=1));act(o.pk,self.owner,'approve_extension');o.refresh_from_db()
        self.assertEqual(o.rent,Decimal('55.50'));self.assertEqual(o.snapshot,snapshot)
    def test_extension_requires_approval_and_conflict_recheck(self):
        a=self.booking();act(a.pk,self.owner,'accept')
        b=apply(self.item.pk,self.borrower,self.end,self.end+timedelta(days=1));act(b.pk,self.owner,'accept')
        act(a.pk,self.borrower,'extend',self.end+timedelta(hours=1));a.refresh_from_db();self.assertEqual(a.end,self.end)
        with self.assertRaises(ValidationError): act(a.pk,self.owner,'approve_extension')
        act(b.pk,self.borrower,'cancel');act(a.pk,self.owner,'approve_extension');a.refresh_from_db();self.assertEqual(a.end,self.end+timedelta(hours=1))
    def test_bilateral_states_and_payment(self):
        o=self.booking();act(o.pk,self.owner,'accept');act(o.pk,self.owner,'rent');o.refresh_from_db()
        self.assertTrue(o.rent_owner);self.assertFalse(o.rent_borrower)
        act(o.pk,self.owner,'handover');o.refresh_from_db();self.assertEqual(o.status,'accepted')
        act(o.pk,self.borrower,'handover');o.refresh_from_db();self.assertEqual(o.status,'active')
        with self.assertRaises(ValidationError): act(o.pk,self.owner,'cancel')
        act(o.pk,self.borrower,'return');o.refresh_from_db();self.assertEqual(o.status,'return_pending');self.assertIsNone(o.actual_return)
        act(o.pk,self.owner,'return');o.refresh_from_db();self.assertEqual(o.status,'completed')
    def test_permission_isolation_orders_chat_evidence_admin(self):
        o=self.booking();act(o.pk,self.owner,'accept');act(o.pk,self.owner,'handover',photo=clean_image(photo()))
        self.assertEqual(self.c.get(f'/orders/{o.pk}/').status_code,403)
        self.assertEqual(self.c.post(f'/orders/{o.pk}/',{'action':'cancel'}).status_code,403)
        self.assertEqual(self.c.get(f'/messages/{o.thread.pk}/').status_code,403)
        self.assertEqual(self.c.post(f'/messages/{o.thread.pk}/',{'text':'Intrusion'}).status_code,403)
        self.assertEqual(self.c.get(f'/media/evidence/{o.evidence.first().pk}/').status_code,403)
        # Read the FileResponse to the end so the test client closes the file; otherwise Windows cannot delete the temp media folder.
        r=self.b.get(f'/media/evidence/{o.evidence.first().pk}/');self.assertEqual(r.status_code,200);self.assertTrue(r.getvalue())
        self.assertEqual(Client().get(f'/media/evidence/{o.evidence.first().pk}/').status_code,403)
        self.assertEqual(self.c.get('/admin/').status_code,302)
        self.assertEqual(self.c.post(f'/orders/{o.pk}/review/',{'rating':5,'text':'fake'}).status_code,403)
    def test_owner_edits_only_and_private_email(self):
        self.assertEqual(self.b.get(f'/items/{self.item.pk}/edit/').status_code,404)
        self.assertNotContains(Client().get(f'/people/{self.owner.pk}/'),self.owner.email)
        self.assertNotContains(Client().get(f'/items/{self.item.pk}/'),self.owner.email)
    def test_restricted_account_blocked_immediately(self):
        self.owner.profile.restricted=True;self.owner.profile.save()
        self.assertEqual(self.a.get('/my/').status_code,302)
        self.assertNotContains(Client().get('/'),'Campus camera')
        self.assertEqual(Client().get(f'/items/{self.item.pk}/').status_code,404)
    def test_upload_validation(self):
        for f in [SimpleUploadedFile('x.svg',b'<svg/>',content_type='image/svg+xml'),SimpleUploadedFile('bad.jpg',b'not image',content_type='image/jpeg'),SimpleUploadedFile('large.jpg',b'x'*(5*1024*1024+1),content_type='image/jpeg')]:
            with self.assertRaises(ValidationError): clean_image(f)
        result=clean_image(photo());self.assertEqual(Image.open(result).format,'JPEG')
    def test_day_rounding_invalid_intervals(self):
        self.assertEqual(interval(self.start,self.start+timedelta(seconds=1)),1)
        self.assertEqual(interval(self.start,self.start+timedelta(hours=24)),1)
        self.assertEqual(interval(self.start,self.start+timedelta(hours=24,seconds=1)),2)
        for end in (self.start,self.start-timedelta(seconds=1)):
            with self.assertRaises(ValidationError): interval(self.start,end)
    def test_review_requires_completion_and_once(self):
        o=self.booking();self.b.post(f'/orders/{o.pk}/review/',{'rating':5,'text':'too early'});self.assertFalse(Review.objects.exists())
        act(o.pk,self.owner,'accept');act(o.pk,self.owner,'handover');act(o.pk,self.borrower,'handover');act(o.pk,self.owner,'return');act(o.pk,self.borrower,'return')
        for _ in range(2): self.b.post(f'/orders/{o.pk}/review/',{'rating':5,'text':'good'})
        self.assertEqual(Review.objects.count(),1)
    def test_filters_wanted_offers_and_chats(self):
        self.assertContains(Client().get('/',{'q':'camera','category':'tech','price':'20'}),'Campus camera')
        self.assertNotContains(Client().get('/',{'price':'0'}),'Campus camera')
        wanted=Wanted.objects.create(owner=self.borrower,title='Need camera',category='tech',description='For project',start=self.start,end=self.end,budget=20,location='AC1')
        self.assertEqual(self.a.post(f'/wanted/{wanted.pk}/',{'item':self.item.pk,'text':'Try mine'}).status_code,302)
        self.assertEqual(wanted.offers.count(),1)
        self.assertEqual(self.c.post(f'/wanted/{wanted.pk}/',{'item':self.item.pk}).status_code,404)
        self.b.post(f'/items/{self.item.pk}/contact/');thread=Thread.objects.get(item=self.item)
        self.b.post(f'/messages/{thread.pk}/',{'text':'Hello <script>alert(1)</script>'})
        self.assertContains(self.a.get(f'/messages/{thread.pk}/'),'&lt;script&gt;')
        self.assertTrue(Notification.objects.filter(user=self.owner).exists())
    def test_dispute_resolution_requires_admin_and_bilateral_return(self):
        o=self.booking();act(o.pk,self.owner,'accept');act(o.pk,self.owner,'handover');act(o.pk,self.borrower,'handover');act(o.pk,self.borrower,'dispute')
        with self.assertRaises(PermissionDenied): resolve_dispute(o.pk,self.owner,'completed')
        admin=User.objects.create_superuser('moderator','admin@example.org','not-a-school-password')
        with self.assertRaises(ValidationError): resolve_dispute(o.pk,admin,'completed')
        act(o.pk,self.owner,'return');act(o.pk,self.borrower,'return');o.refresh_from_db();self.assertEqual(o.status,'disputed')
        resolve_dispute(o.pk,admin,'completed');o.refresh_from_db();self.assertEqual(o.status,'completed')
    def test_all_pages_render_both_languages(self):
        o=self.booking();wanted=Wanted.objects.create(owner=self.borrower,title='Need',category='tech',description='Testing',start=self.start,end=self.end,budget=5,location='AC1')
        for language in ('en','zh'):
            self.a.post('/language/',{'lang':language})
            for url in ('/','/?tab=wanted','/login/','/rules/','/items/new/',f'/items/{self.item.pk}/',f'/items/{self.item.pk}/edit/','/wanted/new/',f'/wanted/{wanted.pk}/','/my/','/messages/',f'/messages/{o.thread.pk}/','/profile/',f'/people/{self.owner.pk}/',f'/orders/{o.pk}/',f'/report/item/{self.item.pk}/'):
                self.assertEqual(self.a.get(url).status_code,200,(url,language))
        for action,user in [('accept',self.owner),('handover',self.owner),('handover',self.borrower),('return',self.owner),('return',self.borrower)]:
            act(o.pk,user,action);self.assertEqual(self.a.get(f'/orders/{o.pk}/').status_code,200)
    def test_csrf_enforced(self):
        c=Client(enforce_csrf_checks=True);c.force_login(self.owner)
        self.assertEqual(c.post('/items/new/',{}).status_code,403)
        self.assertEqual(c.post('/login/',{'email':'x@my.cityu.edu.hk'}).status_code,403)
    def test_overdue_hours(self):
        o=self.booking();act(o.pk,self.owner,'accept')
        Order.objects.filter(pk=o.pk).update(start=timezone.now()-timedelta(days=2),end=timezone.now()-timedelta(hours=2,minutes=5))
        o.refresh_from_db();self.assertEqual(o.overdue,3)

class SimultaneousAcceptance(TransactionTestCase):
    def test_two_simultaneous_accepts_exactly_one_wins(self):
        owner=make_user('concurrent-owner');borrower=make_user('concurrent-borrower');item=make_item(owner)
        start=timezone.now()+timedelta(days=1);end=start+timedelta(days=1)
        a=apply(item.pk,borrower,start,end);b=apply(item.pk,borrower,start,end)
        barrier=Barrier(2)
        def accept(pk):
            close_old_connections();barrier.wait()
            try: act(pk,User.objects.get(pk=owner.pk),'accept');return 'accepted'
            except ValidationError:return 'conflict'
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(accept,[a.pk,b.pk]))
        self.assertCountEqual(results,['accepted','conflict'])
        self.assertEqual(Order.objects.filter(item=item,status='accepted').count(),1)

def completed(item,borrower):
    start=timezone.now()-timedelta(days=3)
    return Order.objects.create(item=item,borrower=borrower,start=start,end=start+timedelta(days=1),status='completed',rent=0,deposit=0)

class ImpactReport(TestCase):
    def setUp(self): self.owner=make_user('lender');self.borrower=make_user('student')
    def test_counts_only_completed_borrows_with_sourced_factors(self):
        tech=make_item(self.owner);book=make_item(self.owner);misc=make_item(self.owner)
        Item.objects.filter(pk=book.pk).update(category='study');Item.objects.filter(pk=misc.pk).update(category='other')
        for item in (tech,book,misc): completed(Item.objects.get(pk=item.pk),self.borrower)
        apply(tech.pk,self.borrower,timezone.now()+timedelta(days=5),timezone.now()+timedelta(days=6))
        s=impact_summary()
        self.assertEqual(s['borrows'],3)
        # 98 kg x 25% (tech) + 1.2 kg x 25% (study); 'other' has no sourced factor and is left out.
        self.assertEqual(s['total_kg'],Decimal('24.8'))
        self.assertIsNone({r['key']:r for r in s['rows']}['other']['kg'])
    @override_settings(CARBON_AVOIDED_PURCHASE_RATE='0.5')
    def test_rate_is_configurable(self):
        completed(make_item(self.owner),self.borrower);self.assertEqual(impact_summary()['total_kg'],Decimal('49.0'))
    def test_public_page(self):
        r=Client().get('/impact/');self.assertContains(r,'kg CO₂e');self.assertContains(r,'25%')

class PurchaseSurvey(TestCase):
    def setUp(self):
        self.owner=make_user('lender');self.borrower=make_user('student');self.order=completed(make_item(self.owner),self.borrower)
        self.url=f'/orders/{self.order.pk}/survey/';self.a=Client();self.b=Client();self.a.force_login(self.owner);self.b.force_login(self.borrower)
    def test_only_borrower_once_after_completion(self):
        page=f'/orders/{self.order.pk}/';question='你會買一件新的嗎'
        self.assertContains(self.b.get(page),question);self.assertNotContains(self.a.get(page),question)
        outsider=Client();outsider.force_login(make_user('outsider'))
        for client,status in ((self.a,403),(outsider,403),(Client(),302)): self.assertEqual(client.post(self.url,{'answer':'yes'}).status_code,status)
        pending=apply(self.order.item_id,self.borrower,timezone.now()+timedelta(days=5),timezone.now()+timedelta(days=6))
        self.b.post(f'/orders/{pending.pk}/survey/',{'answer':'yes'});self.b.post(self.url,{'answer':'maybe'})
        self.assertFalse(Survey.objects.exists())
        for answer in ('no','yes'): self.assertEqual(self.b.post(self.url,{'answer':answer}).status_code,302)
        self.assertEqual(list(Survey.objects.values_list('order','answer')),[(self.order.pk,'no')])
        with self.assertRaises(IntegrityError), transaction.atomic(): Survey.objects.create(order=self.order,answer='yes')
        self.assertNotContains(self.b.get(page),question)
        self.b.post('/language/',{'lang':'en'});self.assertContains(self.b.get(page),'Thanks! Your answer')
    def test_survey_rate_replaces_default_at_threshold(self):
        others=[completed(self.order.item,self.borrower) for _ in range(30)]
        Survey.objects.bulk_create([Survey(order=o,answer=a) for o,a in zip(others,['yes']*11+['no']*18+['unsure'])])
        s=impact_summary()
        # 29 yes/no answers: still below 30, so the configured 25% stays; 'not sure' never counts toward the rate.
        self.assertEqual((s['rate_percent'],s['survey']['used'],s['survey']['total']),(25,False,30))
        self.assertEqual(s['total_kg'],Decimal('759.5'));self.assertContains(Client().get('/impact/'),'29/30')
        self.b.post(self.url,{'answer':'yes'})
        s=impact_summary()
        # 12 yes / (12 + 18) = 40%, applied to 31 completed tech borrows at 98 kg.
        self.assertEqual((s['rate_percent'],s['survey']['used'],s['survey']['counted']),(40,True,30))
        self.assertEqual(s['total_kg'],Decimal('1215.2'));self.assertContains(Client().get('/impact/'),'根據 30 個「會／不會」回答')
        c=Client();c.post('/language/',{'lang':'en'});self.assertContains(c.get('/impact/'),'based on 30 yes/no answers')

REPLY='草稿如下：\n```json\n{"title":"  入門單反相機  ","category":"weapons","description":"黑色相機，附鏡頭。","condition":"九成新","daily":"-5","extra":"ignored"}\n```'

@override_settings(AI_API_KEY='test-key')
class AIDraft(TestCase):
    def setUp(self): self.user=make_user('poster');self.c=Client();self.c.force_login(self.user)
    @override_settings(AI_API_KEY='')
    def test_off_without_key(self):
        self.assertNotContains(self.c.get('/items/new/'),'ai-panel')
        self.assertEqual(self.c.post('/items/ai-draft/',{'photo':photo()}).status_code,404)
    def test_reply_is_sanitised(self):
        with mock.patch('market.ai.ask_model',return_value=REPLY) as ask:
            r=self.c.post('/items/ai-draft/',{'photo':photo()})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['draft'],{'title':'入門單反相機','category':'other','description':'黑色相機，附鏡頭。','condition':'九成新','daily':''})
        # Zhipu gets raw base64 of the server re-encoded JPEG, never the original upload.
        self.assertTrue(base64.b64decode(ask.call_args.args[0]).startswith(b'\xff\xd8'))
    def test_valid_price_kept(self):
        with mock.patch('market.ai.ask_model',return_value='{"title":"Tent","category":"outdoor","daily":12}'):
            d=self.c.post('/items/ai-draft/',{'photo':photo()}).json()['draft']
        self.assertEqual((d['category'],d['daily']),('outdoor','12.00'))
    def test_model_failure_and_missing_photo(self):
        with mock.patch('market.ai.ask_model',side_effect=OSError('timeout')):
            self.assertContains(self.c.post('/items/ai-draft/',{'photo':photo()}),'AI',status_code=400)
        self.assertEqual(self.c.post('/items/ai-draft/').status_code,400)
    def test_panel_and_access(self):
        self.assertContains(self.c.get('/items/new/'),'ai-panel')
        self.assertNotContains(self.c.get(f'/items/{make_item(self.user).pk}/edit/'),'ai-panel')
        c=Client();c.force_login(make_user('pending',False))
        self.assertEqual(c.post('/items/ai-draft/',{'photo':photo()}).status_code,403)
        self.assertEqual(Client().post('/items/ai-draft/').status_code,302)

DB_STORAGE={'default':{'BACKEND':'market.dbstorage.DatabaseStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}

# The whole flow again with photos kept in the database (MEDIA_STORAGE=db, used on Render free).
@override_settings(STORAGES=DB_STORAGE)
class CampusFlowDatabaseStorage(CampusFlow):
    def test_item_photo_stored_served_and_removed(self):
        d={'title':'Lamp','category':'home','description':'Desk lamp','condition':'Good','daily':'5','deposit':'20','available_start':self.start.strftime('%Y-%m-%dT%H:%M'),'available_end':(self.end+timedelta(days=5)).strftime('%Y-%m-%dT%H:%M'),'max_days':'7','location':'Hall','status':'listed','photo':photo()}
        self.assertEqual(self.a.post('/items/new/',d).status_code,302)
        item=Item.objects.get(title='Lamp');p=item.photos.get()
        self.assertTrue(StoredFile.objects.filter(name=p.image.name).exists())
        r=Client().get(f'/media/item/{p.pk}/');self.assertEqual(r.status_code,200);self.assertTrue(r.getvalue().startswith(b'\xff\xd8'))
        d.update(photo='',remove_photos=[p.pk])
        with self.captureOnCommitCallbacks(execute=True): self.assertEqual(self.a.post(f'/items/{item.pk}/edit/',d).status_code,302)
        self.assertFalse(StoredFile.objects.exists())
        self.assertEqual(Client().get(f'/media/item/{p.pk}/').status_code,404)

@override_settings(EMAIL_BACKEND='market.mail.ResendBackend',RESEND_API_KEY='re_test',MAIL_LIVE=True,DEFAULT_FROM_EMAIL='Box Box Share <onboarding@resend.dev>')
class ResendMail(TestCase):
    def test_login_link_sent_through_api(self):
        with mock.patch('market.mail.urlopen') as urlopen:
            r=Client().post('/login/',{'email':'amy@my.cityu.edu.hk'})
        self.assertContains(r,'已建立登入郵件，請查收')
        req=urlopen.call_args.args[0];body=json.loads(req.data)
        self.assertEqual((req.full_url,req.get_header('Authorization')),('https://api.resend.com/emails','Bearer re_test'))
        self.assertEqual((body['to'],body['from']),(['amy@my.cityu.edu.hk'],'Box Box Share <onboarding@resend.dev>'))
        self.assertRegex(body['text'],r'http://testserver/verify/\S+/')
    def test_api_failure_reported_and_token_discarded(self):
        with mock.patch('market.mail.urlopen',side_effect=OSError('403')):
            r=Client().post('/login/',{'email':'amy@my.cityu.edu.hk'})
        self.assertContains(r,'郵件服務暫時無法使用')
        self.assertFalse(LoginToken.objects.exists())

class SecurityHeaders(TestCase):
    def test_csp_and_permissions_policy(self):
        r=Client().get('/rules/')
        self.assertIn("script-src 'self'",r['Content-Security-Policy']);self.assertIn('camera=()',r['Permissions-Policy'])

def soon(days=3): return (timezone.now()+timedelta(days=days)).replace(second=0,microsecond=0)
def logged_in(user):
    c=Client();c.force_login(user);return c

class Buddy(TestCase):
    def setUp(self):
        self.host=make_user('hostess');self.ann=make_user('annie');self.bob=make_user('bobby');self.cat=make_user('cathy')
        self.ch,self.ca,self.cb,self.cc=(logged_in(u) for u in (self.host,self.ann,self.bob,self.cat))
        self.data={'category':'team','kind':'hackathon','title':'HK Hackathon 2026','description':'Need a frontend developer','starts':soon().strftime('%Y-%m-%dT%H:%M'),'location':'CityU AC1','capacity':'1','skills':'React','languages':'English, 廣東話'}
    def new_post(self,**extra):
        self.assertEqual(self.ch.post('/buddy/new/',{**self.data,**extra}).status_code,302)
        return BuddyPost.objects.latest('pk')
    def act(self,client,post,action,**data): return client.post(f'/buddy/{post.pk}/',{'action':action,**data})
    def notes(self,user,url): return Notification.objects.filter(user=user,url=url).count()
    def test_apply_withdraw_approve_capacity_and_close(self):
        post=self.new_post();url=f'/buddy/{post.pk}/'
        self.assertEqual((post.owner,post.capacity,post.state()),(self.host,1,'open'))
        self.assertContains(Client().get('/buddy/'),'HK Hackathon 2026');self.assertContains(Client().get('/buddy/?category=team'),'HK Hackathon 2026')
        self.assertNotContains(Client().get('/buddy/?category=buddy'),'HK Hackathon 2026')
        self.act(self.ch,post,'apply');self.assertFalse(post.applications.exists())
        self.act(self.ca,post,'apply',message='I build with React');self.act(self.ca,post,'apply',message='again')
        self.assertEqual(post.applications.count(),1);self.assertEqual(self.notes(self.host,url),1)
        self.act(self.cb,post,'apply')
        a,b=post.applications.order_by('pk')
        # Only the host manages applications; nobody reads a Buddy chat before being accepted.
        for client in (self.ca,self.cc): self.assertEqual(self.act(client,post,'accept',application=b.pk).status_code,403)
        self.assertEqual(self.act(self.ca,post,'close').status_code,403)
        self.assertFalse(Thread.objects.filter(buddy=post).exists())
        self.act(self.ch,post,'accept',application=a.pk)
        a.refresh_from_db();self.assertEqual(a.status,'accepted');self.assertEqual(self.notes(self.ann,url),1)
        thread=Thread.objects.get(buddy=post);self.assertEqual((thread.first,thread.second),(self.ann,self.host))
        self.assertContains(self.ca.get(url),f'/messages/{thread.pk}/');self.assertContains(self.ch.get(url),f'/messages/{thread.pk}/')
        self.assertEqual(self.cb.get(f'/messages/{thread.pk}/').status_code,403);self.assertEqual(self.cb.post(f'/messages/{thread.pk}/',{'text':'peek'}).status_code,403)
        self.ca.post(f'/messages/{thread.pk}/',{'text':'See you at AC1'});self.assertEqual(thread.messages.count(),1)
        self.assertNotContains(self.cb.get(url),'See you at AC1');self.assertNotContains(self.cb.get(url),f'/people/{self.ann.pk}/')
        # Full: no more accepts, no new applications.
        self.assertEqual(post.state(),'full');self.assertContains(self.ch.post(url,{'action':'accept','application':b.pk},follow=True),'名額已滿')
        b.refresh_from_db();self.assertEqual(b.status,'pending')
        self.act(self.cc,post,'apply');self.assertFalse(post.applications.filter(user=self.cat).exists())
        self.assertContains(Client().get('/buddy/',{'state':'full'}),'HK Hackathon 2026');self.assertNotContains(Client().get('/buddy/',{'state':'open'}),'HK Hackathon 2026')
        # Leaving frees the spot and closes the member's chat; history stays.
        self.act(self.ca,post,'withdraw');a.refresh_from_db();self.assertEqual(a.status,'withdrawn');self.assertEqual(post.state(),'open')
        self.assertEqual(Notification.objects.filter(user=self.host,url=url,text__contains='退出').count(),1)
        self.ca.post(f'/messages/{thread.pk}/',{'text':'still here?'});self.assertEqual(thread.messages.count(),1)
        self.assertContains(self.ca.get(f'/messages/{thread.pk}/'),'See you at AC1')
        self.act(self.ca,post,'apply');a.refresh_from_db();self.assertEqual(a.status,'pending')
        self.act(self.ch,post,'accept',application=b.pk);b.refresh_from_db();self.assertEqual(b.status,'accepted')
        self.act(self.ch,post,'decline',application=a.pk);a.refresh_from_db();self.assertEqual(a.status,'declined')
        self.act(self.ca,post,'apply');a.refresh_from_db();self.assertEqual(a.status,'declined')
        BuddyPost.objects.filter(pk=post.pk).update(capacity=2)
        self.act(self.cc,post,'apply');self.act(self.ch,post,'close')
        post.refresh_from_db();self.assertEqual(post.state(),'closed');self.assertEqual(post.applications.get(user=self.cat).status,'declined')
        self.assertEqual(post.applications.get(user=self.bob).status,'accepted')
        self.assertNotContains(Client().get('/buddy/'),'HK Hackathon 2026');self.assertContains(Client().get('/buddy/',{'state':'closed'}),'HK Hackathon 2026')
        self.act(self.ch,post,'reopen');post.refresh_from_db();self.assertEqual(post.state(),'open')
        self.act(self.ch,post,'remove',application=b.pk);b.refresh_from_db();self.assertEqual(b.status,'removed')
        self.assertEqual(self.cb.post(f'/report/buddy/{post.pk}/',{'reason':'Spam recruitment'}).status_code,302);self.assertEqual(Report.objects.get().kind,'buddy')
    def test_form_rules_edit_and_filters(self):
        r=self.ch.post('/buddy/new/',{**self.data,'category':'buddy','kind':'hackathon','starts':(timezone.now()-timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),'ends':(timezone.now()-timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),'capacity':'0'})
        for text in ('類型與類別不符','開始時間須在未來','結束時間須晚於開始時間'): self.assertContains(r,text)
        self.assertFalse(BuddyPost.objects.exists())
        post=self.new_post(capacity='2');self.act(self.ca,post,'apply');self.act(self.ch,post,'accept',application=post.applications.get().pk)
        self.act(self.cb,post,'apply');self.act(self.ch,post,'accept',application=post.applications.get(user=self.bob).pk)
        self.assertContains(self.ch.post(f'/buddy/{post.pk}/edit/',{**self.data,'capacity':'1'}),'名額不能少於此數')
        self.assertEqual(self.ch.post(f'/buddy/{post.pk}/edit/',{**self.data,'title':'Hackathon crew','capacity':'3'}).status_code,302)
        post.refresh_from_db();self.assertEqual((post.title,post.capacity),('Hackathon crew',3))
        self.assertEqual(self.ca.get(f'/buddy/{post.pk}/edit/').status_code,404);self.assertEqual(self.ca.post(f'/buddy/{post.pk}/edit/',self.data).status_code,404)
        self.assertEqual(logged_in(make_user('unverified',False)).get('/buddy/new/').status_code,403);self.assertEqual(Client().get('/buddy/new/').status_code,302)
        study=self.new_post(category='buddy',kind='study',title='Library revision',starts=soon(20).strftime('%Y-%m-%dT%H:%M'),location='Run Run Shaw Library')
        page=lambda **q: Client().get('/buddy/',q).content.decode()
        self.assertIn('Library revision',page(q='revision'));self.assertNotIn('Hackathon crew',page(q='revision'))
        self.assertIn('Library revision',page(kind='study'));self.assertNotIn('Library revision',page(kind='hackathon'))
        self.assertIn('Hackathon crew',page(when='week'));self.assertNotIn('Library revision',page(when='week'));self.assertIn('Library revision',page(when='month'))
        BuddyPost.objects.filter(pk=study.pk).update(starts=timezone.now()-timedelta(days=1))
        self.assertNotIn('Library revision',page());self.assertIn('Library revision',page(state='ended'))
        self.act(self.cc,BuddyPost.objects.get(pk=study.pk),'apply');self.assertFalse(BuddyApplication.objects.filter(user=self.cat).exists())
    def test_my_activity_keeps_orders_and_adds_buddy(self):
        item=make_item(self.host);start=soon();order=apply(item.pk,self.ann,start,start+timedelta(days=1))
        post=self.new_post(capacity='2');self.act(self.ca,post,'apply');other=self.new_post(title='Badminton',category='buddy',kind='sports')
        self.act(self.ca,other,'apply');self.act(self.ch,other,'accept',application=other.applications.get().pk)
        page=self.ca.get('/my/').content.decode()
        for text in ('我的借出與借入訂單','我的借出物品','我的尋物','我發布的招募','我的申請','我已加入',f'/orders/{order.pk}/'): self.assertIn(text,page)
        joined=page.split('我已加入')[1];self.assertIn('Badminton',joined);self.assertNotIn('HK Hackathon 2026',joined)
        self.assertIn('HK Hackathon 2026',page.split('我的申請')[1].split('我已加入')[0])
        self.assertNotIn('HK Hackathon 2026',page.split('我的借出與借入訂單')[1].split('我的借出物品')[0])
        self.assertIn('待審 1',self.ch.get('/my/').content.decode())
    def test_pages_render_in_all_languages_and_mobile_nav(self):
        post=self.new_post();self.act(self.ca,post,'apply');self.act(self.ch,post,'accept',application=post.applications.get().pk)
        thread=Thread.objects.get(buddy=post)
        for lang in ('en','zh','hans'):
            for client in (self.ch,self.ca):
                client.post('/language/',{'lang':lang})
                for url in ('/','/?tab=wanted','/impact/','/buddy/','/buddy/?category=buddy&state=all','/buddy/new/',f'/buddy/{post.pk}/','/my/','/messages/',f'/messages/{thread.pk}/','/profile/',f'/people/{self.host.pk}/','/rules/',f'/report/buddy/{post.pk}/'):
                    self.assertEqual(client.get(url).status_code,200,(url,lang))
            self.assertEqual(self.ch.get(f'/buddy/{post.pk}/edit/').status_code,200)
        nav=self.ca.get('/').content.decode().split('<nav')[1].split('</nav>')[0]
        order=[nav.index(f'href="{h}"') for h in ('/','/?tab=wanted','/impact/','/buddy/','/my/','/messages/')]
        self.assertEqual(order,sorted(order))

class BuddyRace(TransactionTestCase):
    def test_simultaneous_accepts_never_exceed_capacity(self):
        host=make_user('race-host');people=[make_user(f'racer{i}') for i in range(2)]
        post=BuddyPost.objects.create(owner=host,category='buddy',kind='sports',title='Tennis',description='x',starts=soon(),location='Court',capacity=1)
        apps=[BuddyApplication.objects.create(post=post,user=u) for u in people]
        barrier=Barrier(2)
        def accept(pk):
            close_old_connections();barrier.wait()
            try: social.decide(post.pk,User.objects.get(pk=host.pk),pk,True);return 'accepted'
            except ValidationError: return 'full'
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(accept,[a.pk for a in apps]))
        self.assertCountEqual(results,['accepted','full']);self.assertEqual(post.applications.filter(status='accepted').count(),1)

class Friends(TestCase):
    def setUp(self):
        self.a=make_user('alice');self.b=make_user('brian');self.c=make_user('carol')
        self.ca,self.cb,self.cc=(logged_in(u) for u in (self.a,self.b,self.c))
    def act(self,client,user,action,**extra): return client.post(f'/people/{user.pk}/friend/',{'action':action,**extra})
    def test_request_accept_chat_remove(self):
        self.act(self.ca,self.b,'request');self.act(self.ca,self.b,'request')
        self.assertEqual(Friendship.objects.get().status,'pending');self.assertEqual(Notification.objects.filter(user=self.b,text__contains='好友申請').count(),1)
        inbox=self.cb.get('/messages/').content.decode();self.assertIn('好友申請',inbox);self.assertIn('alice',inbox)
        self.assertEqual(self.act(self.ca,self.b,'chat').status_code,403)
        self.act(self.cc,self.b,'accept');self.assertEqual(Friendship.objects.get().status,'pending')
        self.act(self.cb,self.a,'accept');self.assertEqual(Friendship.objects.get().status,'accepted')
        self.assertEqual(Notification.objects.filter(user=self.a,text__contains='已獲接受').count(),1)
        self.assertContains(self.ca.get('/messages/'),f'/people/{self.b.pk}/')
        r=self.act(self.ca,self.b,'chat');thread=Thread.objects.get(item=None,order=None,buddy=None)
        self.assertRedirects(r,f'/messages/{thread.pk}/');self.assertEqual(self.act(self.cb,self.a,'chat').url,f'/messages/{thread.pk}/')
        self.ca.post(f'/messages/{thread.pk}/',{'text':'Lunch?'});self.cb.post(f'/messages/{thread.pk}/',{'text':'Sure'})
        self.assertEqual(thread.messages.count(),2)
        for method in ('get','post'): self.assertEqual(getattr(self.cc,method)(f'/messages/{thread.pk}/',{'text':'hi'} if method=='post' else None).status_code,403)
        self.assertContains(self.cb.get('/messages/'),f'/messages/{thread.pk}/')
        self.act(self.cb,self.a,'remove',next='/messages/#friends');self.assertFalse(Friendship.objects.exists())
        self.ca.post(f'/messages/{thread.pk}/',{'text':'?'});self.assertEqual(thread.messages.count(),2)
        self.assertContains(self.ca.get(f'/messages/{thread.pk}/'),'Lunch?')
    def test_decline_cancel_crossing_and_no_automatic_friends(self):
        self.act(self.ca,self.b,'request');self.act(self.cb,self.a,'decline')
        self.assertEqual(Friendship.objects.get().status,'declined');self.assertContains(self.ca.get(f'/people/{self.b.pk}/'),'對方暫未接受')
        self.act(self.ca,self.b,'request');self.assertEqual(Notification.objects.filter(user=self.b,text__contains='好友申請').count(),1)
        self.act(self.cb,self.a,'request');f=Friendship.objects.get();self.assertEqual((f.sender,f.status),(self.b,'pending'))
        self.act(self.cb,self.a,'cancel');self.assertFalse(Friendship.objects.exists())
        self.act(self.ca,self.c,'request');self.act(self.cc,self.a,'request');self.assertEqual(Friendship.objects.get().status,'accepted')
        self.act(self.ca,self.a,'request');self.assertEqual(Friendship.objects.filter(sender=self.a,recipient=self.a).count(),0)
        # Finishing a borrow or a Buddy activity together never makes anyone friends.
        item=make_item(self.b);start=soon();o=apply(item.pk,self.a,start,start+timedelta(days=1))
        for actor,action in ((self.b,'accept'),(self.b,'handover'),(self.a,'handover'),(self.a,'return'),(self.b,'return')): act(o.pk,actor,action)
        post=BuddyPost.objects.create(owner=self.b,category='buddy',kind='meal',title='Dinner',description='x',starts=soon(),location='Canteen',capacity=2)
        social.apply(post.pk,self.a,'');social.decide(post.pk,self.b,post.applications.get().pk,True)
        self.assertFalse(social.are_friends(self.a,self.b));self.assertFalse(Friendship.objects.filter(sender__in=[self.a,self.b],recipient__in=[self.a,self.b]).exists())
    def test_public_page_privacy(self):
        Profile.objects.filter(user=self.b).update(bio='Year 2 EE',skills='Python',languages='English')
        anon=Client().get(f'/people/{self.b.pk}/').content.decode()
        self.assertNotIn('Year 2 EE',anon);self.assertNotIn(self.b.email,anon);self.assertNotIn('加好友',anon)
        page=self.ca.get(f'/people/{self.b.pk}/').content.decode()
        self.assertIn('Year 2 EE',page);self.assertIn('加好友',page);self.assertNotIn(self.b.email,page)

@override_settings(STORAGES=DB_STORAGE)
class ProfilePage(TestCase):
    def test_profile_opens_after_avatar_upload_and_saves_buddy_fields(self):
        # Regression: with MEDIA_STORAGE=db (Render), /profile/ crashed once an avatar existed.
        u=make_user('avatar');c=logged_in(u)
        self.assertEqual(c.get('/profile/').status_code,200)
        r=c.post('/profile/',{'nickname':'Ava','avatar':photo(),'bio':'Likes hiking','interests':'行山','skills':'Figma','languages':'English, 普通話'})
        self.assertEqual(r.status_code,302);p=Profile.objects.get(user=u);self.assertTrue(p.avatar)
        self.assertTrue(StoredFile.objects.filter(name=p.avatar.name).exists())
        page=c.get('/profile/');self.assertEqual(page.status_code,200);self.assertContains(page,f'/media/avatar/{u.pk}/');self.assertNotContains(page,u.email)
        self.assertEqual((p.nickname,p.bio,p.languages),('Ava','Likes hiking','English, 普通話'))
        old=p.avatar.name
        with self.captureOnCommitCallbacks(execute=True): c.post('/profile/',{'nickname':'Ava','remove_avatar':'on'})
        p.refresh_from_db();self.assertFalse(p.avatar);self.assertFalse(StoredFile.objects.filter(name=old).exists())
        self.assertEqual(c.get('/profile/').status_code,200)

class Languages(TestCase):
    def setUp(self): self.u=make_user('linguist');self.c=logged_in(self.u)
    def test_three_languages_menu_cookie_and_return_to_same_page(self):
        r=self.c.get('/');self.assertContains(r,'lang="zh-Hant"');self.assertContains(r,'尋物廣場')
        for code,label in i18n.LANGUAGES: self.assertContains(r,f'value="{code}"')
        r=self.c.post('/language/',{'lang':'hans','next':'/buddy/?category=team&q=AI'})
        self.assertRedirects(r,'/buddy/?category=team&q=AI',fetch_redirect_response=False)
        page=self.c.get('/buddy/?category=team&q=AI');self.assertContains(page,'lang="zh-Hans"');self.assertContains(page,'寻物广场');self.assertContains(page,'消息');self.assertContains(page,'value="AI"')
        self.assertRedirects(self.c.post('/language/',{'lang':'en','next':'https://evil.example/'}),'/',fetch_redirect_response=False)
        page=self.c.get('/');self.assertContains(page,'lang="en"');self.assertContains(page,'Seeking');self.assertContains(page,'Buddy')
        # The choice survives signing out (the session is flushed; the cookie stays).
        self.c.post('/language/',{'lang':'hans'});self.c.post('/logout/')
        self.assertContains(self.c.get('/'),'lang="zh-Hans"')
    def test_messages_errors_notifications_translated_but_user_text_untouched(self):
        BuddyPost.objects.create(owner=make_user('poster'),category='buddy',kind='study',title='溫書搭子 國際',description='一起溫書',starts=soon(),location='圖書館',capacity=2)
        self.c.post('/language/',{'lang':'hans'})
        page=self.c.get('/buddy/').content.decode();self.assertIn('溫書搭子 國際',page);self.assertIn('学习',page)
        r=self.c.post('/buddy/new/',{'category':'buddy','kind':'study','title':'x','description':'x','starts':'2000-01-01T10:00','location':'x','capacity':'1'})
        self.assertContains(r,'开始时间须在未来');self.assertNotContains(r,'Must be in the future')
        other=make_user('friendly');logged_in(other).post(f'/people/{self.u.pk}/friend/',{'action':'request'})
        self.assertContains(self.c.get('/messages/'),'收到好友申请')
        self.c.post('/language/',{'lang':'en'})
        inbox=self.c.get('/messages/');self.assertContains(inbox,'New friend request');self.assertNotContains(inbox,'收到好友申請')
        r=self.c.post('/buddy/new/',{'category':'buddy','kind':'study','title':'x','description':'x','starts':'2000-01-01T10:00','location':'x','capacity':'1'})
        self.assertContains(r,'Must be in the future');self.assertContains(r,'People needed (not counting you)')
    def test_pick_rules(self):
        for lang,want in (('en','Pending'),('zh','待確認'),('hans','待确认')): self.assertEqual(i18n.loc('待確認 / Pending',lang),want)
        self.assertEqual(i18n.loc('Too many requests. Try later / 請稍後再試','en'),'Too many requests. Try later')
        self.assertEqual(i18n.loc('A / 甲; B / 乙','zh'),'甲; 乙');self.assertEqual(i18n.loc('Hackathon','hans'),'Hackathon')
        self.assertEqual(i18n.loc('物品 / Item',None),'物品 / Item')

class MigrationKeepsData(TransactionTestCase):
    def test_0005_preserves_users_items_orders_and_messages(self):
        executor=MigrationExecutor(connection)
        old=[('market','0004_stored_file')];new=[('market','0005_buddy_friends_profile')]
        executor.migrate(old);apps=executor.loader.project_state(old).apps
        U=apps.get_model('auth','User');P=apps.get_model('market','Profile');I=apps.get_model('market','Item');O=apps.get_model('market','Order');T=apps.get_model('market','Thread');M=apps.get_model('market','Message')
        lender=U.objects.create(username='old@my.cityu.edu.hk',email='old@my.cityu.edu.hk');borrower=U.objects.create(username='b@my.cityu.edu.hk',email='b@my.cityu.edu.hk')
        P.objects.create(user=lender,nickname='Old lender',verified=True);P.objects.create(user=borrower,nickname='Old borrower',verified=True)
        now=timezone.now();item=I.objects.create(owner=lender,title='Old camera',category='tech',description='x',condition='ok',daily=5,deposit=0,available_start=now,available_end=now+timedelta(days=9),location='AC1')
        order=O.objects.create(item=item,borrower=borrower,start=now+timedelta(days=1),end=now+timedelta(days=2),status='completed',rent=5,deposit=0,snapshot={'title':'Old camera'})
        t1=T.objects.create(item=item,first=borrower,second=lender);t2=T.objects.create(order=order,first=borrower,second=lender)
        M.objects.create(thread=t1,sender=borrower,text='Is it free?');M.objects.create(thread=t2,sender=lender,text='Returned, thanks')
        executor=MigrationExecutor(connection);executor.migrate(new)
        self.assertEqual(Profile.objects.get(user__username='old@my.cityu.edu.hk').nickname,'Old lender')
        self.assertEqual((Item.objects.get().title,Order.objects.get().status,Order.objects.get().snapshot),('Old camera','completed',{'title':'Old camera'}))
        self.assertEqual(sorted(Message.objects.values_list('text',flat=True)),['Is it free?','Returned, thanks'])
        self.assertEqual(Thread.objects.filter(buddy__isnull=True).count(),2);self.assertEqual(Profile.objects.filter(bio='').count(),2)
        c=Client();c.force_login(User.objects.get(username='b@my.cityu.edu.hk'))
        inbox=c.get('/messages/');self.assertContains(inbox,'Old camera');self.assertEqual(c.get(f'/messages/{t1.pk}/').status_code,200)

