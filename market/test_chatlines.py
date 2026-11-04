from datetime import timedelta
from io import BytesIO
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from . import groups, inbox, services, social, translate
from .models import BuddyGroup, BuddyGroupMember, BuddyPost, Friendship, Item, Message, Notification, Profile, Thread
import tempfile


def person(name):
    user=User.objects.create_user(f'{name}@my.cityu.edu.hk',f'{name}@my.cityu.edu.hk')
    Profile.objects.update_or_create(user=user,defaults={'verified':True,'nickname':name.title(),'major':'Computer Science'})
    client=Client(); client.force_login(user)
    return user,client


def photo():
    out=BytesIO(); Image.new('RGB',(40,30),'red').save(out,'PNG')
    return SimpleUploadedFile('p.png',out.getvalue(),content_type='image/png')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(),EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class Base(TestCase):
    def setUp(self):
        self.owner,self.co=person('olive')
        self.ann,self.ca=person('ann')
        self.other,self.cx=person('xavier')
        Friendship.objects.create(sender=self.ann,recipient=self.owner,status='accepted')
        self.chat=Thread.objects.create(first=self.ann,second=self.owner)
        now=timezone.now()
        self.item=Item.objects.create(owner=self.owner,title='Camera',category='other',description='A camera',daily=10,deposit=50,available_start=now,available_end=now+timedelta(days=30),location='AC1')

    def order(self):
        start=timezone.now()+timedelta(days=2)
        return services.apply(self.item.pk,self.ann,start,start+timedelta(days=2))

    def say(self,text='hello',sender=None,thread=None): return Message.objects.create(thread=thread or self.chat,sender=sender or self.ann,text=text)
    def line(self,client,message,**data): return client.post(f'/messages/line/message/{message.pk}/',data)


class OneConversation(Base):
    def test_one_row_per_person_with_all_unread(self):
        order=self.order()
        self.say('from chat'); self.say('about order',thread=order.thread)
        rows=[row for row in inbox.feed_rows(self.owner,'en') if row['type']=='thread']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['unread'],2)
        self.assertEqual(self.co.get('/messages/').content.decode().count('class="thread-row wa-row'),2)

    def test_conversation_shows_everything_and_reads_all_of_it(self):
        order=self.order()
        self.say('from chat'); self.say('about order',thread=order.thread)
        page=self.co.get(f'/messages/{self.chat.pk}/')
        self.assertContains(page,'from chat'); self.assertContains(page,'about order')
        self.assertEqual(inbox.counts(self.owner)['chat_all'],0)

    def test_request_is_a_message_with_applicant_details_and_actions(self):
        order=self.order()
        owner_page=self.co.get(f'/messages/{self.chat.pk}/')
        self.assertContains(owner_page,'order-line'); self.assertContains(owner_page,'Ann · Computer Science')
        self.assertContains(owner_page,'value="decline"')
        applicant_page=self.ca.get(f'/messages/{self.chat.pk}/')
        self.assertContains(applicant_page,'order-line'); self.assertNotContains(applicant_page,'value="decline"')
        self.co.post(f'/orders/{order.pk}/',{'action':'accept'})
        self.assertNotContains(self.co.get(f'/messages/{self.chat.pk}/'),'value="decline"')

    def test_request_fills_the_list_preview_and_notification(self):
        self.order()
        self.assertContains(self.co.get('/messages/'),'Camera')
        note=Notification.objects.get(user=self.owner,kind='request')
        self.assertEqual(note.detail[:3],'Ann')
        self.assertContains(self.co.get('/notifications/'),'Ann · Camera')

    def test_message_goes_to_an_open_thread_when_this_one_is_closed(self):
        order=self.order()
        Friendship.objects.all().delete()
        self.co.post(f'/messages/{self.chat.pk}/',{'text':'still reachable'})
        self.assertEqual(Message.objects.get(text='still reachable').thread_id,order.thread.pk)

    def test_no_popup_for_the_person_already_open(self):
        first=self.co.get('/notifications/poll/').json()
        self.say('new')
        alert=self.co.get('/notifications/poll/',first['cursors']).json()['alerts'][0]
        self.assertEqual(alert['person'],self.ann.pk)

    def test_messages_with_the_same_timestamp_keep_their_order(self):
        first=self.say('first'); second=self.say('second')
        Message.objects.filter(pk__in=[first.pk,second.pk]).update(created=first.created)
        page=self.co.get(f'/messages/{self.chat.pk}/').content.decode().split('data-live-url')[1]
        self.assertLess(page.index('>first<'),page.index('>second<'))

    def test_outsider_is_refused(self):
        self.assertEqual(self.cx.get(f'/messages/{self.chat.pk}/').status_code,403)


