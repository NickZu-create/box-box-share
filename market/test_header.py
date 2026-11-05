from django.contrib.auth.models import User
from django.test import Client, TestCase
from .models import Profile


class Header(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('lin@my.cityu.edu.hk','lin@my.cityu.edu.hk')
        Profile.objects.update_or_create(user=self.user,defaults={'verified':True,'nickname':'Lin Chan'})
        self.member=Client(); self.member.force_login(self.user)

    def actions(self,client,path='/'):
        page=client.get(path).content.decode()
        return page.split('class="header-actions"')[1].split('</header>')[0]

    def test_signed_out_shows_login_and_no_plus(self):
        actions=self.actions(Client())
        self.assertIn('href="/login/"',actions)
        self.assertNotIn('plus.svg',actions)
        self.assertNotIn('/items/new/',actions)

    def test_signed_in_shows_avatar_and_name_and_no_plus(self):
        actions=self.actions(self.member)
        self.assertIn('href="/profile/"',actions)
        self.assertIn('Lin Chan',actions)
        self.assertIn('class="avatar small"',actions)
        self.assertNotIn('href="/login/"',actions)
        self.assertNotIn('plus.svg',actions)

    def test_name_is_escaped(self):
        Profile.objects.filter(user=self.user).update(nickname='<b>x</b>')
        self.assertNotIn('<b>x</b>',self.actions(self.member))


class PublishEntry(Header):
    def test_browse_pages_offer_the_right_thing_to_publish(self):
        for path,href in (('/','/items/new/'),('/?tab=wanted','/wanted/new/')):
            self.assertContains(self.member.get(path),f'class="publish-fab" href="{href}"')
            self.assertContains(Client().get(path),f'class="publish-fab" href="{href}"')

    def test_buddy_page_uses_its_own_button(self):
        page=self.member.get('/buddy/')
        self.assertContains(page,'href="/buddy/new/"')
        self.assertNotContains(page,'publish-fab')

    def test_it_stays_out_of_the_way_elsewhere(self):
        for path in ('/messages/','/notifications/','/people/search/','/profile/','/items/new/','/rules/'):
            self.assertNotContains(self.member.get(path),'publish-fab')

    def test_phone_more_menu_keeps_publishing(self):
        page=self.member.get('/rules/').content.decode()
        self.assertIn('href="/items/new/"',page.split('class="more-nav"')[1])


class MoreIcon(Header):
    def test_three_dots_are_gone_from_every_page_with_more_actions(self):
        for path in ('/','/buddy/','/messages/','/people/search/','/messages/friends/','/rules/'):
            page=self.member.get(path)
            self.assertNotContains(page,'ellipsis.svg')
            self.assertContains(page,'plus-circle')
