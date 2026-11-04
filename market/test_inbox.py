import importlib, json, re
from django.apps import apps
from datetime import timedelta
from unittest import mock
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from . import inbox, services
from .models import Friendship, ThreadRead, BuddyGroup, BuddyGroupMember, BuddyGroupMessage, BuddyPost, Item, LoginToken, Message, Notification, Order, Profile, Thread, UserBlock


def person(name):
    user=User.objects.create_user(f'{name}@my.cityu.edu.hk',f'{name}@my.cityu.edu.hk')
    Profile.objects.update_or_create(user=user,defaults={'verified':True,'nickname':name.title()})
    client=Client(); client.force_login(user)
    return user,client


def listing(owner,**extra):
    now=timezone.now()
    return Item.objects.create(**{'owner':owner,'title':'Camera','category':'other','description':'A camera','daily':10,'deposit':50,'available_start':now,'available_end':now+timedelta(days=30),'location':'AC1',**extra})


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class Base(TestCase):
    def setUp(self):
        self.owner,self.co=person('olive')
        self.ann,self.ca=person('ann')
        self.other,self.cx=person('xavier')
        Friendship.objects.create(sender=self.ann,recipient=self.owner,status='accepted')
        self.friends=Thread.objects.create(first=self.ann,second=self.owner)

    def poll(self,client,**params):
        response=client.get('/notifications/poll/',params)
        self.assertEqual(response.status_code,200)
        return response.json()

    def request_order(self,**extra):
        item=extra.pop('item',None) or listing(self.owner)
        start=timezone.now()+timedelta(days=2)
        return services.apply(item.pk,self.ann,start,start+timedelta(days=2),**extra)


class Unread(Base):
    def test_message_counts_until_the_thread_is_opened(self):
        self.ca.post(f'/messages/{self.friends.pk}/',{'text':'hello'})
        self.ca.post(f'/messages/{self.friends.pk}/',{'text':'again'})
        data=self.poll(self.co)
        self.assertEqual((data['unread']['total'],data['unread']['friend']),(2,2))
        self.assertEqual(self.poll(self.ca)['unread']['total'],0)
        self.assertContains(self.co.get('/'),'data-unread-badge')
        self.co.get(f'/messages/{self.friends.pk}/')
        self.assertEqual(self.poll(self.co)['unread']['total'],0)

    def test_message_no_longer_adds_a_notification(self):
        self.ca.post(f'/messages/{self.friends.pk}/',{'text':'hello'})
        self.assertFalse(Notification.objects.filter(user=self.owner).exists())

    def test_threads_land_in_the_right_tab(self):
        item=listing(self.owner)
        about_item=Thread.objects.create(item=item,first=self.ann,second=self.owner)
        order=self.request_order(item=item)
        self.assertEqual(inbox.thread_kind(self.friends),'friend')
        self.assertEqual(inbox.thread_kind(about_item),'item')
        self.assertEqual(inbox.thread_kind(order.thread),'request')
        purchase=Order.objects.create(kind='purchase',item=listing(self.owner,intent='sale'),borrower=self.ann,start=timezone.now(),end=timezone.now()+timedelta(days=1),rent=5,deposit=0)
        self.assertEqual(inbox.thread_kind(Thread.objects.create(order=purchase,first=self.ann,second=self.owner)),'item')

    def test_blocked_person_raises_no_alert(self):
        Message.objects.create(thread=self.friends,sender=self.ann,text='hi')
        UserBlock.objects.create(blocker=self.owner,blocked=self.ann)
        data=self.poll(self.co,m=0,g=0,n=0)
        self.assertEqual(data['unread']['total'],0)
        self.assertEqual(data['alerts'],[])

    def test_group_messages_count_and_clear(self):
        post=BuddyPost.objects.create(owner=self.owner,category='buddy',kind='other',title='Hike',description='Hike',starts=timezone.now()+timedelta(days=3),location='AC1',capacity=3)
        group=BuddyGroup.objects.create(post=post)
        BuddyGroupMember.objects.create(group=group,user=self.owner)
        post.applications.create(user=self.ann,status='accepted')
        BuddyGroupMember.objects.create(group=group,user=self.ann)
        BuddyGroupMessage.objects.create(group=group,sender=self.ann,text='see you')
        data=self.poll(self.co,m=0,g=0,n=0)
        self.assertEqual(data['unread']['friend'],1)
        self.assertEqual(data['alerts'][0]['url'],f'/messages/groups/{group.pk}/')
        fresh=self.co.get(f'/messages/groups/{group.pk}/new/',{'after':0}).json()
        self.assertIn('see you',fresh['html'])
        self.assertEqual(fresh['unread']['total'],0)


