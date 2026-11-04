"""Sale listings, want-to-buy requests, direct purchase, contact unlocking and the simplified publisher."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
import re

from . import social
from .forms import ItemForm, WantedForm
from .impact import impact_summary
from .models import *
from .services import act, apply, buy, derive_title, resolve_dispute
from .tests import make_item, make_user


def sale_item(owner, price='80.00', **changes):
    now = timezone.now()
    data = dict(owner=owner, intent='sale', title='Spare calculator', category='study', description='Working calculator.', condition='', daily=Decimal(price), deposit=0, available_start=now, available_end=now + timedelta(days=365), max_days=365, location='CityUHK campus')
    data.update(changes)
    return Item.objects.create(**data)


class Base(TestCase):
    def setUp(self):
        self.seller = make_user('seller'); self.buyer = make_user('buyer'); self.other = make_user('other')
        self.s, self.b, self.o = Client(), Client(), Client()
        self.s.force_login(self.seller); self.b.force_login(self.buyer); self.o.force_login(self.other)


class Publishing(Base):
    def test_title_comes_from_first_sentence(self):
        self.assertEqual(derive_title('  二手課本。保存完好  '), '二手課本')
        self.assertEqual(derive_title('Calculator in good condition. Includes cover'), 'Calculator in good condition')
        self.assertEqual(len(derive_title('x' * 200)), 100)

    def test_sale_needs_only_price_and_description(self):
        response = self.s.post('/items/new/', {'intent': 'sale', 'daily': '80', 'description': 'Spare calculator. With cover.'})
        self.assertEqual(response.status_code, 302)
        item = Item.objects.get()
        self.assertEqual((item.intent, item.title, item.deposit, item.status, item.category, item.location), ('sale', 'Spare calculator', 0, 'listed', 'other', 'CityUHK campus'))

    def test_rental_defaults_to_seven_days(self):
        self.assertEqual(self.s.post('/items/new/', {'intent': 'rent', 'daily': '12', 'description': 'Tripod.'}).status_code, 302)
        item = Item.objects.get()
        self.assertEqual((item.intent, item.title, item.deposit, item.max_days), ('rent', 'Tripod', 0, 7))
        self.assertEqual((item.available_end - item.available_start).days, 7)

    def test_missing_amount_or_description_rejected(self):
        for data in ({'intent': 'sale', 'description': 'No price'}, {'intent': 'sale', 'daily': '5'}, {'intent': 'sale', 'daily': '-1', 'description': 'Negative'}):
            self.assertEqual(self.s.post('/items/new/', data).status_code, 200)
        self.assertFalse(Item.objects.exists())

    def test_rental_end_must_follow_start(self):
        now = timezone.localtime().strftime('%Y-%m-%dT%H:%M')
        response = self.s.post('/items/new/', {'intent': 'rent', 'daily': '5', 'description': 'Bad dates', 'available_start': now, 'available_end': now})
        self.assertEqual(response.status_code, 200); self.assertFalse(Item.objects.exists())

    def test_sale_cannot_carry_a_deposit(self):
        self.s.post('/items/new/', {'intent': 'sale', 'daily': '5', 'deposit': '100', 'description': 'No deposit please'})
        self.assertEqual(Item.objects.get().deposit, 0)

    def test_listing_type_is_fixed_after_publishing(self):
        item = make_item(self.seller)
        self.s.post(f'/items/{item.pk}/edit/', {'intent': 'sale', 'daily': '5', 'description': 'Changed', 'status': 'listed'})
        item.refresh_from_db(); self.assertEqual(item.intent, 'rent')

    def test_want_to_buy_needs_only_budget_and_description(self):
        self.assertEqual(self.b.post('/wanted/new/', {'intent': 'buy', 'budget': '100', 'description': 'Used textbook. Any edition.'}).status_code, 302)
        wanted = Wanted.objects.get()
        self.assertEqual((wanted.intent, wanted.title, wanted.active), ('buy', 'Used textbook', True))

    def test_publish_page_preselects_intent_from_link(self):
        self.assertContains(self.s.get('/items/new/'), 'value="rent" checked')


class Browsing(Base):
    def setUp(self):
        super().setUp()
        self.rental = make_item(self.seller); self.sale = sale_item(self.seller, title='Sale thing')

    def test_type_filter(self):
        self.assertContains(self.b.get('/?intent=sale'), 'Sale thing')
        self.assertNotContains(self.b.get('/?intent=sale'), 'Campus camera')
        self.assertContains(self.b.get('/?intent=rent'), 'Campus camera')
        self.assertNotContains(self.b.get('/?intent=rent'), 'Sale thing')
        page = self.b.get('/?intent=bogus')
        self.assertContains(page, 'Sale thing'); self.assertContains(page, 'Campus camera')

    def test_want_filter(self):
        now = timezone.now()
        Wanted.objects.create(owner=self.buyer, intent='buy', title='Buy me', category='study', description='x', start=now, end=now + timedelta(days=30), budget=5, location='AC1')
        Wanted.objects.create(owner=self.buyer, intent='borrow', title='Lend me', category='study', description='x', start=now, end=now + timedelta(days=3), budget=5, location='AC1')
        page = self.b.get('/?tab=wanted&intent=buy')
        self.assertContains(page, 'Buy me'); self.assertNotContains(page, 'Lend me')

    def test_items_have_share_control_and_requests_do_not(self):
        self.assertContains(self.b.get('/'), 'data-share-item="/items/')
        self.assertNotContains(self.b.get('/?tab=wanted'), 'data-share-item')

    def test_guest_can_view_a_listing_without_signing_in(self):
        self.assertEqual(Client().get(f'/items/{self.sale.pk}/').status_code, 200)

    def test_sale_page_offers_purchase_not_dates(self):
        page = self.b.get(f'/items/{self.sale.pk}/')
        self.assertContains(page, f'/items/{self.sale.pk}/buy/'); self.assertNotContains(page, 'name="start"')
        self.assertNotContains(self.b.get(f'/items/{self.rental.pk}/'), '/buy/')


class Purchase(Base):
    def setUp(self):
        super().setUp(); self.item = sale_item(self.seller)

    def test_full_flow(self):
        self.assertContains(self.b.get(f'/items/{self.item.pk}/buy/'), 'HK$ 80')
        self.assertFalse(Order.objects.exists())
        response = self.b.post(f'/items/{self.item.pk}/buy/')
        order = Order.objects.get()
        self.assertRedirects(response, f'/orders/{order.pk}/pay/')
        self.item.refresh_from_db()
        self.assertEqual((order.kind, order.status, order.rent, order.deposit, order.borrower), ('purchase', 'accepted', Decimal('80.00'), 0, self.buyer))
        self.assertEqual(self.item.status, 'sold')
        self.assertTrue(Thread.objects.filter(order=order, first=self.buyer, second=self.seller).exists())
        self.assertTrue(Notification.objects.filter(user=self.seller, url=f'/orders/{order.pk}/').exists())
        self.assertNotContains(self.b.get('/'), 'Spare calculator')
        act(order.pk, self.buyer, 'handover'); order.refresh_from_db(); self.assertEqual(order.status, 'accepted')
        act(order.pk, self.seller, 'handover'); order.refresh_from_db(); self.assertEqual(order.status, 'completed')

    def test_guest_is_sent_to_sign_in_and_back(self):
        response = Client().get(f'/items/{self.item.pk}/buy/')
        self.assertEqual(response.status_code, 302); self.assertIn(f'next=/items/{self.item.pk}/buy/', response['Location'])

    def test_sign_in_returns_to_the_item(self):
        guest = Client()
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            guest.post('/login/', {'email': 'newbuyer@my.cityu.edu.hk', 'next': f'/items/{self.item.pk}/buy/'})
        path = re.search(r'http://testserver(/verify/\S+)', mail.outbox[-1].body).group(1)
        self.assertRedirects(guest.post(path), f'/items/{self.item.pk}/buy/')

    def test_sign_in_ignores_outside_redirects(self):
        guest = Client()
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            guest.post('/login/', {'email': 'evil@my.cityu.edu.hk', 'next': 'https://evil.example/'})
        path = re.search(r'http://testserver(/verify/\S+)', mail.outbox[-1].body).group(1)
        self.assertRedirects(guest.post(path), '/')

    def test_only_one_buyer(self):
        buy(self.item.pk, self.buyer)
        with self.assertRaises(ValidationError): buy(self.item.pk, self.other)
        self.assertEqual(self.o.get(f'/items/{self.item.pk}/buy/').status_code, 404)

    def test_cannot_buy_own_rental_blocked_or_restricted(self):
        with self.assertRaises(ValidationError): buy(self.item.pk, self.seller)
        with self.assertRaises(ValidationError): buy(make_item(self.seller).pk, self.buyer)
        UserBlock.objects.create(blocker=self.seller, blocked=self.other)
        with self.assertRaises(PermissionDenied): buy(self.item.pk, self.other)
        self.seller.profile.restricted = True; self.seller.profile.save()
        with self.assertRaises(ValidationError): buy(self.item.pk, self.buyer)

    def test_sale_cannot_be_rented(self):
        start = timezone.now() + timedelta(days=1)
        with self.assertRaises(ValidationError): apply(self.item.pk, self.buyer, start, start + timedelta(days=1))

    def test_cancel_before_handover_relists_either_side(self):
        for canceller in (self.buyer, self.seller):
            order = buy(self.item.pk, self.buyer)
            act(order.pk, canceller, 'cancel')
            self.item.refresh_from_db(); order.refresh_from_db()
            self.assertEqual((order.status, self.item.status), ('cancelled', 'listed'))

    def test_no_cancel_after_handover_starts(self):
        order = buy(self.item.pk, self.buyer); act(order.pk, self.buyer, 'handover')
        with self.assertRaises(ValidationError): act(order.pk, self.seller, 'cancel')

    def test_rental_only_actions_are_refused(self):
        order = buy(self.item.pk, self.buyer)
        for action in ('deposit', 'refund', 'return'):
            with self.assertRaises(ValidationError): act(order.pk, self.buyer, action)
        with self.assertRaises(ValidationError): act(order.pk, self.buyer, 'extend', timezone.now() + timedelta(days=60))
        with self.assertRaises(ValidationError): act(order.pk, self.seller, 'accept')
        act(order.pk, self.buyer, 'rent'); order.refresh_from_db(); self.assertTrue(order.rent_borrower)

    def test_price_snapshot_survives_edit(self):
        order = buy(self.item.pk, self.buyer)
        Item.objects.filter(pk=self.item.pk).update(daily=999)
        order.refresh_from_db(); self.assertEqual(order.rent, Decimal('80.00'))

    def test_sold_item_cannot_be_edited(self):
        buy(self.item.pk, self.buyer)
        self.assertRedirects(self.s.get(f'/items/{self.item.pk}/edit/'), f'/items/{self.item.pk}/')
        self.s.post(f'/items/{self.item.pk}/edit/', {'daily': '1', 'description': 'relist', 'status': 'listed'})
        self.item.refresh_from_db(); self.assertEqual(self.item.status, 'sold')

    def test_free_sale_skips_payment(self):
        item = sale_item(self.seller, price='0', title='Free')
        response = self.b.post(f'/items/{item.pk}/buy/')
        self.assertRedirects(response, f'/orders/{Order.objects.get(item=item).pk}/')

    def test_order_and_payment_pages_read_as_a_purchase(self):
        self.b.post('/language/', {'lang': 'en'})
        order = buy(self.item.pk, self.buyer)
        page = self.b.get(f'/orders/{order.pk}/')
        self.assertContains(page, 'Purchase order'); self.assertContains(page, 'Payment made')
        self.assertNotContains(page, 'Deposit paid'); self.assertNotContains(page, 'Extend the loan')
        pay = self.b.get(f'/orders/{order.pk}/pay/')
        self.assertContains(pay, 'Pay the seller'); self.assertNotContains(pay, 'pay-breakdown')

    def test_payment_confirmations_read_as_a_purchase(self):
        self.b.post('/language/', {'lang': 'en'})
        PaymentCode.objects.create(owner=self.seller, channel='fps', image='payment-codes/x.jpg')
        order = buy(self.item.pk, self.buyer)
        act(order.pk, self.seller, 'rent')
        page = self.b.get(f'/orders/{order.pk}/pay/')
        self.assertContains(page, 'Seller confirmed; buyer has not confirmed')
        self.assertContains(page, 'You pay the seller directly'); self.assertContains(page, 'This is the order price')
        self.assertNotContains(page, 'data-confirmation="deposit"'); self.assertNotContains(page, 'pay-breakdown')
        self.assertEqual(page.context['payment_confirmations'][0]['key'], 'rent'); self.assertEqual(len(page.context['payment_confirmations']), 1)
        act(order.pk, self.buyer, 'rent')
        self.assertContains(self.b.get(f'/orders/{order.pk}/pay/'), 'data-pay-confirmed')
        order_page = self.b.get(f'/orders/{order.pk}/')
        self.assertContains(order_page, 'The buyer pays the seller directly'); self.assertContains(order_page, 'Seller')

    def test_purchase_not_counted_as_avoided_purchase(self):
        order = buy(self.item.pk, self.buyer); act(order.pk, self.buyer, 'handover'); act(order.pk, self.seller, 'handover')
        self.assertEqual(impact_summary()['borrows'], 0)
        self.assertNotContains(self.b.get(f'/orders/{order.pk}/'), 'One quick question')

    def test_dispute_resolution(self):
        staff = User.objects.create_superuser('mod', 'mod@example.org', 'x')
        order = buy(self.item.pk, self.buyer); act(order.pk, self.buyer, 'dispute')
        resolve_dispute(order.pk, staff, 'cancelled')
        self.item.refresh_from_db(); self.assertEqual(self.item.status, 'listed')
        order = buy(self.item.pk, self.buyer); act(order.pk, self.buyer, 'handover'); act(order.pk, self.buyer, 'dispute')
        with self.assertRaises(ValidationError): resolve_dispute(order.pk, staff, 'completed')
        with self.assertRaises(ValidationError): resolve_dispute(order.pk, staff, 'cancelled')
        act(order.pk, self.seller, 'handover'); order.refresh_from_db(); self.assertEqual(order.status, 'disputed')
        resolve_dispute(order.pk, staff, 'completed')
        order.refresh_from_db(); self.assertEqual(order.status, 'completed')


class SimultaneousPurchase(TransactionTestCase):
    def test_two_buyers_exactly_one_wins(self):
        seller, one, two = make_user('s2'), make_user('b2'), make_user('b3')
        item = sale_item(seller)
        barrier = Barrier(2)
        def attempt(user):
            close_old_connections(); barrier.wait()
            try:
                buy(item.pk, user); return True
            except ValidationError: return False
            finally: close_old_connections()
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(attempt, (one, two)))
        self.assertEqual(sorted(results), [False, True]); self.assertEqual(Order.objects.count(), 1)


class WantedContact(Base):
    def setUp(self):
        super().setUp(); now = timezone.now()
        self.wanted = Wanted.objects.create(owner=self.buyer, intent='buy', title='Need a book', category='study', description='x', start=now, end=now + timedelta(days=30), budget=50, location='AC1')

    def test_message_opens_one_thread_about_the_request(self):
        first = self.s.post(f'/wanted/{self.wanted.pk}/contact/'); second = self.s.post(f'/wanted/{self.wanted.pk}/contact/')
        self.assertEqual(first['Location'], second['Location']); thread = Thread.objects.get()
        self.assertEqual((thread.wanted, thread.first, thread.second), (self.wanted, self.seller, self.buyer))
        page = self.s.get(first['Location']); self.assertContains(page, f'/wanted/{self.wanted.pk}/'); self.assertContains(page, 'name="text"')
        self.assertEqual(self.s.post(first['Location'], {'text': 'I have one'}).status_code, 302)
        self.assertEqual(Message.objects.get().text, 'I have one')

    def test_cannot_message_own_request_or_when_blocked_or_guest(self):
        self.assertEqual(self.b.post(f'/wanted/{self.wanted.pk}/contact/').status_code, 403)
        UserBlock.objects.create(blocker=self.buyer, blocked=self.other)
        self.assertEqual(self.o.post(f'/wanted/{self.wanted.pk}/contact/').status_code, 403)
        self.assertEqual(Client().post(f'/wanted/{self.wanted.pk}/contact/').status_code, 302)
        self.assertFalse(Thread.objects.exists())


class ContactUnlock(Base):
    def setUp(self):
        super().setUp()
        self.seller.profile.contact_whatsapp = '+852 5555 1111'; self.seller.profile.save()
        self.buyer.profile.contact_wechat = 'buyer_wechat'; self.buyer.profile.save()
        self.thread = Thread.objects.create(item=make_item(self.seller), first=self.buyer, second=self.seller)
        self.url = f'/messages/{self.thread.pk}/'

    def say(self, user, text='hello', count=1):
        for _ in range(count): Message.objects.create(thread=self.thread, sender=user, text=text)

    def test_four_from_one_side_stay_locked(self):
        self.say(self.buyer, count=6)
        self.assertNotContains(self.b.get(self.url), '+852 5555 1111')

    def test_three_messages_stay_locked(self):
        self.say(self.buyer, count=2); self.say(self.seller)
        self.assertNotContains(self.b.get(self.url), '+852 5555 1111')
        self.assertContains(self.b.get(self.url), '3/4')

    def test_blank_messages_do_not_count(self):
        self.say(self.buyer, count=2); self.say(self.seller); self.say(self.seller, text='   ')
        self.assertNotContains(self.b.get(self.url), '+852 5555 1111')

    def test_unlocks_with_both_people_and_four_messages(self):
        self.say(self.buyer, count=2); self.say(self.seller, count=2)
        page = self.b.get(self.url)
        self.assertContains(page, '+852 5555 1111'); self.assertContains(page, 'buyer_wechat')
        self.assertContains(self.s.get(self.url), 'buyer_wechat')

    def test_count_is_per_conversation(self):
        self.say(self.buyer, count=2); self.say(self.seller, count=2)
        other = Thread.objects.create(item=make_item(self.seller), first=self.buyer, second=self.seller)
        self.assertFalse(social.contacts_unlocked(other)[0])

    def test_never_shown_outside_the_conversation(self):
        self.say(self.buyer, count=2); self.say(self.seller, count=2)
        for path in (f'/people/{self.seller.pk}/', f'/items/{self.thread.item_id}/', '/'):
            self.assertNotContains(self.b.get(path), '+852 5555 1111')
        self.assertEqual(self.o.get(self.url).status_code, 403)

    def test_blocking_hides_and_unblocking_restores(self):
        self.say(self.buyer, count=2); self.say(self.seller, count=2)
        block = UserBlock.objects.create(blocker=self.seller, blocked=self.buyer)
        self.assertNotContains(self.b.get(self.url), '+852 5555 1111')
        block.delete()
        self.assertContains(self.b.get(self.url), '+852 5555 1111')

    def test_restricted_member_contact_hidden(self):
        self.say(self.buyer, count=2); self.say(self.seller, count=2)
        self.seller.profile.restricted = True; self.seller.profile.save()
        self.assertNotContains(self.b.get(self.url), '+852 5555 1111')

    def test_profile_saves_contact_fields(self):
        self.o.post('/profile/', {'nickname': 'Other', 'contact_whatsapp': '+852 1', 'contact_phone': '', 'contact_wechat': 'w', 'contact_instagram': ''})
        self.other.profile.refresh_from_db()
        self.assertEqual((self.other.profile.contact_whatsapp, self.other.profile.contact_wechat), ('+852 1', 'w'))


class Interface(Base):
    def test_design_pages_render_in_all_languages(self):
        item = sale_item(self.seller); rental = make_item(self.seller)
        order = buy(item.pk, self.buyer)
        thread = order.thread
        pages = ['/', '/?tab=wanted', '/?intent=sale', '/buddy/', '/lost-found/', '/rules/', '/impact/', '/items/new/', '/wanted/new/', '/my/', '/messages/', f'/messages/{thread.pk}/', f'/items/{rental.pk}/', f'/orders/{order.pk}/', f'/orders/{order.pk}/pay/', '/profile/']
        for lang in ('en', 'zh', 'hans'):
            self.b.post('/language/', {'lang': lang})
            for path in pages: self.assertEqual(self.b.get(path).status_code, 200, (lang, path))

    def test_collection_pages_use_design_layout(self):
        make_item(self.seller)
        page = self.b.get('/')
        for hook in ('collection-page', 'item-grid', 'item-tile', 'filter-form', 'market-filter-tabs', 'collection-hero', 'site-header', 'mobile-primary'):
            self.assertContains(page, hook)
        self.assertContains(self.b.get('/?tab=wanted'), 'wanted-list')
        self.assertContains(self.b.get('/buddy/'), 'recruitment-list')
        self.assertContains(self.b.get('/messages/'), 'conversation-sidebar')

    def test_filter_links_keep_other_filters(self):
        page = self.b.get('/?q=camera&category=tech').content.decode()
        self.assertIn('q=camera', re.search(r'href="([^"]*intent=sale[^"]*)"', page).group(1).replace('&amp;', '&'))

    def test_sidebar_shows_only_own_conversations_with_latest_message(self):
        item = make_item(self.seller)
        mine = Thread.objects.create(item=item, first=self.buyer, second=self.seller)
        Message.objects.create(thread=mine, sender=self.seller, text='Latest words')
        theirs = Thread.objects.create(item=item, first=self.other, second=self.seller)
        Message.objects.create(thread=theirs, sender=self.other, text='Private words')
        page = self.b.get('/messages/')
        self.assertContains(page, 'Latest words'); self.assertNotContains(page, 'Private words')
