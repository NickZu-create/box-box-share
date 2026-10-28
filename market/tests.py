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
        c=Client();self.assertContains(c.post('/login/',{'email':'x@evilmy.cityu.edu.hk'}),'Only approved school email')
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
        self.assertContains(Client().post(path),'Expired or used link')
        raw=secrets.token_urlsafe(32)
        LoginToken.objects.create(email='old@my.cityu.edu.hk',digest=hashlib.sha256(raw.encode()).hexdigest(),expires=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError): consume_token(raw)
    def test_email_rate_limit(self):
        c=Client();c.post('/login/',{'email':'new@my.cityu.edu.hk'})
        self.assertContains(c.post('/login/',{'email':'new@my.cityu.edu.hk'}),'Too many requests')
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
        self.assertContains(self.b.post(f'/items/{self.item.pk}/',dates),'Listing terms changed')
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

class Social(TestCase):
    def setUp(self):
        self.a=make_user('amy');self.b=make_user('ben');self.c=make_user('cat')
        Profile.objects.update(social=True)
        self.ca,self.cb,self.cc=Client(),Client(),Client()
        for client,u in ((self.ca,self.a),(self.cb,self.b),(self.cc,self.c)): client.force_login(u)
        self.when=(timezone.now()+timedelta(days=3)).replace(second=0,microsecond=0)
    def post_buddy(self,client=None,**extra):
        d={'kind':'outdoor','title':'Weekend hike','description':'Easy trail, tent available','when':self.when.strftime('%Y-%m-%dT%H:%M'),'location':'Lion Rock','spots':'1','active':'on',**extra}
        self.assertEqual((client or self.ca).post('/buddies/new/',d).status_code,302)
        return Buddy.objects.latest('pk')
    def social(self,client,user,action): return client.post(f'/people/{user.pk}/social/',{'action':action})
    def test_buddy_join_accept_spots_and_chat(self):
        item=make_item(self.a);b=self.post_buddy(item=item.pk)
        self.assertContains(Client().get('/buddies/'),'Weekend hike');self.assertContains(self.cb.get(f'/items/{item.pk}/'),'Weekend hike')
        self.cb.post(f'/buddies/{b.pk}/',{'action':'join','text':'Count me in'});self.cc.post(f'/buddies/{b.pk}/',{'action':'join'})
        self.assertContains(self.cb.post(f'/buddies/{b.pk}/',{'action':'join'},follow=True),'Already asked to join')
        self.assertEqual(b.joins.count(),2);self.assertTrue(Notification.objects.filter(user=self.a,url=f'/buddies/{b.pk}/').exists())
        thread=Thread.objects.get(buddy=b,first=self.b);self.assertEqual(thread.messages.get().text,'Count me in')
        self.assertContains(self.ca.get(f'/messages/{thread.pk}/'),'Weekend hike')
        jb,jc=b.joins.order_by('pk')
        self.assertEqual(self.cb.post(f'/buddies/{b.pk}/',{'action':'accept','join':jb.pk}).status_code,403)
        self.ca.post(f'/buddies/{b.pk}/',{'action':'accept','join':jb.pk})
        self.assertContains(self.ca.post(f'/buddies/{b.pk}/',{'action':'accept','join':jc.pk},follow=True),'No spots left')
        self.assertEqual(list(b.joins.order_by('pk').values_list('status',flat=True)),['accepted','pending'])
        self.assertEqual(self.ca.post(f'/buddies/{b.pk}/',{'action':'decline','join':999}).status_code,404)
        self.ca.post(f'/buddies/{b.pk}/',{'action':'decline','join':jc.pk});declined=Thread.objects.get(buddy=b,first=self.c)
        self.cc.post(f'/messages/{declined.pk}/',{'text':'Please?'});self.assertFalse(declined.messages.exists())
        # Only the host and accepted buddies see who joined; others see the count.
        self.assertContains(self.cb.get(f'/buddies/{b.pk}/'),'這次的搭子');self.assertNotContains(self.cc.get(f'/buddies/{b.pk}/'),'這次的搭子')
        self.assertEqual(met_ids(self.b),{self.a.pk});self.assertEqual(met_ids(self.c),set())
        self.ca.post(f'/buddies/{b.pk}/',{'action':'join'});self.assertEqual(b.joins.count(),2)
        Buddy.objects.filter(pk=b.pk).update(when=timezone.now()-timedelta(hours=1))
        self.assertNotContains(Client().get('/buddies/'),'Weekend hike')
    def test_buddy_form_rules(self):
        other=make_item(self.b)
        r=self.ca.post('/buddies/new/',{'kind':'study','title':'Past','description':'x','when':(timezone.now()-timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),'location':'Library','spots':'2','item':other.pk})
        self.assertContains(r,'Must be in the future');self.assertFalse(Buddy.objects.exists())
        # Someone else's item cannot be attached.
        self.assertContains(self.ca.post('/buddies/new/',{'kind':'study','title':'x','description':'x','when':self.when.strftime('%Y-%m-%dT%H:%M'),'location':'Library','spots':'2','item':other.pk}),'errorlist')
        self.assertEqual(self.cb.get(f'/buddies/{self.post_buddy().pk}/edit/').status_code,404)
        c=Client();c.force_login(make_user('pending',False));self.assertEqual(c.get('/buddies/new/').status_code,403)
    def test_friends_only_after_meeting(self):
        self.social(self.ca,self.b,'friend');self.assertFalse(Connection.objects.exists())
        self.assertContains(self.ca.get(f'/people/{self.b.pk}/'),'你們還沒有在這裡見過面')
        o=apply(make_item(self.a).pk,self.b,self.when,self.when+timedelta(days=1))
        with self.assertRaises(ValidationError): connect(self.a,self.b,'friend')
        act(o.pk,self.a,'accept');self.assertEqual(met_ids(self.a),{self.b.pk})
        Profile.objects.filter(user=self.b).update(social=False)
        with self.assertRaises(ValidationError): connect(self.a,self.b,'friend')
        Profile.objects.filter(user=self.b).update(social=True)
        self.social(self.ca,self.b,'friend');self.assertContains(self.cb.get('/friends/'),'好友請求')
        self.assertTrue(Notification.objects.filter(user=self.b,url='/friends/').exists())
        self.social(self.cb,self.a,'friend');self.assertTrue(mutual(self.a,self.b,'friend'))
        self.assertEqual(Notification.objects.filter(url__startswith='/people/').count(),2)
        r=self.social(self.cb,self.a,'chat');thread=Thread.objects.get(item=None,order=None,buddy=None)
        self.assertRedirects(r,f'/messages/{thread.pk}/');self.cb.post(f'/messages/{thread.pk}/',{'text':'Hi friend'})
        self.assertEqual(thread.messages.count(),1);self.assertEqual(self.social(self.ca,self.b,'chat').url,f'/messages/{thread.pk}/')
        self.assertEqual(self.social(self.cc,self.a,'chat').status_code,403);self.assertEqual(self.cc.get(f'/messages/{thread.pk}/').status_code,403)
        self.social(self.ca,self.b,'unfriend');self.assertFalse(Connection.objects.exists())
        self.cb.post(f'/messages/{thread.pk}/',{'text':'Still there?'});self.assertEqual(thread.messages.count(),1)
        self.assertContains(self.cb.get(f'/messages/{thread.pk}/'),'此對話已關閉')
    def test_crush_secret_until_mutual(self):
        b=self.post_buddy();BuddyJoin.objects.create(buddy=b,user=self.b,status='accepted')
        self.social(self.ca,self.b,'crush');self.assertFalse(Connection.objects.exists())
        self.assertContains(self.ca.post('/profile/',{'nickname':'amy','dating':'on','social':'on'}),'Confirm you are 18 or older')
        self.ca.post('/profile/',{'nickname':'amy','dating':'on','adult':'on','social':'on','bio':'Hiker','interests':'hiking, 攝影'})
        self.assertTrue(Profile.objects.get(user=self.a).dating)
        notes=Notification.objects.count();self.social(self.ca,self.b,'crush')
        self.assertTrue(Connection.objects.filter(sender=self.a,kind='crush').exists());self.assertEqual(Notification.objects.count(),notes)
        # The recipient sees nothing of a one-sided crush.
        page=self.cb.get(f'/people/{self.a.pk}/');self.assertContains(page,'#攝影');self.assertNotContains(page,'互相心動');self.assertNotContains(page,'你已悄悄心動')
        self.assertNotContains(self.cb.get('/friends/'),'互相心動')
        Profile.objects.filter(user=self.b).update(dating=True);self.social(self.cb,self.a,'crush')
        self.assertTrue(mutual(self.a,self.b,'crush'));self.assertEqual(Notification.objects.filter(text__contains='互相心動').count(),2)
        self.assertContains(self.ca.get(f'/people/{self.b.pk}/'),'你們互相心動');self.assertContains(self.ca.get('/friends/'),'>ben ↗<')
        self.ca.post('/profile/',{'nickname':'amy','social':'on'})
        self.assertFalse(Connection.objects.filter(sender=self.a).exists());self.assertFalse(mutual(self.a,self.b,'crush'))
    def test_block(self):
        b=self.post_buddy(client=self.cb,spots='3');BuddyJoin.objects.create(buddy=b,user=self.a,status='accepted')
        o=apply(make_item(self.a).pk,self.b,self.when,self.when+timedelta(days=1));act(o.pk,self.a,'accept')
        connect(self.a,self.b,'friend');connect(self.b,self.a,'friend')
        item_thread=Thread.objects.create(item=o.item,first=self.b,second=self.a)
        notes=Notification.objects.filter(user=self.b).count();self.social(self.ca,self.b,'block')
        self.assertFalse(Connection.objects.exists());self.assertEqual(BuddyJoin.objects.get().status,'declined')
        self.assertEqual(Notification.objects.filter(user=self.b).count(),notes)
        with self.assertRaises(ValidationError): connect(self.b,self.a,'friend')
        self.assertNotContains(self.ca.get('/buddies/'),'Weekend hike');self.assertContains(self.cc.get('/buddies/'),'Weekend hike')
        self.assertContains(self.cb.get(f'/people/{self.a.pk}/'),'暫時無法與此用戶建立連結')
        self.cb.post(f'/messages/{item_thread.pk}/',{'text':'hey'});self.assertFalse(item_thread.messages.exists())
        self.assertEqual(self.cb.post(f'/items/{o.item.pk}/contact/').status_code,403)
        # The order chat stays open so the item can still be handed back.
        self.cb.post(f'/messages/{o.thread.pk}/',{'text':'Returning tomorrow'});self.assertEqual(o.thread.messages.count(),1)
        self.assertContains(self.ca.get('/friends/'),'解除封鎖')
        self.social(self.ca,self.b,'unblock');self.assertFalse(Block.objects.exists())
    def test_pages_render_both_languages_and_report(self):
        b=self.post_buddy();BuddyJoin.objects.create(buddy=b,user=self.b,status='accepted')
        for language in ('en','zh'):
            for client in (self.ca,self.cb):
                client.post('/language/',{'lang':language})
                for url in ('/buddies/','/buddies/?kind=outdoor&q=hike','/buddies/new/',f'/buddies/{b.pk}/','/friends/',f'/people/{self.a.pk}/',f'/people/{self.b.pk}/','/profile/','/messages/','/rules/'):
                    self.assertEqual(client.get(url).status_code,200,(url,language))
            self.assertEqual(self.ca.get(f'/buddies/{b.pk}/edit/').status_code,200)
        self.assertEqual(Client().get(f'/buddies/{b.pk}/').status_code,200);self.assertEqual(Client().get('/friends/').status_code,302)
        self.assertEqual(self.cc.post(f'/report/buddy/{b.pk}/',{'reason':'Spam activity'}).status_code,302)
        self.assertEqual(Report.objects.get().kind,'buddy')

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
        self.assertContains(r,'Check your inbox')
        req=urlopen.call_args.args[0];body=json.loads(req.data)
        self.assertEqual((req.full_url,req.get_header('Authorization')),('https://api.resend.com/emails','Bearer re_test'))
        self.assertEqual((body['to'],body['from']),(['amy@my.cityu.edu.hk'],'Box Box Share <onboarding@resend.dev>'))
        self.assertRegex(body['text'],r'http://testserver/verify/\S+/')
    def test_api_failure_reported_and_token_discarded(self):
        with mock.patch('market.mail.urlopen',side_effect=OSError('403')):
            r=Client().post('/login/',{'email':'amy@my.cityu.edu.hk'})
        self.assertContains(r,'Email service unavailable')
        self.assertFalse(LoginToken.objects.exists())

class SecurityHeaders(TestCase):
    def test_csp_and_permissions_policy(self):
        r=Client().get('/rules/')
        self.assertIn("script-src 'self'",r['Content-Security-Policy']);self.assertIn('camera=()',r['Permissions-Policy'])
