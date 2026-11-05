from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('market', '0013_chat_lines')]
    operations = [
        migrations.AddField(model_name='profile',name='searchable',field=models.BooleanField(default=True,help_text='其他成員輸入你的完整郵箱時可以找到你 / Other members can find you by entering your full email',verbose_name='允許用郵箱搜尋到我 / Let members find me by email')),
        migrations.AlterField(model_name='profile',name='request_emails',field=models.BooleanField(default=True,help_text='有人申請借用你的物品，或申請有結果時發送郵件 / Email me about new borrow requests and their results',verbose_name='借用申請郵件提醒 / Borrow request emails')),
    ]