class ExistingData(Base):
    def test_migration_keeps_unread_and_reads_the_rest(self):
        # Rows as the previous version left them: old messages, then one unread "new message" note.
        old=Message.objects.create(thread=self.friends,sender=self.ann,text='old')
        Message.objects.filter(pk=old.pk).update(created=timezone.now()-timedelta(days=1))
        fresh=Message.objects.create(thread=self.friends,sender=self.ann,text='fresh')
        Notification.objects.create(user=self.owner,text='收到新訊息 / New message',url=f'/messages/{self.friends.pk}/')
        order=self.request_order()
        Notification.objects.filter(user=self.owner,url=f'/orders/{order.pk}/').update(kind='system')
        Notification.objects.create(user=self.owner,text='收到新評價 / New review',url=f'/people/{self.owner.pk}/')
        ThreadRead.objects.all().delete()
        importlib.import_module('market.migrations.0012_inbox_read_state').forward(apps,None)
        self.assertEqual(ThreadRead.objects.get(thread=self.friends,user=self.owner).last_read,old.pk)
        self.assertEqual(ThreadRead.objects.get(thread=self.friends,user=self.ann).last_read,fresh.pk)
        self.assertFalse(Notification.objects.filter(text__startswith='收到新訊息').exists())
        self.assertEqual(Notification.objects.get(user=self.owner,url=f'/orders/{order.pk}/').kind,'request')
        self.assertEqual(Notification.objects.get(text__startswith='收到新評價').kind,'system')
        self.assertEqual(inbox.counts(self.owner)['friend'],1)


class Polling(Base):
    def test_signed_out_gets_401(self):
        self.assertEqual(Client().get('/notifications/poll/').status_code,401)

    def test_first_poll_has_no_alerts_then_only_new_ones(self):
        Message.objects.create(thread=self.friends,sender=self.ann,text='old')
        first=self.poll(self.co)
        self.assertEqual(first['alerts'],[])
        Message.objects.create(thread=self.friends,sender=self.ann,text='<b>new</b>')
        second=self.poll(self.co,**first['cursors'])
        self.assertEqual(len(second['alerts']),1)
        self.assertEqual((second['alerts'][0]['title'],second['alerts'][0]['url']),('Ann',f'/messages/{self.friends.pk}/'))
        self.assertNotEqual(first['signature'],second['signature'])
        self.assertEqual(self.poll(self.co,**second['cursors'])['alerts'],[])

    def test_outsider_sees_nothing_of_a_thread(self):
        Message.objects.create(thread=self.friends,sender=self.ann,text='private')
        self.assertEqual(self.poll(self.cx,m=0,g=0,n=0)['alerts'],[])
        self.assertEqual(self.cx.get(f'/messages/{self.friends.pk}/new/').status_code,403)

    def test_live_chat_returns_only_newer_escaped_messages(self):
        old=Message.objects.create(thread=self.friends,sender=self.ann,text='old')
        Message.objects.create(thread=self.friends,sender=self.ann,text='<script>x</script>')
        data=self.co.get(f'/messages/{self.friends.pk}/new/',{'after':old.pk}).json()
        self.assertNotIn('old',data['html']); self.assertNotIn('<script>',data['html']); self.assertIn('&lt;script&gt;',data['html'])
        self.assertEqual(data['unread']['total'],0)

    def test_notification_opens_only_for_its_owner_and_marks_read(self):
        note=Notification.objects.create(user=self.owner,text='收到尋物回應 / New offer',url='/wanted/1/',kind='item')
        self.assertEqual(self.cx.get(f'/notifications/{note.pk}/open/').status_code,404)
        self.assertRedirects(self.co.get(f'/notifications/{note.pk}/open/'),'/wanted/1/',fetch_redirect_response=False)
        note.refresh_from_db(); self.assertTrue(note.read)


