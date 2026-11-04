from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, Client
from django.utils import timezone
from .models import *
from .tests import make_user
from . import groups, social


class GroupChat(TestCase):
    def setUp(self):
        self.host=make_user('host');self.ann=make_user('ann');self.bob=make_user('bob');self.out=make_user('outsider')
        self.post=BuddyPost.objects.create(owner=self.host,category='team',kind='course',title='EE1001 team',description='Test',starts=timezone.now()+timedelta(days=2),ends=timezone.now()+timedelta(days=2,hours=2),location='Library',capacity=4)
        self.aa=BuddyApplication.objects.create(post=self.post,user=self.ann,status='accepted')
        self.bb=BuddyApplication.objects.create(post=self.post,user=self.bob,status='pending')
        self.ch=Client();self.ch.force_login(self.host)
        self.ca=Client();self.ca.force_login(self.ann)
        self.cb=Client();self.cb.force_login(self.bob)
        self.co=Client();self.co.force_login(self.out)

    def create(self):return groups.create(self.post.pk,self.host)
    def url(self,g):return f'/messages/groups/{g.pk}/'

    def test_host_only_after_acceptance_and_idempotency(self):
        with self.assertRaises(PermissionDenied):groups.create(self.post.pk,self.ann)
        self.aa.status='pending';self.aa.save()
        with self.assertRaises(ValidationError):self.create()
        self.assertEqual(BuddyGroup.objects.count(),0)
        self.aa.status='accepted';self.aa.save();g=self.create()
        self.assertEqual(self.create().pk,g.pk)
        self.assertEqual(g.memberships.count(),1)
        self.assertEqual(g.memberships.get().user,self.host)
        self.assertEqual(Notification.objects.filter(user=self.ann).count(),1)

    def test_opt_in_and_approval_required(self):
        g=self.create()
        for c in (self.ca,self.cb,self.co):self.assertEqual(c.get(self.url(g)).status_code,403)
        for u in (self.bob,self.out):
            with self.assertRaises(PermissionDenied):groups.join(g.pk,u)
        groups.join(g.pk,self.ann);self.assertEqual(self.ca.get(self.url(g)).status_code,200)
        self.assertEqual(g.memberships.count(),2)

    def test_late_join_and_rejoin_boundary_cannot_reset_backwards(self):
        g=self.create();old=groups.send(g.pk,self.host,'Before join secret')
        first=groups.join(g.pk,self.ann);after=groups.send(g.pk,self.host,'After join hello')
        self.assertEqual(groups.join(g.pk,self.ann).history_after,first.history_after)
        self.assertEqual(list(groups.visible_messages(g,self.ann).values_list('pk',flat=True)),[after.pk])
        groups.leave(g.pk,self.ann)
        self.assertEqual(self.ca.get(self.url(g)).status_code,403)
        groups.send(g.pk,self.host,'While outside')
        row=groups.join(g.pk,self.ann);self.assertGreater(row.history_after,first.history_after)
        self.assertEqual(groups.visible_messages(g,self.ann).count(),0)
        last=groups.send(g.pk,self.host,'After rejoin')
        self.assertEqual(list(groups.visible_messages(g,self.ann).values_list('pk',flat=True)),[last.pk])
        self.assertEqual(self.post.applications.get(user=self.ann).status,'accepted')

    def test_join_after_further_approval(self):
        g=self.create();social.decide(self.post.pk,self.host,self.bb.pk,True)
        self.assertFalse(g.memberships.filter(user=self.bob).exists())
        groups.join(g.pk,self.bob);self.assertEqual(self.cb.get(self.url(g)).status_code,200)

    def test_withdrawal_revokes_access_and_sending(self):
        g=self.create();groups.join(g.pk,self.ann);social.withdraw(self.post.pk,self.ann)
        self.assertIsNotNone(g.memberships.get(user=self.ann).left_at)
        self.assertEqual(self.ca.get(self.url(g)).status_code,403)
        with self.assertRaises(PermissionDenied):groups.send(g.pk,self.ann,'No access')
        with self.assertRaises(PermissionDenied):groups.join(g.pk,self.ann)

    def test_host_removal_revokes_access(self):
        g=self.create();groups.join(g.pk,self.ann);social.remove_member(self.post.pk,self.host,self.aa.pk)
        self.assertEqual(self.ca.get(self.url(g)).status_code,403)
        self.assertNotIn(g.pk,[r.group_id for r in groups.active_memberships(self.ann)])

    def test_closed_or_ended_recruitment_keeps_chat(self):
        g=self.create();groups.join(g.pk,self.ann);social.set_open(self.post.pk,self.host,False)
        BuddyPost.objects.filter(pk=self.post.pk).update(starts=timezone.now()-timedelta(days=2),ends=timezone.now()-timedelta(days=1))
        groups.send(g.pk,self.ann,'Still here')
        self.assertContains(self.ca.get(self.url(g)),'Still here')

    def test_message_privacy_blocking_and_contacts(self):
        g=self.create();groups.join(g.pk,self.ann);social.decide(self.post.pk,self.host,self.bb.pk,True);groups.join(g.pk,self.bob)
        social.block_user(self.ann,self.bob)
        groups.send(g.pk,self.bob,'Hidden from Ann');groups.send(g.pk,self.host,'Visible to Ann')
        page=self.ca.get(self.url(g));self.assertNotContains(page,'Hidden from Ann');self.assertContains(page,'Visible to Ann')
        self.assertNotContains(page,'contact_whatsapp')
        self.assertFalse(Notification.objects.filter(user=self.ann,text__contains='New Buddy group message').count()>1)
        social.block_user(self.ann,self.host)
        self.assertEqual(self.ca.get(self.url(g)).status_code,403)

    def test_group_reporting_requires_current_visibility(self):
        g=self.create();old=groups.send(g.pk,self.host,'Before join');groups.join(g.pk,self.ann)
        new=groups.send(g.pk,self.host,'Report this')
        self.assertEqual(self.ca.get(f'/report/group_message/{old.pk}/').status_code,403)
        self.assertEqual(self.co.get(f'/report/group_message/{new.pk}/').status_code,403)
        self.assertEqual(self.ca.post(f'/report/group_message/{new.pk}/',{'reason':'Harassment test report'}).status_code,302)
        self.assertTrue(Report.objects.filter(kind='group_message',target=new.pk,reporter=self.ann).exists())

    def test_http_actions_csrf_and_validation(self):
        g=self.create();endpoint=f'/buddy/{self.post.pk}/group/'
        self.assertEqual(self.ca.get(endpoint).status_code,405)
        self.assertEqual(self.ca.post(endpoint,{'action':'join'}).status_code,302)
        self.assertEqual(Client(enforce_csrf_checks=True).post(endpoint,{'action':'join'}).status_code,403)
        for text in ('','x'*2001):
            with self.assertRaises(ValidationError):groups.send(g.pk,self.ann,text)
        self.ca.post(self.url(g),{'action':'send','text':'<script>bad()</script>'})
        self.assertContains(self.ca.get(self.url(g)),'&lt;script&gt;bad()&lt;/script&gt;')
        with self.assertRaises(ValidationError):groups.leave(g.pk,self.host)

    def test_inbox_and_buddy_links_and_three_languages(self):
        g=self.create();self.assertNotContains(self.ca.get('/messages/'),self.url(g))
        groups.join(g.pk,self.ann)
        for lang in ('en','zh','hans'):
            self.ca.post('/language/',{'lang':lang})
            self.assertContains(self.ca.get('/messages/'),self.url(g))
            self.assertContains(self.ca.get(f'/buddy/{self.post.pk}/'),self.url(g))
            self.assertEqual(self.ca.get(self.url(g)).status_code,200)


