from datetime import timedelta
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

MESSAGE_NOTES = ('收到新訊息 / New message','Buddy 群聊有新訊息 / New Buddy group message')


def kind_of(note,purchases):
    url=note.url
    if url.startswith('/orders/'):
        try: return 'item' if int(url.split('/')[2]) in purchases else 'request'
        except (IndexError,ValueError): return 'request'
    if note.text.startswith(('收到新評價','糾紛已處理')): return 'system'
    if url.startswith(('/wanted/','/items/','/lost-found/')): return 'item'
    if url.startswith(('/buddy/','/messages/','/people/')): return 'friend'
    return 'system'


def forward(apps,schema_editor):
    Notification=apps.get_model('market','Notification')
    Order=apps.get_model('market','Order')
    Thread=apps.get_model('market','Thread')
    Message=apps.get_model('market','Message')
    GroupMessage=apps.get_model('market','BuddyGroupMessage')
    ThreadRead=apps.get_model('market','ThreadRead')
    BuddyGroupMember=apps.get_model('market','BuddyGroupMember')
    purchases=set(Order.objects.filter(kind='purchase').values_list('pk',flat=True))
    # What was unread before stays unread: the old "new message" note marks where the reader stopped.
    unread_since={(note.user_id,note.url):note.created for note in Notification.objects.filter(read=False,text__in=MESSAGE_NOTES).order_by('-created')}
    def last_read(messages,user_id,url):
        since=unread_since.get((user_id,url))
        if since: messages=messages.filter(created__lt=since-timedelta(seconds=1))
        return messages.aggregate(last=models.Max('pk'))['last'] or 0
    markers=[]
    for thread in Thread.objects.all():
        messages=Message.objects.filter(thread_id=thread.pk)
        if not messages.exists(): continue
        url=f'/messages/{thread.pk}/'
        markers+=[ThreadRead(thread_id=thread.pk,user_id=user_id,last_read=last_read(messages,user_id,url)) for user_id in (thread.first_id,thread.second_id)]
    ThreadRead.objects.bulk_create(markers)
    for row in BuddyGroupMember.objects.all():
        row.last_read=last_read(GroupMessage.objects.filter(group_id=row.group_id),row.user_id,f'/messages/groups/{row.group_id}/')
        row.save(update_fields=['last_read'])
    Notification.objects.filter(text__in=MESSAGE_NOTES).delete()
    for note in Notification.objects.all():
        kind=kind_of(note,purchases)
        if kind!='system': Notification.objects.filter(pk=note.pk).update(kind=kind)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('market', '0011_content_translation'),
    ]
    operations = [
        migrations.AddField(model_name='notification',name='kind',field=models.CharField(choices=[('system','系統更新 / System'),('item','物品通知 / Items'),('friend','好友 / Friends'),('request','借用申請 / Borrowing')],default='system',max_length=10)),
        migrations.AddField(model_name='buddygroupmember',name='last_read',field=models.PositiveBigIntegerField(default=0)),
        migrations.AddField(model_name='profile',name='request_emails',field=models.BooleanField(default=True,help_text='有人申請借用你的物品時發送郵件提醒 / Email me when someone asks to borrow my item',verbose_name='借用申請郵件提醒 / Borrow request emails')),
        migrations.AddField(model_name='logintoken',name='code_digest',field=models.CharField(blank=True,default='',max_length=64)),
        migrations.AddField(model_name='logintoken',name='code_attempts',field=models.PositiveSmallIntegerField(default=0)),
        migrations.CreateModel(name='ThreadRead',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('last_read',models.PositiveBigIntegerField(default=0)),
            ('thread',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='read_markers',to='market.thread')),
            ('user',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='+',to=settings.AUTH_USER_MODEL)),
        ],options={'constraints':[models.UniqueConstraint(fields=('thread','user'),name='one_read_marker_each')]}),
        migrations.AddIndex(model_name='notification',index=models.Index(fields=['user','read'],name='market_note_user_read')),
        migrations.RunPython(forward,migrations.RunPython.noop),
    ]