class Lists(Base):
    def test_notifications_have_one_row_and_their_own_page(self):
        Notification.objects.create(user=self.owner,text='System note',url='/rules/',kind='system')
        Notification.objects.create(user=self.owner,text='Item note',url='/wanted/1/',kind='item')
        page=self.co.get('/messages/')
        self.assertContains(page,'wa-notes'); self.assertContains(page,'Item note'); self.assertNotContains(page,'System note')
        self.assertContains(self.co.get('/notifications/'),'System note')
        filtered=self.co.get('/notifications/?kind=system')
        self.assertContains(filtered,'System note'); self.assertNotContains(filtered,'Item note')
        self.co.post('/notifications/',{'kind':'system'})
        self.assertEqual(self.poll(self.co)['unread']['system'],0)
        self.assertEqual(self.poll(self.co)['unread']['item'],1)

    def test_filter_shows_only_its_conversations(self):
        item_thread=Thread.objects.create(item=listing(self.owner),first=self.ann,second=self.owner)
        self.assertContains(self.co.get('/messages/?tab=item'),f'/messages/{item_thread.pk}/')
        self.assertContains(self.co.get('/messages/?tab=friend'),f'/messages/{self.friends.pk}/')
        self.assertContains(self.co.get('/messages/?tab=request'),'inbox-feed-empty')
        # The same person is one row in the full list.
        self.assertEqual(self.co.get('/messages/').content.decode().count('class="thread-row wa-row'),1)

    def test_counts_keep_chats_and_notifications_apart(self):
        Notification.objects.create(user=self.owner,text='Note',url='/rules/',kind='system')
        Message.objects.create(thread=self.friends,sender=self.ann,text='hi')
        data=self.poll(self.co)['unread']
        self.assertEqual((data['total'],data['notes'],data['chat_all'],data['chat_friend']),(2,1,1,1))

    def test_feed_fragment(self):
        Message.objects.create(thread=self.friends,sender=self.ann,text='hello there')
        response=self.co.get('/messages/feed/',{'tab':'friend'})
        self.assertContains(response,'hello there'); self.assertContains(response,'thread-unread')
        self.assertNotContains(response,'<html')

    def test_friends_page_and_old_links(self):
        self.assertContains(self.co.get('/messages/friends/'),'Ann')
        note=Notification.objects.create(user=self.owner,text='收到好友申請 / New friend request',url='/messages/#friends',kind='friend')
        self.assertRedirects(self.co.get(f'/notifications/{note.pk}/open/'),'/messages/friends/',fetch_redirect_response=False)

    def test_new_day_gets_a_date_line(self):
        old=Message.objects.create(thread=self.friends,sender=self.ann,text='old')
        Message.objects.filter(pk=old.pk).update(created=timezone.now()-timedelta(days=3))
        Message.objects.create(thread=self.friends,sender=self.ann,text='new')
        self.assertContains(self.co.get(f'/messages/{self.friends.pk}/new/',{'after':old.pk}),'day-sep')


