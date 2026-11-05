import json, re
from datetime import timedelta
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from . import services
from .models import Item, Notification, Order, Profile


def person(name):
    user=User.objects.create_user(f'{name}@my.cityu.edu.hk',f'{name}@my.cityu.edu.hk')
    Profile.objects.update_or_create(user=user,defaults={'verified':True,'nickname':name.title()})
    client=Client(); client.force_login(user)
    return user,client


def day(days,hour=10):
    # A local date and time this many days ahead.
    return (timezone.localtime()+timedelta(days=days)).replace(hour=hour,minute=0,second=0,microsecond=0)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class Base(TestCase):
    def setUp(self):
        self.owner,self.co=person('olive')
        self.ann,self.ca=person('ann')
        self.bob,self.cb=person('bob')
        self.item=Item.objects.create(owner=self.owner,title='Camera',category='other',description='A camera',daily=10,deposit=50,available_start=day(-1),available_end=day(40),location='AC1',max_days=7)

    def booked(self): return json.loads(services.booking_calendar(self.item))['booked']
    def iso(self,days): return day(days).strftime('%Y-%m-%d')
    def request(self,user,first,last): return services.apply(self.item.pk,user,day(first),day(last,18))
    def accepted(self,user,first,last):
        order=self.request(user,first,last)
        return services.act(order.pk,self.owner,'accept')


class Occupied(Base):
    def test_only_a_confirmed_order_takes_the_days(self):
        pending=self.request(self.ann,5,6)
        self.assertEqual(self.booked(),[])
        services.act(pending.pk,self.owner,'accept')
        self.assertEqual(self.booked(),[self.iso(5),self.iso(6)])

    def test_every_day_of_the_order_is_taken_including_partial_days(self):
        self.accepted(self.ann,5,7)
        self.assertEqual(self.booked(),[self.iso(5),self.iso(6),self.iso(7)])

    def test_a_midnight_end_does_not_take_the_next_day(self):
        order=services.apply(self.item.pk,self.ann,day(5),day(7,0))
        services.act(order.pk,self.owner,'accept')
        self.assertEqual(self.booked(),[self.iso(5),self.iso(6)])

    def test_listing_page_carries_the_days_but_not_who_booked(self):
        self.accepted(self.ann,5,6)
        page=self.cb.get(f'/items/{self.item.pk}/')
        self.assertContains(page,'data-booking-calendar')
        data=json.loads(re.search(r'data-calendar="([^"]+)"',page.content.decode()).group(1).replace('&quot;','"'))
        self.assertEqual(data['booked'],[self.iso(5),self.iso(6)])
        self.assertEqual(data['maxDays'],7)
        self.assertNotIn(self.ann.email,page.content.decode())

    def test_window_runs_from_now_to_the_end_of_the_listing(self):
        data=json.loads(services.booking_calendar(self.item))
        self.assertEqual(data['last'],self.iso(40))
        self.assertGreaterEqual(data['first'],timezone.localtime().strftime('%Y-%m-%d'))

    def test_sale_listing_and_owner_get_no_calendar(self):
        sale=Item.objects.create(owner=self.owner,title='Lamp',intent='sale',category='other',description='A lamp',daily=10,deposit=0,available_start=day(-1),available_end=day(40),location='AC1')
        self.assertNotContains(self.cb.get(f'/items/{sale.pk}/'),'data-booking-calendar')
        self.assertNotContains(self.co.get(f'/items/{self.item.pk}/'),'data-booking-calendar')


class FirstComeFirstServed(Base):
    def test_a_taken_day_cannot_be_requested_even_by_hand(self):
        self.accepted(self.ann,5,6)
        for first,last in ((5,5),(6,8),(3,5),(3,8)):
            with self.assertRaises(ValidationError): self.request(self.bob,first,last)
        # The same day at a later hour is still the same day.
        with self.assertRaises(ValidationError): services.apply(self.item.pk,self.bob,day(6,20),day(7,10))

    def test_form_explains_a_taken_day(self):
        self.accepted(self.ann,5,6)
        page=self.cb.post(f'/items/{self.item.pk}/',{'start':day(5).strftime('%Y-%m-%dT%H:%M'),'end':day(5,18).strftime('%Y-%m-%dT%H:%M'),'action':'quote'})
        self.assertContains(page,'已被預約')
        self.assertFalse(Order.objects.filter(borrower=self.bob).exists())

    def test_neighbouring_days_stay_open(self):
        self.accepted(self.ann,5,6)
        self.request(self.bob,7,8)
        self.request(self.bob,3,4)
        self.assertEqual(Order.objects.filter(borrower=self.bob).count(),2)

    def test_two_people_may_wait_on_a_day_and_the_first_confirmed_wins(self):
        first=self.request(self.ann,5,6)
        second=self.request(self.bob,6,7)
        services.act(second.pk,self.owner,'accept')
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((second.status,first.status),('accepted','cancelled'))
        with self.assertRaises(ValidationError): services.act(first.pk,self.owner,'accept')

    def test_the_request_that_lost_out_is_told(self):
        first=self.request(self.ann,5,6)
        second=self.request(self.bob,6,7)
        mail.outbox.clear()
        self.co.post(f'/orders/{second.pk}/',{'action':'accept'})
        self.assertTrue(Notification.objects.filter(user=self.ann,url=f'/orders/{first.pk}/',text__startswith='該時段').exists())
        lost=[m for m in mail.outbox if m.to==[self.ann.email]]
        self.assertEqual(len(lost),1)
        self.assertIn('#f59e0b',lost[0].alternatives[0][0])
        self.assertIn('其他人預約',lost[0].body)

    def test_requests_for_other_days_or_items_are_untouched(self):
        other_days=self.request(self.ann,10,11)
        other_item=Item.objects.create(owner=self.owner,title='Lens',category='other',description='A lens',daily=10,deposit=0,available_start=day(-1),available_end=day(40),location='AC1')
        elsewhere=services.apply(other_item.pk,self.ann,day(5),day(6,18))
        self.accepted(self.bob,5,6)
        other_days.refresh_from_db(); elsewhere.refresh_from_db()
        self.assertEqual((other_days.status,elsewhere.status),('pending','pending'))

    def test_extension_takes_days_and_closes_waiting_requests(self):
        order=self.accepted(self.ann,5,6)
        waiting=self.request(self.bob,8,9)
        services.act(order.pk,self.ann,'extend',new_end=day(9,18))
        services.act(order.pk,self.owner,'approve_extension')
        waiting.refresh_from_db()
        self.assertEqual(waiting.status,'cancelled')
        self.assertIn(self.iso(9),self.booked())


class Reopening(Base):
    def test_declining_leaves_the_days_open(self):
        order=self.request(self.ann,5,6)
        self.co.post(f'/orders/{order.pk}/',{'action':'decline'})
        self.assertEqual(self.booked(),[])
        self.request(self.bob,5,6)

    def test_cancelling_a_confirmed_order_reopens_its_days(self):
        order=self.accepted(self.ann,5,6)
        self.assertTrue(self.booked())
        self.co.post(f'/orders/{order.pk}/',{'action':'cancel'})
        self.assertEqual(self.booked(),[])
        again=self.request(self.bob,5,6)
        services.act(again.pk,self.owner,'accept')
        self.assertEqual(self.booked(),[self.iso(5),self.iso(6)])

    def test_finished_loans_free_their_days(self):
        order=self.accepted(self.ann,5,6)
        Order.objects.filter(pk=order.pk).update(status='completed')
        self.assertEqual(self.booked(),[])
