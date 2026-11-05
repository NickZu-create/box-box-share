import pathlib, re
from datetime import timedelta
from unittest import mock
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from . import i18n, services
from .models import Item, Profile, UserBlock


def person(name,**profile):
    user=User.objects.create_user(f'{name}@my.cityu.edu.hk',f'{name}@my.cityu.edu.hk')
    Profile.objects.update_or_create(user=user,defaults={'verified':True,'nickname':name.title(),**profile})
    client=Client(); client.force_login(user)
    return user,client


def listing(owner,**extra):
    now=timezone.now()
    return Item.objects.create(**{'owner':owner,'title':'Camera','category':'other','description':'A camera','daily':10,'deposit':50,'available_start':now,'available_end':now+timedelta(days=30),'location':'AC1',**extra})


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class Base(TestCase):
    def setUp(self):
        self.owner,self.co=person('olive',bio='I lend cameras',contact_phone='+852 5555 1111')
        self.ann,self.ca=person('ann')
        self.item=listing(self.owner)

    def order(self):
        start=timezone.now()+timedelta(days=2)
        return services.apply(self.item.pk,self.ann,start,start+timedelta(days=2))


class ResultMail(Base):
    def only_mail(self):
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(mail.outbox[0].to,[self.ann.email])
        return mail.outbox[0]

    def test_accept_mails_the_applicant_in_green(self):
        order=self.order()
        self.co.post(f'/orders/{order.pk}/',{'action':'accept'})
        message=self.only_mail()
        html=message.alternatives[0][0]
        self.assertIn('#16a34a',html); self.assertNotIn('#f59e0b',html)
        self.assertIn(f'/orders/{order.pk}/',html); self.assertIn('Olive',message.body)

    def test_decline_mails_the_applicant_in_yellow(self):
        order=self.order()
        self.co.post(f'/orders/{order.pk}/',{'action':'decline'})
        html=self.only_mail().alternatives[0][0]
        self.assertIn('#f59e0b',html); self.assertNotIn('#16a34a',html)

    def test_owner_cancelling_a_pending_request_counts_as_declining(self):
        order=self.order()
        self.co.post(f'/orders/{order.pk}/',{'action':'cancel'})
        self.assertIn('#f59e0b',self.only_mail().alternatives[0][0])

    def test_applicant_cancelling_or_later_steps_send_nothing(self):
        order=self.order()
        self.ca.post(f'/orders/{order.pk}/',{'action':'cancel'})
        self.assertEqual(mail.outbox,[])
        second=self.order()
        self.co.post(f'/orders/{second.pk}/',{'action':'accept'})
        mail.outbox.clear()
        self.co.post(f'/orders/{second.pk}/',{'action':'cancel'})
        self.assertEqual(mail.outbox,[])

    def test_refused_action_sends_nothing(self):
        order=self.order()
        self.ca.post(f'/orders/{order.pk}/',{'action':'accept'})
        self.assertEqual(mail.outbox,[])

    def test_applicant_can_turn_it_off(self):
        Profile.objects.filter(user=self.ann).update(request_emails=False)
        order=self.order()
        self.co.post(f'/orders/{order.pk}/',{'action':'accept'})
        self.assertEqual(mail.outbox,[])

    def test_mail_failure_never_blocks_the_decision(self):
        order=self.order()
        with mock.patch('market.services.send_email',side_effect=OSError('down')),self.assertLogs('market.services','ERROR'):
            self.co.post(f'/orders/{order.pk}/',{'action':'accept'})
        order.refresh_from_db(); self.assertEqual(order.status,'accepted')

    def test_title_is_escaped(self):
        self.item.title='<img src=x>'; self.item.save()
        order=self.order()
        self.co.post(f'/orders/{order.pk}/',{'action':'accept'})
        self.assertNotIn('<img src=x>',mail.outbox[0].alternatives[0][0])