class Requests(Base):
    def test_owner_only_sees_pending_requests(self):
        order=self.request_order()
        rows=self.poll(self.co)['requests']
        self.assertEqual([row['id'] for row in rows],[order.pk])
        self.assertEqual((rows[0]['applicant'],rows[0]['person'],rows[0]['chat_url']),('Ann',self.ann.pk,f'/messages/{order.thread.pk}/'))
        self.assertEqual(self.poll(self.ca)['requests'],[])
        services.act(order.pk,self.ann,'cancel')
        self.assertEqual(self.poll(self.co)['requests'],[])

    def test_expired_request_does_not_prompt(self):
        order=self.request_order()
        Order.objects.filter(pk=order.pk).update(start=timezone.now()-timedelta(hours=1))
        self.assertEqual(self.poll(self.co)['requests'],[])

    def test_decline_is_for_the_owner_and_notifies(self):
        order=self.request_order()
        self.ca.post(f'/orders/{order.pk}/',{'action':'decline'})
        order.refresh_from_db(); self.assertEqual(order.status,'pending')
        self.co.post(f'/orders/{order.pk}/',{'action':'decline'})
        order.refresh_from_db(); self.assertEqual(order.status,'cancelled')
        self.assertTrue(Notification.objects.filter(user=self.ann,text='物主未接受申請 / Application declined',kind='request').exists())


class RequestEmail(Base):
    def test_email_has_links_and_html_and_never_approves(self):
        order=self.request_order()
        self.assertTrue(services.email_owner_about_request(order,'https://x.test'))
        message=mail.outbox[-1]
        self.assertEqual(message.to,[self.owner.email])
        self.assertIn(f'https://x.test/orders/{order.pk}/',message.body); self.assertIn(f'https://x.test/messages/{order.thread.pk}/',message.body)
        self.assertEqual(message.alternatives[0][1],'text/html')
        self.assertIn(f'https://x.test/orders/{order.pk}/',message.alternatives[0][0])
        order.refresh_from_db(); self.assertEqual(order.status,'pending')

    def test_title_is_escaped_in_html(self):
        order=self.request_order(item=listing(self.owner,title='<img src=x>'))
        services.email_owner_about_request(order,'https://x.test')
        self.assertNotIn('<img src=x>',mail.outbox[-1].alternatives[0][0])

    def test_turning_off_is_respected(self):
        Profile.objects.filter(user=self.owner).update(request_emails=False)
        order=self.request_order()
        self.assertFalse(services.email_owner_about_request(order,'https://x.test'))
        self.assertEqual(mail.outbox,[])

    def test_failure_only_logs(self):
        order=self.request_order()
        with mock.patch('market.services.send_email',side_effect=OSError('down')),self.assertLogs('market.services','ERROR'):
            self.assertFalse(services.email_owner_about_request(order,'https://x.test'))

    def test_one_applicant_cannot_flood(self):
        order=self.request_order()
        self.assertTrue(services.email_owner_about_request(order,'https://x.test'))
        self.assertFalse(services.email_owner_about_request(order,'https://x.test'))
        self.assertEqual(len(mail.outbox),1)


class OrderNotes(Base):
    def test_opening_the_order_clears_its_notifications_only(self):
        order=self.request_order()
        other=Notification.objects.create(user=self.owner,text='Item note',url='/wanted/1/',kind='item')
        self.assertEqual(inbox.counts(self.owner)['request'],1)
        self.co.get(f'/orders/{order.pk}/')
        self.assertEqual(inbox.counts(self.owner)['request'],0)
        other.refresh_from_db(); self.assertFalse(other.read)


class ChatCard(Base):
    def test_order_uses_snapshot_price(self):
        item=listing(self.owner)
        order=self.request_order(item=item)
        Item.objects.filter(pk=item.pk).update(daily=999,title='Changed')
        page=self.ca.get(f'/messages/{order.thread.pk}/')
        self.assertContains(page,'chat-item-card'); self.assertContains(page,'Camera'); self.assertContains(page,'HK$ 10')
        self.assertNotContains(page,'HK$ 999')

    def test_action_follows_state_and_side(self):
        order=self.request_order()
        self.assertContains(self.co.get(f'/messages/{order.thread.pk}/'),'value="accept"')
        self.assertNotContains(self.ca.get(f'/messages/{order.thread.pk}/'),'value="accept"')
        services.act(order.pk,self.owner,'accept')
        self.assertContains(self.ca.get(f'/messages/{order.thread.pk}/'),f'/orders/{order.pk}/pay/')

    def test_friend_chat_has_no_card(self):
        self.assertNotContains(self.co.get(f'/messages/{self.friends.pk}/'),'chat-item-card')