class Quote(Base):
    def test_quote_shows_in_the_reply(self):
        original=self.say('original words')
        self.co.post(f'/messages/{self.chat.pk}/',{'text':'my answer','reply_to':original.pk})
        reply=Message.objects.get(text='my answer')
        self.assertEqual(reply.reply_to,original)
        self.assertContains(self.ca.get(f'/messages/{self.chat.pk}/'),'bubble-quote')

    def test_cannot_quote_someone_elses_conversation(self):
        foreign=Message.objects.create(thread=Thread.objects.create(first=self.other,second=self.owner),sender=self.other,text='secret')
        self.ca.post(f'/messages/{self.chat.pk}/',{'text':'peek','reply_to':foreign.pk})
        self.assertIsNone(Message.objects.get(text='peek').reply_to)

    def test_quote_of_a_recalled_message_hides_its_text(self):
        original=self.say('take this back')
        self.co.post(f'/messages/{self.chat.pk}/',{'text':'answer','reply_to':original.pk})
        self.line(self.ca,original,action='recall')
        self.assertNotContains(self.co.get(f'/messages/{self.chat.pk}/'),'take this back')


class Photos(Base):
    def test_photo_only_message_is_private_to_the_conversation(self):
        self.ca.post(f'/messages/{self.chat.pk}/',{'text':'','image':photo()})
        message=Message.objects.get()
        self.assertTrue(message.image.name.endswith('.jpg'))
        self.assertEqual(self.co.get(f'/media/message/{message.pk}/').status_code,200)
        self.assertEqual(self.cx.get(f'/media/message/{message.pk}/').status_code,403)
        self.assertEqual(Client().get(f'/media/message/{message.pk}/').status_code,403)
        self.assertContains(self.co.get('/messages/'),'[圖片]')

    def test_bad_upload_and_empty_message_are_refused(self):
        bad=SimpleUploadedFile('x.png',b'not an image',content_type='image/png')
        self.ca.post(f'/messages/{self.chat.pk}/',{'text':'','image':bad})
        self.ca.post(f'/messages/{self.chat.pk}/',{'text':'  '})
        self.assertFalse(Message.objects.exists())

    def test_recalled_photo_stops_being_served(self):
        self.ca.post(f'/messages/{self.chat.pk}/',{'text':'','image':photo()})
        message=Message.objects.get()
        self.line(self.ca,message,action='recall')
        self.assertEqual(self.co.get(f'/media/message/{message.pk}/').status_code,404)


class Recall(Base):
    def test_sender_recalls_for_both_within_two_minutes(self):
        message=self.say('oops')
        self.line(self.ca,message,action='recall')
        for client in (self.ca,self.co):
            page=client.get(f'/messages/{self.chat.pk}/')
            self.assertNotContains(page,'oops'); self.assertContains(page,'撤回了一條訊息')
        message.refresh_from_db(); self.assertTrue(message.recalled)
        self.assertEqual(message.text,'oops')
        self.assertEqual(inbox.counts(self.owner)['chat_all'],0)

    def test_too_late_or_not_the_sender(self):
        late=self.say('late')
        Message.objects.filter(pk=late.pk).update(created=timezone.now()-timedelta(seconds=121))
        self.line(self.ca,late,action='recall')
        late.refresh_from_db(); self.assertFalse(late.recalled)
        fresh=self.say('fresh')
        self.assertEqual(self.line(self.co,fresh,action='recall').status_code,403)
        self.assertEqual(self.line(self.cx,fresh,action='recall').status_code,403)

    def test_recall_reaches_an_open_page(self):
        message=self.say('oops')
        before=self.co.get('/notifications/poll/').json()['signature']
        self.line(self.ca,message,action='recall')
        self.assertNotEqual(self.co.get('/notifications/poll/').json()['signature'],before)
        data=self.co.get(f'/messages/{self.chat.pk}/new/',{'after':message.pk}).json()
        self.assertIn('撤回',data['recalled'][str(message.pk)])

    def test_recalled_cannot_be_translated_or_counted_for_contacts(self):
        message=self.say('hidden words')
        self.line(self.ca,message,action='recall')
        self.assertIsNone(translate.source(f'message:{message.pk}',self.owner))
        for _ in range(4): self.line(self.ca,self.say('x'),action='recall')
        self.assertEqual(social.contacts_unlocked(self.chat)[1],0)


