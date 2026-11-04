"""Keep pre-Buddy member pages accessible alongside the social additions."""
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from .models import Message, Notification, Offer, Review, Thread, Wanted
from .impact import FACTORS, METHOD_URL
from .services import apply
from .tests import make_item, make_user


class LegacyMemberPages(TestCase):
    def setUp(self):
        self.owner = make_user('legacy-owner')
        self.borrower = make_user('legacy-borrower')
        self.item = make_item(self.owner)
        self.own_item = make_item(self.borrower)
        self.own_item.title = 'Borrower original listing'
        self.own_item.save()
        start = timezone.now() + timedelta(days=2)
        self.order = apply(self.item.pk, self.borrower, start, start + timedelta(days=1))
        self.wanted = Wanted.objects.create(
            owner=self.borrower, title='Original request', category='tech',
            description='User content stays unchanged', start=start,
            end=start + timedelta(days=1), budget=100, location='AC1')
        Offer.objects.create(wanted=self.wanted, item=self.item, text='Original offer')
        self.thread = Thread.objects.get(order=self.order)
        Message.objects.create(thread=self.thread, sender=self.owner, text='Original private message')
        Notification.objects.create(user=self.borrower, text='Original notification', url=f'/orders/{self.order.pk}/', kind='request')
        self.client.force_login(self.borrower)

    def test_existing_dashboard_records_and_edit_links_survive(self):
        for lang in ('en', 'zh', 'hans'):
            self.client.post('/language/', {'lang': lang})
            page = self.client.get('/my/')
            for text in ('Campus camera', 'Borrower original listing', 'Original request'):
                self.assertContains(page, text)
            for url in (f'/orders/{self.order.pk}/', f'/items/{self.own_item.pk}/edit/',
                        f'/wanted/{self.wanted.pk}/edit/', '/wanted/new/', '/items/new/'):
                self.assertContains(page, f'href="{url}"')
            # These remain member pages even when Buddy has no records.
            for url in ('/profile/', '/items/new/', '/wanted/new/',
                        f'/items/{self.own_item.pk}/edit/', f'/wanted/{self.wanted.pk}/edit/'):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_original_conversations_notifications_and_order_links_survive(self):
        self.client.post('/language/', {'lang': 'en'})
        inbox = self.client.get('/messages/')
        for text in ('Conversations', 'Borrow', 'Notifications', 'Original notification'):
            self.assertContains(inbox, text)
        notes = self.client.get('/notifications/')
        for text in ('Mark all read', 'Original notification'):
            self.assertContains(notes, text)
        self.assertContains(inbox, f'href="/messages/{self.thread.pk}/"')
        chat = self.client.get(f'/messages/{self.thread.pk}/')
        self.assertContains(chat, 'Original private message')
        self.assertContains(chat, f'href="/orders/{self.order.pk}/"')
        self.assertContains(chat, 'name="text"')

    def test_borrowing_offers_and_reviews_remain_separate_from_buddy(self):
        self.client.post('/language/', {'lang': 'en'})
        item = self.client.get(f'/items/{self.item.pk}/')
        for text in ('Check price & availability', 'Message owner', 'id_start', 'id_end', 'Deposit'):
            self.assertContains(item, text)
        self.assertContains(self.client.get(f'/wanted/{self.wanted.pk}/'), 'Original offer')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(f'/wanted/{self.wanted.pk}/'), 'name="item"')
        self.order.status = 'completed'
        self.order.save(update_fields=['status'])
        Review.objects.create(order=self.order, author=self.borrower, recipient=self.owner,
                              rating=5, text='Original community review')
        self.assertContains(self.client.get(f'/people/{self.owner.pk}/'), 'Original community review')

    def test_user_report_link_does_not_depend_on_friend_eligibility(self):
        url = f'/people/{self.owner.pk}/'
        report = f'href="/report/user/{self.owner.pk}/"'
        self.assertContains(Client().get(url), report)
        unverified = make_user('legacy-unverified', verified=False)
        self.client.force_login(unverified)
        self.assertContains(self.client.get(url), report)
        # Keeping the entry does not bypass the existing verification requirement.
        self.assertEqual(self.client.get(f'/report/user/{self.owner.pk}/').status_code, 403)
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(url), report)

    def test_impact_keeps_statistics_all_categories_and_method_in_every_language(self):
        headings = {
            'en': ('Estimated emissions avoided', 'Completed borrows', 'Items listed',
                   'Purchase-avoidance rate', 'By category', 'Method', 'Other'),
            'zh': ('估算減少碳排放', '已完成借用', '上架中物品', '代替購買比例', '按分類', '計算方法', '其他'),
            'hans': ('估算减少碳排放', '已完成借用', '上架中物品', '代替购买比例', '按分类', '计算方法', '其他'),
        }
        for completed in (False, True):
            if completed:
                self.order.status = 'completed'
                self.order.save(update_fields=['status'])
            for client in (Client(), self.client):
                for lang, labels in headings.items():
                    with self.subTest(completed=completed, lang=lang, member=client is self.client):
                        client.post('/language/', {'lang': lang})
                        response = client.get('/impact/')
                        for label in labels:
                            self.assertContains(response, label)
                        # Zero completed orders must not hide the original explanation or sources.
                        for factor in FACTORS.values():
                            if factor:
                                self.assertContains(response, f'href="{factor[4]}"')
                        self.assertContains(response, f'href="{METHOD_URL}"')
                        self.assertEqual(len(response.context['impact']['rows']), 6)
                        self.assertEqual(response.context['impact']['borrows'], int(completed))
                        self.assertContains(response, '24.5' if completed else '0.0')
                        self.assertContains(response, 'kg CO₂e')
