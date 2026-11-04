import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def fill_request_details(apps,schema_editor):
    # Existing "new request" notifications say who is asking, like the new ones do.
    Notification=apps.get_model('market','Notification')
    Order=apps.get_model('market','Order')
    for note in Notification.objects.filter(text__startswith='申請借用',url__startswith='/orders/'):
        try: pk=int(note.url.split('/')[2])
        except (IndexError,ValueError): continue
        order=Order.objects.select_related('borrower__profile','item').filter(pk=pk).first()
        if order is None: continue
        title=order.snapshot.get('title') or order.item.title
        note.detail=f'{order.borrower.profile.nickname} · {title}'[:200]
        note.save(update_fields=['detail'])


def line_fields(model):
    return [
        migrations.AlterField(model_name=model,name='text',field=models.TextField(blank=True,max_length=2000)),
        migrations.AddField(model_name=model,name='image',field=models.ImageField(blank=True,upload_to='chat/')),
        migrations.AddField(model_name=model,name='reply_to',field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='+',to=f'market.{model}')),
        migrations.AddField(model_name=model,name='forwarded',field=models.BooleanField(default=False)),
        migrations.AddField(model_name=model,name='recalled',field=models.BooleanField(default=False)),
        migrations.AddField(model_name=model,name='recalled_at',field=models.DateTimeField(blank=True,null=True)),
    ]


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('market', '0012_inbox_read_state'),
    ]
    operations = line_fields('message')+line_fields('buddygroupmessage')+[
        migrations.AddField(model_name='notification',name='detail',field=models.CharField(blank=True,default='',max_length=200)),
        migrations.RunPython(fill_request_details,migrations.RunPython.noop),
    ]