class DeleteFromDevice(Base):
    def test_server_keeps_serving_it_and_offers_the_control(self):
        message=self.say('keep on the server')
        page=self.co.get(f'/messages/{self.chat.pk}/')
        self.assertContains(page,'keep on the server')
        self.assertContains(page,f'data-delete-line="message:{message.pk}"')
        self.assertContains(self.co.get('/messages/'),f'data-last-line="message:{message.pk}"')

    def test_there_is_no_server_side_delete(self):
        message=self.say('stays')
        self.assertEqual(self.line(self.co,message,action='hide').status_code,404)
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())


class Forward(Base):
    def setUp(self):
        super().setUp()
        Friendship.objects.create(sender=self.other,recipient=self.owner,status='accepted')
        self.second=Thread.objects.create(first=self.other,second=self.owner)

    def test_forward_copies_and_marks(self):
        message=self.say('pass this on')
        url=f'/messages/line/message/{message.pk}/forward/'
        self.assertContains(self.co.get(url),f'thread:{self.second.pk}')
        self.co.post(url,{'target':f'thread:{self.second.pk}'})
        copy=Message.objects.get(thread=self.second)
        self.assertEqual((copy.text,copy.forwarded,copy.sender),('pass this on',True,self.owner))
        self.assertContains(self.cx.get(f'/messages/{self.second.pk}/'),'已轉發')

    def test_cannot_forward_what_you_cannot_see_or_to_a_stranger(self):
        message=self.say('private')
        self.assertEqual(self.cx.post(f'/messages/line/message/{message.pk}/forward/',{'target':f'thread:{self.second.pk}'}).status_code,403)
        self.assertEqual(self.ca.post(f'/messages/line/message/{message.pk}/forward/',{'target':f'thread:{self.second.pk}'}).status_code,403)
        self.assertFalse(Message.objects.filter(thread=self.second).exists())

    def test_recalled_cannot_be_forwarded(self):
        message=self.say('gone')
        self.line(self.ca,message,action='recall')
        self.co.post(f'/messages/line/message/{message.pk}/forward/',{'target':f'thread:{self.second.pk}'})
        self.assertFalse(Message.objects.filter(thread=self.second).exists())

    def test_forwarded_photo_is_served_to_the_new_reader(self):
        self.ca.post(f'/messages/{self.chat.pk}/',{'text':'','image':photo()})
        message=Message.objects.get()
        self.co.post(f'/messages/line/message/{message.pk}/forward/',{'target':f'thread:{self.second.pk}'})
        copy=Message.objects.get(thread=self.second)
        self.assertEqual(self.cx.get(f'/media/message/{copy.pk}/').status_code,200)
        self.assertEqual(self.cx.get(f'/media/message/{message.pk}/').status_code,403)


class GroupLines(Base):
    def setUp(self):
        super().setUp()
        post=BuddyPost.objects.create(owner=self.owner,category='buddy',kind='other',title='Hike',description='Hike',starts=timezone.now()+timedelta(days=3),location='AC1',capacity=3)
        self.group=BuddyGroup.objects.create(post=post)
        BuddyGroupMember.objects.create(group=self.group,user=self.owner)
        post.applications.create(user=self.ann,status='accepted')
        BuddyGroupMember.objects.create(group=self.group,user=self.ann)
        self.url=f'/messages/groups/{self.group.pk}/'

    def test_photo_quote_and_recall(self):
        self.ca.post(self.url,{'action':'send','text':'','image':photo()})
        picture=self.group.messages.get()
        self.assertEqual(self.co.get(f'/media/groupmessage/{picture.pk}/').status_code,200)
        self.assertEqual(self.cx.get(f'/media/groupmessage/{picture.pk}/').status_code,403)
        self.co.post(self.url,{'action':'send','text':'nice','reply_to':picture.pk})
        reply=self.group.messages.get(text='nice')
        self.assertEqual(reply.reply_to,picture)
        self.ca.post(f'/messages/line/group/{picture.pk}/',{'action':'recall'})
        picture.refresh_from_db(); self.assertTrue(picture.recalled)
        self.assertContains(self.co.get(self.url),f'data-delete-line="group:{reply.pk}"')