class GroupRace(TransactionTestCase):
    def setUp(self):
        self.host=make_user('racehost');self.ann=make_user('raceann')
        self.post=BuddyPost.objects.create(owner=self.host,category='buddy',kind='study',title='Study',description='x',starts=timezone.now()+timedelta(days=1),location='Library',capacity=2)
        BuddyApplication.objects.create(post=self.post,user=self.ann,status='accepted')

    def test_concurrent_creation_and_join_remain_unique(self):
        barrier=Barrier(2)
        def create():
            close_old_connections()
            try:
                host=User.objects.get(pk=self.host.pk);barrier.wait();return groups.create(self.post.pk,host).pk
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(lambda _:create(),range(2)))
        self.assertEqual(ids[0],ids[1]);g=BuddyGroup.objects.get(pk=ids[0])
        barrier=Barrier(2)
        def join():
            close_old_connections()
            try:
                user=User.objects.get(pk=self.ann.pk);barrier.wait();return groups.join(g.pk,user).pk
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(lambda _:join(),range(2)))
        self.assertEqual(ids[0],ids[1]);self.assertEqual(g.memberships.count(),2)

    def test_sending_and_removal_serialize_on_post(self):
        g=groups.create(self.post.pk,self.host);groups.join(g.pk,self.ann);barrier=Barrier(2)
        def act(which):
            close_old_connections()
            try:
                u=User.objects.get(pk=self.ann.pk);barrier.wait()
                try:
                    if which=='send':groups.send(g.pk,u,'Concurrent message')
                    else:social.withdraw(self.post.pk,u)
                except PermissionDenied:pass
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(act,['send','remove']))
        with self.assertRaises(PermissionDenied):groups.send(g.pk,self.ann,'After removal')


class GroupMigration(TransactionTestCase):
    def test_additive_migration_keeps_private_messages(self):
        executor=MigrationExecutor(connection);old=[('market','0007_student_profile_recommendations')];latest=executor.loader.graph.leaf_nodes()
        executor.migrate(old)
        try:
            apps=executor.loader.project_state(old).apps;U=apps.get_model('auth','User');P=apps.get_model('market','Profile')
            a=U.objects.create(username='old-a');b=U.objects.create(username='old-b')
            P.objects.create(user_id=a.pk,nickname='Old name',major='EE');P.objects.create(user_id=b.pk)
            t=apps.get_model('market','Thread').objects.create(first_id=a.pk,second_id=b.pk)
            message=apps.get_model('market','Message').objects.create(thread_id=t.pk,sender_id=a.pk,text='Existing private history')
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(Message.objects.get(pk=message.pk).text,'Existing private history')
            self.assertEqual(Profile.objects.get(user_id=a.pk).major,'EE');self.assertEqual(BuddyGroup.objects.count(),0)
        finally:MigrationExecutor(connection).migrate(latest)
