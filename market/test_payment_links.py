from datetime import timedelta
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from . import services
from .models import Item, PaymentCode, Profile
from io import BytesIO
from PIL import Image
import pathlib, tempfile


def person(name):
    user=User.objects.create_user(f'{name}@my.cityu.edu.hk',f'{name}@my.cityu.edu.hk')
    Profile.objects.update_or_create(user=user,defaults={'verified':True,'nickname':name.title()})
    client=Client(); client.force_login(user)
    return user,client


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PaymentPage(TestCase):
    def setUp(self):
        self.owner,self.co=person('olive')
        self.ann,self.ca=person('ann')
        self.other,self.cx=person('xavier')
        out=BytesIO(); Image.new('RGB',(30,30),'white').save(out,'JPEG')
        for channel in ('wechat','alipay_cn','alipay_hk','fps'):
            PaymentCode.objects.create(owner=self.owner,channel=channel,image=ContentFile(out.getvalue(),name=f'{channel}.jpg'))
        now=timezone.now()
        item=Item.objects.create(owner=self.owner,title='Camera',category='other',description='A camera',daily=10,deposit=50,available_start=now,available_end=now+timedelta(days=30),location='AC1')
        self.order=services.apply(item.pk,self.ann,now+timedelta(days=2),now+timedelta(days=4))
        services.act(self.order.pk,self.owner,'accept')

    def test_page_offers_four_currencies_with_hkd_first(self):
        page=self.ca.get(f'/orders/{self.order.pk}/pay/')
        self.assertEqual(page.context['currencies'],['HKD','CNY','USD','JPY'])
        html=page.content.decode()
        self.assertLess(html.index('value="HKD"'),html.index('value="CNY"'))
        self.assertIn('data-pay-total',html); self.assertIn('data-pay-amount',html)
        self.assertIn(f'HK$ {self.order.total}',html)

    def test_each_option_says_which_channel_it_is(self):
        page=self.ca.get(f'/orders/{self.order.pk}/pay/')
        for channel in ('wechat','alipay_cn','alipay_hk','fps'):
            self.assertContains(page,f'data-channel="{channel}"')
            self.assertContains(page,f'data-steps-{channel}=')

    def test_decoder_is_served_from_this_site_with_its_licence(self):
        self.assertContains(self.ca.get(f'/orders/{self.order.pk}/pay/'),'market/vendor/jsQR')
        vendor=pathlib.Path(__file__).parent/'static/market/vendor'
        self.assertTrue((vendor/'jsQR.js').exists())
        self.assertIn('Apache',(vendor/'jsQR.LICENSE.txt').read_text(encoding='utf-8'))

    def test_code_is_still_only_for_the_people_on_the_order(self):
        code=PaymentCode.objects.get(channel='wechat')
        self.assertEqual(self.ca.get(f'/media/payment/{code.pk}/').status_code,200)
        self.assertEqual(self.cx.get(f'/media/payment/{code.pk}/').status_code,403)

    def test_only_verified_app_links_are_in_the_script(self):
        script=(pathlib.Path(__file__).parent/'static/market/payment.js').read_text(encoding='utf-8')
        self.assertIn('https:\\/\\/qr\\.alipay\\.com',script)
        self.assertNotIn('alipayhk://',script)