class Simplified(TestCase):
    BANNED=('温书','食饭','打波','这部装置')

    def test_interface_text_has_no_cantonese_once_simplified(self):
        root=pathlib.Path(__file__).parent
        files=[*root.rglob('*.html'),*root.rglob('*.py'),*root.rglob('*.js')]
        for path in files:
            if 'migrations' in path.parts or path.name.startswith('test') or path.name=='i18n.py': continue
            for text in re.findall(r"[^'\"<>{}]*[㐀-鿿][^'\"<>{}]*",path.read_text(encoding='utf-8',errors='ignore')):
                converted=i18n.zh(text,'hans')
                for word in self.BANNED: self.assertNotIn(word,converted,f'{path.name}: {text}')

    def test_members_keep_their_own_words(self):
        self.assertEqual(i18n.hans('溫書'),'温书')

    def test_the_buddy_line_reads_as_standard_chinese(self):
        client=Client()
        client.post('/language/',{'lang':'hans'})
        self.assertContains(client.get('/buddy/'),'复习、打球、吃饭')
        client.post('/language/',{'lang':'zh'})
        self.assertContains(client.get('/buddy/'),'溫書、打波、食飯')


class Search(Base):
    def find(self,client,email): return client.post('/people/search/',{'email':email})

    def test_full_email_finds_the_member_case_insensitively(self):
        page=self.find(self.ca,'OLIVE@my.cityu.edu.hk')
        self.assertContains(page,f'/people/{self.owner.pk}/'); self.assertContains(page,'I lend cameras')
        self.assertNotContains(page,'+852 5555 1111')

    def test_partial_email_finds_nothing(self):
        for text in ('olive','olive@','@my.cityu.edu.hk','oliv@my.cityu.edu.hk'):
            self.assertNotContains(self.find(self.ca,text),f'/people/{self.owner.pk}/')

    def test_members_who_cannot_be_found(self):
        hidden,_=person('hidden',searchable=False)
        unverified,_=person('never',verified=False)
        restricted,_=person('banned',restricted=True)
        blocked,_=person('blocked')
        UserBlock.objects.create(blocker=blocked,blocked=self.ann)
        for user in (hidden,unverified,restricted,blocked):
            self.assertNotContains(self.find(self.ca,user.email),f'/people/{user.pk}/')

    def test_only_members_can_search(self):
        self.assertEqual(Client().post('/people/search/',{'email':self.owner.email}).status_code,302)

    def test_search_is_rate_limited(self):
        for _ in range(30): self.find(self.ca,self.owner.email)
        self.assertNotContains(self.find(self.ca,self.owner.email),f'/people/{self.owner.pk}/')

    def test_email_stays_out_of_the_address_bar(self):
        self.assertNotContains(self.ca.get('/people/search/',{'email':self.owner.email}),f'/people/{self.owner.pk}/')


class PersonPage(Base):
    def test_shows_listed_items_with_the_right_request(self):
        sale=listing(self.owner,title='Desk lamp',intent='sale')
        listing(self.owner,title='Paused thing',status='paused')
        page=self.ca.get(f'/people/{self.owner.pk}/')
        self.assertContains(page,'Camera'); self.assertContains(page,'Desk lamp'); self.assertNotContains(page,'Paused thing')
        self.assertContains(page,f'href="/items/{self.item.pk}/"'); self.assertContains(page,f'href="/items/{sale.pk}/"')
        self.assertContains(page,'申請借用'); self.assertContains(page,'申請購買')
        self.assertContains(page,'value="request"')

    def test_email_and_contacts_stay_private(self):
        page=self.ca.get(f'/people/{self.owner.pk}/')
        self.assertNotContains(page,self.owner.email); self.assertNotContains(page,'+852 5555 1111')

    def test_blocked_member_sees_no_items(self):
        UserBlock.objects.create(blocker=self.owner,blocked=self.ann)
        self.assertNotContains(self.ca.get(f'/people/{self.owner.pk}/'),'申請借用')

    def test_profile_setting_saves(self):
        data={'nickname':'Ann','request_emails':'on'}
        self.ca.post('/profile/',data)
        self.assertFalse(Profile.objects.get(user=self.ann).searchable)
