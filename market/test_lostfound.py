"""Lost-and-found and harassment controls tested through real server requests."""
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from . import social
from .models import (
    BuddyPost, LostFoundPost, LOSTFOUND_CATEGORIES, Message, Notification,
    Report, Thread, UserBlock,
)
from .services import apply
from .tests import make_item, make_user


class LostFoundFlow(TestCase):
    def setUp(self):
        self.owner = make_user('lf-owner')
        self.finder = make_user('lf-finder')
        self.other = make_user('lf-outsider')
        self.a, self.b, self.c = Client(), Client(), Client()
        for client, user in ((self.a, self.owner), (self.b, self.finder), (self.c, self.other)):
            client.force_login(user)
        self.category = LOSTFOUND_CATEGORIES[0][0]
        self.other_category = LOSTFOUND_CATEGORIES[-1][0]
        self.when = timezone.now() - timedelta(hours=2)
        self.post = self.new_post()

    def new_post(self, **changes):
        data = dict(owner=self.owner, kind='lost', category=self.category,
                    title='Black notebook', description='A notebook with a plain cover.',
                    occurred_at=self.when, location='AC1', color='Black', status='open')
        data.update(changes)
        return LostFoundPost.objects.create(**data)

    def form_data(self, **changes):
        data = dict(kind='found', category=self.category, title='Found headphones',
                    description='Found near the library entrance.',
                    occurred_at=self.when.strftime('%Y-%m-%dT%H:%M'),
                    location='Library', color='White', status='open')
        data.update(changes)
        return data

    def test_found_and_lost_publishing_validate_dates_and_owner_permissions(self):
        response = self.b.post('/lost-found/new/', self.form_data())
        self.assertEqual(response.status_code, 302)
        created = LostFoundPost.objects.get(title='Found headphones')
        self.assertEqual((created.owner_id, created.kind), (self.finder.pk, 'found'))
        self.assertEqual(self.a.get(f'/lost-found/{created.pk}/edit/').status_code, 404)
        changed = self.b.post(f'/lost-found/{created.pk}/edit/', self.form_data(title='Found white headphones'))
        self.assertEqual(changed.status_code, 302)
        created.refresh_from_db()
        self.assertEqual(created.title, 'Found white headphones')
        before = LostFoundPost.objects.count()
        invalid = self.b.post('/lost-found/new/', self.form_data(category='not-a-category'))
        self.assertEqual(invalid.status_code, 200)
        self.assertTrue(invalid.context['form'].errors)
        future = self.b.post('/lost-found/new/', self.form_data(
            occurred_at=(timezone.now()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')))
        self.assertEqual(future.status_code, 200)
        self.assertIn('occurred_at', future.context['form'].errors)
        self.assertEqual(LostFoundPost.objects.count(), before)
        anonymous = Client().post('/lost-found/new/', self.form_data(title='Anonymous'))
        self.assertEqual(anonymous.status_code, 302)
        self.assertFalse(LostFoundPost.objects.filter(title='Anonymous').exists())

    def test_combined_search_facets_do_not_mix_boards_or_resolved_items(self):
        found = self.new_post(kind='found', title='Black notebook at AC1')
        self.new_post(kind='found', title='Black notebook at library', location='Library')
        self.new_post(kind='found', title='Black notebook, other category', category=self.other_category)
        resolved = self.new_post(kind='found', title='Black notebook returned', status='resolved')
        result = self.b.get('/lost-found/', {'kind':'found', 'q':'notebook',
                                           'category':self.category, 'location':'AC1', 'status':'open'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual([p.pk for p in result.context['rows']], [found.pk])
        resolved_page = self.b.get('/lost-found/', {'kind':'found', 'status':'resolved'})
        self.assertIn(resolved.pk, [p.pk for p in resolved_page.context['rows']])
        old = self.new_post(kind='found', title='Old found notice', occurred_at=timezone.now()-timedelta(days=40))
        recent_page = self.b.get('/lost-found/', {'kind':'found', 'since':'week'})
        self.assertNotIn(old.pk, [p.pk for p in recent_page.context['rows']])

    def test_contact_opens_one_contextual_private_conversation_without_friendship(self):
        path = f'/lost-found/{self.post.pk}/contact/'
        first = self.b.post(path)
        self.assertEqual(first.status_code, 302)
        thread = Thread.objects.get(lostfound=self.post)
        self.assertEqual({thread.first_id,thread.second_id}, {self.owner.pk,self.finder.pk})
        self.assertEqual(self.b.post(path).url, first.url)
        self.assertEqual(Thread.objects.filter(lostfound=self.post).count(), 1)
        before = Notification.objects.filter(user=self.owner).count()
        self.assertEqual(self.b.post(first.url, {'text':'I found something like this.'}).status_code, 302)
        self.assertTrue(Message.objects.filter(thread=thread,text='I found something like this.').exists())
        self.assertGreater(Notification.objects.filter(user=self.owner).count(), before)
        self.assertEqual(self.c.get(first.url).status_code, 403)
        self.assertEqual(self.c.post(first.url, {'text':'Unauthorized'}).status_code, 403)
        self.assertFalse(Message.objects.filter(text='Unauthorized').exists())
        self.assertEqual(self.a.post(path).status_code, 403)

    def test_only_owner_can_resolve_and_resolved_posts_do_not_accept_new_contacts(self):
        path=f'/lost-found/{self.post.pk}/'
        self.assertIn(self.b.post(path, {'action':'resolve'}).status_code, (403,404))
        self.post.refresh_from_db()
        self.assertEqual(self.post.status,'open')
        self.assertEqual(self.a.post(path, {'action':'resolve'}).status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status,'resolved')
        self.assertEqual(self.b.post(path+'contact/').status_code,403)

    def test_reports_allow_post_or_participant_conversation_but_reject_outsiders(self):
        thread=Thread.objects.create(lostfound=self.post,first=self.finder,second=self.owner)
        report_url=f'/report/thread/{thread.pk}/'
        self.assertEqual(self.c.post(report_url, {'reason':'Unrelated report attempt'}).status_code,403)
        self.assertEqual(self.b.post(report_url, {'reason':'Repeated unwanted messages'}).status_code,302)
        self.assertTrue(Report.objects.filter(reporter=self.finder,kind='thread',target=thread.pk).exists())
        self.assertEqual(self.b.post(f'/report/lostfound/{self.post.pk}/', {'reason':'The description appears misleading'}).status_code,302)
        self.assertTrue(Report.objects.filter(reporter=self.finder,kind='lostfound',target=self.post.pk).exists())
        before=Report.objects.count()
        self.b.post(report_url, {'reason':'x'})
        self.assertEqual(Report.objects.count(),before)

    def test_block_closes_both_directions_of_every_existing_chat_and_keeps_history(self):
        item=make_item(self.owner)
        order=apply(item.pk,self.finder,timezone.now()+timedelta(days=2),timezone.now()+timedelta(days=3))
        buddy=BuddyPost.objects.create(owner=self.owner,category='buddy',kind='sports',title='Tennis',
            description='Join a game.',starts=timezone.now()+timedelta(days=2),location='Court',capacity=2)
        application=social.apply(buddy.pk,self.finder,'Joining')
        social.decide(buddy.pk,self.owner,application.pk,True)
        friendship=social.request_friend(self.owner,self.finder)
        social.respond(self.finder,friendship.pk,True)
        threads=[
            order.thread,
            Thread.objects.get(buddy=buddy),
            social.direct_thread(self.owner,self.finder),
            Thread.objects.create(item=item,first=self.finder,second=self.owner),
            Thread.objects.create(lostfound=self.post,first=self.finder,second=self.owner),
        ]
        for thread in threads:
            Message.objects.create(thread=thread,sender=self.finder,text='Historical message')
        blocked=self.a.post(f'/people/{self.finder.pk}/block/', {'action':'block'})
        self.assertEqual(blocked.status_code,302)
        self.assertTrue(social.is_blocked(self.owner,self.finder))
        self.assertTrue(social.is_blocked(self.finder,self.owner))
        self.assertEqual(UserBlock.objects.filter(blocker=self.owner,blocked=self.finder).count(),1)
        before_messages=Message.objects.count();before_notifications=Notification.objects.count()
        for client in (self.a,self.b):
            for thread in threads:
                self.assertEqual(client.get(f'/messages/{thread.pk}/').status_code,200)
                self.assertEqual(client.post(f'/messages/{thread.pk}/', {'text':'Must not arrive'}).status_code,302)
        self.assertEqual(Message.objects.count(),before_messages)
        self.assertEqual(Notification.objects.count(),before_notifications)
        self.assertEqual(self.a.get(f'/orders/{order.pk}/').status_code,200)
        self.assertEqual(self.b.get(f'/orders/{order.pk}/').status_code,200)
        self.assertEqual(self.b.post(f'/items/{item.pk}/contact/').status_code,403)
        self.assertEqual(self.b.post(f'/lost-found/{self.post.pk}/contact/').status_code,403)
        self.assertEqual(self.a.post(f'/people/{self.finder.pk}/block/', {'action':'block'}).status_code,302)
        self.assertEqual(UserBlock.objects.filter(blocker=self.owner,blocked=self.finder).count(),1)
        self.assertEqual(self.a.post(f'/people/{self.finder.pk}/block/', {'action':'unblock'}).status_code,302)
        self.assertFalse(social.is_blocked(self.owner,self.finder))
        self.assertEqual(self.b.post(f'/messages/{threads[-1].pk}/', {'text':'Contact restored'}).status_code,302)
        self.assertTrue(Message.objects.filter(text='Contact restored').exists())

    def test_block_prevents_new_friend_or_buddy_requests_without_notification(self):
        social.block_user(self.owner,self.finder)
        buddy=BuddyPost.objects.create(owner=self.owner,category='buddy',kind='study',title='Revision',
            description='Study together.',starts=timezone.now()+timedelta(days=2),location='Library',capacity=2)
        before=Notification.objects.count()
        with self.assertRaises((ValidationError,PermissionDenied)):
            social.request_friend(self.finder,self.owner)
        with self.assertRaises((ValidationError,PermissionDenied)):
            social.apply(buddy.pk,self.finder,'Please add me')
        self.assertEqual(Notification.objects.count(),before)
        self.assertEqual(self.a.post(f'/people/{self.owner.pk}/block/', {'action':'block'}).status_code,403)

    def test_three_language_navigation_and_contact_safety_pages(self):
        response = self.b.post(f'/lost-found/{self.post.pk}/contact/')
        thread = Thread.objects.get(lostfound=self.post)
        for lang, label in (('en','Lost & Found'),('zh','失物招領'),('hans','失物招领')):
            self.b.post('/language/', {'lang':lang})
            listing = self.b.get('/lost-found/', {'kind':'lost'})
            self.assertEqual(listing.status_code,200)
            nav = listing.content.decode().split('<nav')[1].split('</nav>')[0]
            positions = [nav.index(f'href="{path}"') for path in ('/lost-found/','/buddy/','/my/','/messages/','/impact/')]
            self.assertEqual(positions,sorted(positions))
            self.assertIn(label, nav)
            for code, _ in LOSTFOUND_CATEGORIES:
                self.assertContains(listing, f'value="{code}"')
            for path in ('/lost-found/new/?kind=found','/lost-found/new/?kind=lost',
                         f'/lost-found/{self.post.pk}/',f'/messages/{thread.pk}/',
                         f'/report/thread/{thread.pk}/','/messages/'):
                self.assertEqual(self.b.get(path).status_code,200,(path,lang))
            chat = self.b.get(f'/messages/{thread.pk}/')
            self.assertContains(chat, f'href="/lost-found/{self.post.pk}/"')
            self.assertContains(chat, f'href="/report/thread/{thread.pk}/"')
            self.assertContains(chat, f'action="/people/{self.owner.pk}/block/"')
