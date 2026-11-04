from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import AnonymousUser
from django.db.models import Count, Q
from django.test import TestCase, TransactionTestCase, Client
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from .models import Profile, BuddyPost, BuddyApplication, BuddyFeedback, UserBlock
from .forms import ProfileForm
from .tests import make_user, make_item
from .recommendations import rank_posts
from .university import AcademicContext, Course, ClassMeeting, academic_context


class StudentRecommendations(TestCase):
    def setUp(self):
        self.user=make_user('student');self.owner=make_user('host')
        self.client.force_login(self.user)
        self.now=timezone.now()

    def post(self,title='Study',kind='study',**kwargs):
        return BuddyPost.objects.create(owner=self.owner,category='buddy',kind=kind,title=title,
            description=kwargs.pop('description','Activity'),starts=kwargs.pop('starts',self.now+timedelta(days=2)),
            ends=kwargs.pop('ends',self.now+timedelta(days=2,hours=1)),location='Library',capacity=5,**kwargs)

    def rows(self):
        return BuddyPost.objects.select_related('owner__profile').annotate(joined_count=Count('applications',filter=Q(applications__status='accepted')))

    def test_optional_fields_and_no_identity_escalation(self):
        data={'nickname':'Student','university':'CityUHK','major':'EE','academic_year':'Year 2','faculty':'Engineering','university_verified_at':self.now.isoformat(),'verified':'True'}
        self.assertEqual(self.client.post('/profile/',data).status_code,302)
        self.user.profile.refresh_from_db();self.assertEqual(self.user.profile.major,'EE')
        self.assertIsNone(self.user.profile.university_verified_at)
        self.assertNotIn('verified',ProfileForm().fields)
        self.assertNotIn('university_verified_at',ProfileForm().fields)
        self.assertEqual(self.client.post('/profile/',{'nickname':'Student','university':'','major':'','academic_year':'','faculty':''}).status_code,302)
        self.user.profile.refresh_from_db();self.assertEqual(self.user.profile.major,'')

    def test_student_fields_private_from_guests_and_escaped(self):
        p=self.user.profile;p.major='<script>EEE</script>';p.save()
        self.assertNotContains(Client().get(f'/people/{self.user.pk}/'),'EEE')
        page=self.client.get(f'/people/{self.user.pk}/')
        self.assertContains(page,'&lt;script&gt;EEE&lt;/script&gt;')
        self.assertNotContains(page,'Account Verified')

    def test_course_code_and_name_search(self):
        post=self.post('MA 1201 Calculus revision');self.post('Football','sports')
        self.assertContains(self.client.get('/buddy/',{'q':'MA1201'}),post.title)
        self.assertContains(self.client.get('/buddy/',{'q':'Calculus'}),post.title)
        self.assertNotContains(self.client.get('/buddy/',{'q':'MA1201'}),'Football')
        self.assertEqual(academic_context(self.user.pk),AcademicContext())

    def test_major_people_search_and_blocks(self):
        p=self.owner.profile;p.major='Electrical Engineering';p.save();self.post('A team')
        page=self.client.get('/buddy/',{'major':'Electrical'})
        self.assertContains(page,f'/people/{self.owner.pk}/')
        UserBlock.objects.create(blocker=self.user,blocked=self.owner)
        self.assertNotContains(self.client.get('/buddy/',{'major':'Electrical'}),f'/people/{self.owner.pk}/')
        self.assertNotContains(Client().get('/buddy/',{'q':'Electrical'}),'A team')

    def test_major_rank_and_missing_data_fallback(self):
        other=make_user('other');p=self.owner.profile;p.major='EE';p.save()
        p=self.user.profile;p.major='EE';p.save()
        a=self.post('Relevant');b=self.post('Unrelated');b.owner=other;b.save()
        self.assertEqual(rank_posts(self.rows(),self.user)[0].pk,a.pk)
        self.assertEqual(len(rank_posts(self.rows(),AnonymousUser())),2)
        self.assertEqual(len(rank_posts(self.rows(),make_user('blank'))),2)

    def test_participation_stronger_than_search(self):
        study=self.post('EE1001');sport=self.post('Badminton','sports')
        prior=self.post('Past sport','sports',starts=self.now-timedelta(days=2),ends=self.now-timedelta(days=1))
        BuddyApplication.objects.create(user=self.user,post=prior,status='accepted')
        rows=self.rows().exclude(pk=prior.pk)
        self.assertEqual(rank_posts(rows,self.user,['EE1001'])[0].pk,sport.pk)
        BuddyApplication.objects.filter(post=prior).update(status='pending')
        self.assertEqual(rank_posts(rows,self.user,['EE1001'])[0].pk,study.pk)

    def test_views_dismissal_restore_and_post_only(self):
        a=self.post('First');b=self.post('Second')
        self.client.get(f'/buddy/{a.pk}/');self.client.get(f'/buddy/{a.pk}/')
        self.assertEqual(BuddyFeedback.objects.filter(user=self.user,post=a).count(),1)
        self.assertEqual(rank_posts(self.rows(),self.user)[0].pk,b.pk)
        self.assertEqual(self.client.get(f'/buddy/{a.pk}/feedback/').status_code,405)
        self.client.post(f'/buddy/{a.pk}/feedback/',{'action':'dismiss','next':'https://evil.invalid/'})
        self.assertTrue(BuddyFeedback.objects.get(user=self.user,post=a).dismissed)
        self.client.post(f'/buddy/{a.pk}/feedback/',{'action':'restore'})
        self.assertFalse(BuddyFeedback.objects.get(user=self.user,post=a).dismissed)

    def test_study_interest_also_promotes_course_teams(self):
        past=self.post('Joined study');BuddyApplication.objects.create(user=self.user,post=past,status='accepted')
        course=self.post('Course team','course');self.post('Badminton','sports')
        self.assertEqual(rank_posts(self.rows().exclude(pk=past.pk),self.user)[0].pk,course.pk)

    def test_official_course_and_timetable_require_separate_authorization(self):
        a=self.post('EE1001');b=self.post('Other')
        meeting=ClassMeeting(a.starts,a.ends,'EE1001')
        unauth=AcademicContext(courses=(Course('EE1001','Electronics','T1'),),meetings=(meeting,))
        self.assertEqual([p.pk for p in rank_posts(self.rows(),self.user,academic=unauth)],
                         [p.pk for p in rank_posts(self.rows(),self.user)])
        course=AcademicContext(courses=unauth.courses,courses_authorized=True)
        self.assertEqual(rank_posts(self.rows(),self.user,academic=course)[0].pk,a.pk)
        b.starts+=timedelta(days=1);b.ends+=timedelta(days=1);b.save()
        table=AcademicContext(meetings=(meeting,),timetable_authorized=True)
        self.assertEqual(rank_posts(self.rows(),self.user,academic=table)[0].pk,b.pk)
        # Touching boundaries do not conflict.
        table=AcademicContext(meetings=(ClassMeeting(a.ends,a.ends+timedelta(hours=1)),),timetable_authorized=True)
        self.assertEqual(len(rank_posts(self.rows(),self.user,academic=table)),2)

    def test_search_is_interest_only_and_bounded(self):
        for i in range(15):self.client.get('/buddy/',{'q':f'EE{i}'})
        self.assertEqual(len(self.client.session['buddy_searches']),10)
        self.user.profile.refresh_from_db();self.assertEqual(self.user.profile.major,'')
        self.assertIsNone(self.user.profile.university_verified_at)

    def test_exploration_and_full_posts(self):
        past=self.post('Joined','sports');BuddyApplication.objects.create(user=self.user,post=past,status='accepted')
        for i in range(6):self.post(f'Sport {i}','sports')
        novel=self.post('New interest','event')
        rows=rank_posts(self.rows().exclude(pk=past.pk),self.user)
        self.assertEqual(rows[4].pk,novel.pk)
        full=self.post('Full');full.capacity=1;full.save();BuddyApplication.objects.create(user=self.user,post=full,status='accepted')
        self.assertNotEqual(rank_posts(self.rows(),self.user)[0].pk,full.pk)

    def test_languages_and_existing_surfaces(self):
        post=self.post('EE1001')
        for lang in ('en','zh','hans'):
            self.client.post('/language/',{'lang':lang})
            for path in ('/profile/','/buddy/',f'/buddy/{post.pk}/','/messages/'):
                self.assertEqual(self.client.get(path).status_code,200)


class StudentMigration(TransactionTestCase):
    def test_old_profile_and_item_preserved(self):
        executor=MigrationExecutor(connection);old=[('market','0006_lostfound_blocks')];latest=executor.loader.graph.leaf_nodes()
        executor.migrate(old)
        try:
            apps=executor.loader.project_state(old).apps
            User=apps.get_model('auth','User');P=apps.get_model('market','Profile')
            user=User.objects.create(username='migration-student')
            profile=P.objects.create(user_id=user.pk,nickname='Kept',bio='Existing introduction',verified=True)
            executor=MigrationExecutor(connection);executor.migrate(latest)
            p=Profile.objects.get(pk=profile.pk)
            self.assertEqual(p.nickname,'Kept');self.assertEqual(p.bio,'Existing introduction')
            self.assertTrue(p.verified);self.assertEqual(p.major,'');self.assertIsNone(p.university_verified_at)
        finally:
            MigrationExecutor(connection).migrate(latest)