class SignIn(Base):
    def code_from(self):
        return re.search(r'code on the sign-in page: (\d{6})',mail.outbox[-1].body).group(1)

    def test_code_signs_in_and_returns_to_next(self):
        client=Client()
        page=client.post('/login/',{'email':'new@my.cityu.edu.hk','next':'/rules/'})
        self.assertContains(page,'name="code"')
        response=client.post('/login/code/',{'email':'new@my.cityu.edu.hk','code':self.code_from()})
        self.assertRedirects(response,'/rules/',fetch_redirect_response=False)
        self.assertEqual(client.get('/notifications/poll/').status_code,200)
        self.assertTrue(LoginToken.objects.get().used)

    def test_code_is_in_the_subject_and_the_page_asks_only_for_it(self):
        page=Client().post('/login/',{'email':'new@my.cityu.edu.hk'})
        self.assertContains(page,'name="code"'); self.assertNotContains(page,'id="email"')
        self.assertTrue(mail.outbox[-1].subject.startswith(self.code_from()))
        self.assertContains(Client().get('/login/'),'id="email"')

    def signed_in(self,**extra):
        client=Client()
        client.post('/login/',{'email':'new@my.cityu.edu.hk'})
        client.post('/login/code/',{'email':'new@my.cityu.edu.hk','code':self.code_from(),**extra})
        return client

    def test_remembered_device_stays_signed_in(self):
        client=self.signed_in(remember='1')
        self.assertEqual(int(client.cookies['sessionid']['max-age']),60*60*24*180)
        self.assertEqual(client.get('/notifications/poll/').status_code,200)

    def test_without_remember_the_session_ends_with_the_browser(self):
        client=self.signed_in()
        self.assertEqual(client.cookies['sessionid']['max-age'],'')
        self.assertEqual(client.get('/notifications/poll/').status_code,200)

    def test_remember_works_through_the_link_too(self):
        client=Client()
        client.post('/login/',{'email':'new@my.cityu.edu.hk'})
        path=re.search(r'http://testserver(/verify/\S+)',mail.outbox[-1].body).group(1)
        self.assertContains(client.get(path,follow=True),'name="remember"')
        client.post(path.split('?')[0],{'remember':'1'})
        self.assertEqual(int(client.cookies['sessionid']['max-age']),60*60*24*180)

    def test_five_wrong_codes_end_it(self):
        client=Client()
        client.post('/login/',{'email':'new@my.cityu.edu.hk'})
        code=self.code_from()
        wrong='000000' if code!='000000' else '111111'
        for _ in range(5): self.assertContains(client.post('/login/code/',{'email':'new@my.cityu.edu.hk','code':wrong}),'驗證碼不正確')
        self.assertContains(client.post('/login/code/',{'email':'new@my.cityu.edu.hk','code':code}),'驗證碼不正確')
        self.assertFalse(User.objects.filter(username='new@my.cityu.edu.hk').exists())

    def test_link_carries_language_and_get_does_not_consume(self):
        client=Client()
        client.post('/language/',{'lang':'en'})
        client.post('/login/',{'email':'new@my.cityu.edu.hk'})
        path=re.search(r'http://testserver(/verify/\S+)',mail.outbox[-1].body).group(1)
        self.assertIn('?lang=en',path)
        other=Client()
        response=other.get(path,follow=True)
        self.assertContains(response,'Confirm sign-in')
        self.assertFalse(LoginToken.objects.get().used)

    def test_html_part_goes_through_resend(self):
        with override_settings(EMAIL_BACKEND='market.mail.ResendBackend',RESEND_API_KEY='re_test'),mock.patch('market.mail.urlopen') as urlopen:
            Client().post('/login/',{'email':'new@my.cityu.edu.hk'})
        body=json.loads(urlopen.call_args.args[0].data)
        self.assertIn('<html',body['html']); self.assertRegex(body['text'],r'\d{6}')
