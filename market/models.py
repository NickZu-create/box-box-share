import uuid, math, re
from decimal import Decimal
from django.db import models, transaction
from django.db.models import Q, F
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

CATEGORIES = [('tech','電子器材 / Tech'),('study','學習用品 / Study'),('outdoor','戶外運動 / Outdoors'),('home','生活用品 / Living'),('creative','創作音樂 / Creative'),('other','其他 / Other')]
# Commas and 、 separate tags; spaces don't, so "PCB Design" and "board games" stay whole.
def split_tags(text,limit=8): return [t.strip() for t in re.split(r'[,，、;；\n]+',text or '') if t.strip()][:limit]
# Schools are data, not code: login domains, grading scale and how GPA proofs are checked differ per university.
class University(models.Model):
    code = models.SlugField(max_length=30,unique=True)
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=2,default='HK')
    email_domains = models.CharField(max_length=300,help_text='Comma separated student email domains, e.g. my.cityu.edu.hk')
    grading_scale = models.DecimalField(max_digits=5,decimal_places=2,default=Decimal('4.30'))
    verification_policy = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    class Meta: verbose_name_plural='universities'
    def __str__(self): return self.name
    @property
    def domains(self): return [d.strip().lower() for d in self.email_domains.split(',') if d.strip()]
class Profile(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    university = models.ForeignKey(University,on_delete=models.PROTECT,null=True,blank=True)
    nickname = models.CharField(max_length=40, default='Campus member')
    avatar = models.ImageField(upload_to='avatars/',blank=True)
    verified = models.BooleanField(default=False)
    restricted = models.BooleanField(default=False)
    bio = models.CharField(max_length=300,blank=True)
    interests = models.CharField(max_length=120,blank=True)
    # Opt-in only: friend requests need both sides open; dating (18+) enables secret crushes.
    social = models.BooleanField(default=False)
    dating = models.BooleanField(default=False)
    def __str__(self): return self.nickname
    @property
    def tags(self): return split_tags(self.interests)
class LoginToken(models.Model):
    email = models.EmailField()
    digest = models.CharField(max_length=64,unique=True)
    expires = models.DateTimeField()
    used = models.BooleanField(default=False)
class RateBucket(models.Model):
    key = models.CharField(max_length=100,unique=True)
    count = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField()
class Item(models.Model):
    owner = models.ForeignKey(User,on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    category = models.CharField(max_length=20,choices=CATEGORIES)
    description = models.TextField(max_length=4000)
    condition = models.CharField(max_length=200)
    daily = models.DecimalField(max_digits=9,decimal_places=2,validators=[MinValueValidator(0)])
    deposit = models.DecimalField(max_digits=9,decimal_places=2,validators=[MinValueValidator(0)])
    available_start = models.DateTimeField()
    available_end = models.DateTimeField()
    max_days = models.PositiveIntegerField(default=14,validators=[MinValueValidator(1),MaxValueValidator(365)])
    location = models.CharField(max_length=160)
    status = models.CharField(max_length=15,choices=[('listed','上架 / Listed'),('paused','暫停 / Paused'),('removed','下架 / Removed')],default='listed')
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.title
class ItemPhoto(models.Model):
    item = models.ForeignKey(Item,on_delete=models.CASCADE,related_name='photos')
    image = models.ImageField(upload_to='items/')
    def __str__(self): return f'Photo #{self.pk}'
class Wanted(models.Model):
    owner = models.ForeignKey(User,on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    category = models.CharField(max_length=20,choices=CATEGORIES)
    description = models.TextField(max_length=4000)
    start = models.DateTimeField()
    end = models.DateTimeField()
    budget = models.DecimalField(max_digits=9,decimal_places=2,validators=[MinValueValidator(0)])
    location = models.CharField(max_length=160)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.title
class Offer(models.Model):
    wanted = models.ForeignKey(Wanted,on_delete=models.CASCADE,related_name='offers')
    item = models.ForeignKey(Item,on_delete=models.CASCADE)
    text = models.CharField(max_length=1000)
    created = models.DateTimeField(auto_now_add=True)
BUDDY_KINDS = [('study','學習搭子 / Study'),('sports','運動搭子 / Sports'),('outdoor','戶外搭子 / Outdoors'),('food','飯搭子 / Food'),('creative','攝影音樂搭子 / Creative'),('games','遊戲桌遊搭子 / Games'),('other','其他 / Other')]
class Buddy(models.Model):
    owner = models.ForeignKey(User,on_delete=models.CASCADE)
    kind = models.CharField(max_length=20,choices=BUDDY_KINDS)
    title = models.CharField(max_length=100)
    description = models.TextField(max_length=2000)
    when = models.DateTimeField()
    location = models.CharField(max_length=160)
    item = models.ForeignKey(Item,on_delete=models.SET_NULL,null=True,blank=True,related_name='buddies')
    spots = models.PositiveIntegerField(default=1,validators=[MinValueValidator(1),MaxValueValidator(20)])
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.title
class BuddyJoin(models.Model):
    STATES = [('pending','待確認 / Pending'),('accepted','已加入 / Joined'),('declined','未獲接受 / Declined')]
    buddy = models.ForeignKey(Buddy,on_delete=models.CASCADE,related_name='joins')
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    text = models.CharField(max_length=300,blank=True)
    status = models.CharField(max_length=10,choices=STATES,default='pending')
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['buddy','user'],name='one_join_each')]
class Order(models.Model):
    STATES = [('pending','待確認 / Pending'),('accepted','已接受 / Accepted'),('active','借用中 / On loan'),('return_pending','歸還待確認 / Return pending'),('completed','已完成 / Completed'),('cancelled','已取消 / Cancelled'),('disputed','糾紛中 / Disputed')]
    LOCKED = ['accepted','active','return_pending','disputed']
    item = models.ForeignKey(Item,on_delete=models.PROTECT)
    borrower = models.ForeignKey(User,on_delete=models.PROTECT)
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=20,choices=STATES,default='pending')
    snapshot = models.JSONField(default=dict)
    rent = models.DecimalField(max_digits=12,decimal_places=2)
    deposit = models.DecimalField(max_digits=9,decimal_places=2)
    created = models.DateTimeField(auto_now_add=True)
    actual_return = models.DateTimeField(null=True,blank=True)
    extension_end = models.DateTimeField(null=True,blank=True)
    hand_owner = models.BooleanField(default=False)
    hand_borrower = models.BooleanField(default=False)
    return_owner = models.BooleanField(default=False)
    return_borrower = models.BooleanField(default=False)
    rent_owner = models.BooleanField(default=False)
    rent_borrower = models.BooleanField(default=False)
    deposit_owner = models.BooleanField(default=False)
    deposit_borrower = models.BooleanField(default=False)
    refund_owner = models.BooleanField(default=False)
    refund_borrower = models.BooleanField(default=False)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=F('start')),name='positive_order_interval')]
    @property
    def overdue(self):
        if self.status in self.LOCKED and self.end < timezone.now():
            return math.ceil((timezone.now()-self.end).total_seconds()/3600)
        return 0
class Audit(models.Model):
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name='events')
    actor = models.ForeignKey(User,on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    data = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)
class Evidence(models.Model):
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name='evidence')
    actor = models.ForeignKey(User,on_delete=models.PROTECT)
    image = models.ImageField(upload_to='evidence/')
    phase = models.CharField(max_length=20)
    created = models.DateTimeField(auto_now_add=True)
class Thread(models.Model):
    item = models.ForeignKey(Item,on_delete=models.CASCADE,null=True,blank=True)
    order = models.OneToOneField(Order,on_delete=models.CASCADE,null=True,blank=True)
    # No item, order, buddy post or team: a direct chat between friends or a mutual crush.
    buddy = models.ForeignKey(Buddy,on_delete=models.CASCADE,null=True,blank=True)
    # Team chats have no first/second; access follows current team membership.
    team = models.OneToOneField('Team',on_delete=models.CASCADE,null=True,blank=True)
    first = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_first',null=True,blank=True)
    second = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_second',null=True,blank=True)
class Message(models.Model):
    thread = models.ForeignKey(Thread,on_delete=models.CASCADE,related_name='messages')
    sender = models.ForeignKey(User,on_delete=models.CASCADE)
    text = models.TextField(max_length=2000)
    created = models.DateTimeField(auto_now_add=True)
class Notification(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    text = models.CharField(max_length=240)
    url = models.CharField(max_length=200)
    read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
class Review(models.Model):
    order = models.ForeignKey(Order,on_delete=models.PROTECT,related_name='reviews')
    author = models.ForeignKey(User,on_delete=models.PROTECT,related_name='reviews_written')
    recipient = models.ForeignKey(User,on_delete=models.PROTECT,related_name='reviews_received')
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)])
    text = models.CharField(max_length=1000)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order','author'],name='one_review_each')]
class Connection(models.Model):
    # A friend request is visible to its recipient; a crush is never shown to anyone unless it is mutual.
    KINDS = [('friend','好友 / Friend'),('crush','心動 / Crush')]
    sender = models.ForeignKey(User,on_delete=models.CASCADE,related_name='connections_sent')
    recipient = models.ForeignKey(User,on_delete=models.CASCADE,related_name='connections_received')
    kind = models.CharField(max_length=10,choices=KINDS)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['sender','recipient','kind'],name='one_connection_each')]
class Block(models.Model):
    blocker = models.ForeignKey(User,on_delete=models.CASCADE,related_name='blocks_made')
    blocked = models.ForeignKey(User,on_delete=models.CASCADE,related_name='blocks_received')
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['blocker','blocked'],name='one_block_each')]
class Survey(models.Model):
    ANSWERS = [('yes','會 / Yes'),('no','不會 / No'),('unsure','不確定 / Not sure')]
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name='surveys')
    answer = models.CharField(max_length=10,choices=ANSWERS)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order'],name='one_survey_each')]
class Report(models.Model):
    reporter = models.ForeignKey(User,on_delete=models.PROTECT)
    kind = models.CharField(max_length=20,choices=[('item','物品 / Item'),('user','用戶 / User'),('order','訂單 / Order'),('buddy','搭子帖 / Buddy post'),('team','組隊帖 / Team')])
    target = models.PositiveBigIntegerField()
    reason = models.TextField(max_length=2000)
    resolved = models.BooleanField(default=False)
    resolution = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
# Photo bytes for market.dbstorage.DatabaseStorage (MEDIA_STORAGE=db).
class StoredFile(models.Model):
    name = models.CharField(max_length=255,unique=True)
    content = models.BinaryField()
    size = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)

# Team Up. Academic data lives apart from social and dating profiles and is never copied into them.
TEAM_KINDS = [('course','課程小組 / Course group'),('competition','學術競賽 / Competition'),('research','科研創新 / Research'),('startup','創業項目 / Startup'),('hackathon','Hackathon'),('study','自主學習 / Study group')]
YEARS = [('1','一年級 / Year 1'),('2','二年級 / Year 2'),('3','三年級 / Year 3'),('4','四年級 / Year 4'),('5','五年級或以上 / Year 5+'),('pg','研究生 / Postgraduate')]
class AcademicProfile(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE,related_name='academic')
    major = models.CharField(max_length=100,blank=True)
    year = models.CharField(max_length=3,choices=YEARS,blank=True)
    areas = models.CharField(max_length=160,blank=True)
    skills = models.CharField(max_length=200,blank=True)
    courses = models.CharField(max_length=200,blank=True)
    kinds = models.CharField(max_length=120,blank=True)
    projects = models.TextField(max_length=1500,blank=True)
    link = models.URLField(blank=True)
    # Private by default: only you, plus a team leader you explicitly share it with when applying.
    public = models.BooleanField(default=False)
    cross_school = models.BooleanField(default=False)
    updated = models.DateTimeField(auto_now=True)
    @property
    def skill_tags(self): return split_tags(self.skills,12)
    @property
    def area_tags(self): return split_tags(self.areas)
    @property
    def course_tags(self): return split_tags(self.courses,12)
    @property
    def kind_labels(self): return [label for key,label in TEAM_KINDS if key in self.kinds.split(',')]
class GpaVerification(models.Model):
    STATES = [('draft','私密草稿 / Private draft'),('pending','審核中 / Under review'),('verified','平台已審核 / Platform reviewed'),('rejected','未通過 / Not approved')]
    SHOW = [('hidden','隱藏 / Hidden'),('band','只顯示區間 / Range only'),('exact','顯示數值 / Exact value')]
    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name='gpa_records')
    university = models.ForeignKey(University,on_delete=models.PROTECT)
    value = models.DecimalField(max_digits=5,decimal_places=2,validators=[MinValueValidator(0)])
    scale = models.DecimalField(max_digits=5,decimal_places=2,validators=[MinValueValidator(Decimal('0.01')),MaxValueValidator(100)])
    term = models.CharField(max_length=40)
    status = models.CharField(max_length=10,choices=STATES,default='draft')
    visibility = models.CharField(max_length=10,choices=SHOW,default='hidden')
    proof = models.FileField(upload_to='gpa/',blank=True)
    proof_removed = models.DateTimeField(null=True,blank=True)
    submitted = models.DateTimeField(null=True,blank=True)
    reviewed = models.DateTimeField(null=True,blank=True)
    reviewer = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='gpa_reviews')
    note = models.CharField(max_length=300,blank=True)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        permissions = [('review_gpa','Can review GPA proofs / 可審核 GPA 證明')]
        constraints = [models.CheckConstraint(condition=Q(value__gte=0,value__lte=F('scale'),scale__gt=0),name='gpa_within_scale'),
                       models.UniqueConstraint(fields=['user'],condition=Q(status='pending'),name='one_pending_gpa')]
    def __str__(self): return f'GPA #{self.pk}'
    @property
    def shown(self): return self.status=='verified' and self.visibility!='hidden'
    @property
    def band(self):
        step=Decimal('0.25') if self.scale<=5 else Decimal('0.5') if self.scale<=10 else Decimal('5')
        low=(self.value//step)*step
        return f'{low:.2f}–{min(low+step-Decimal("0.01"),self.scale):.2f}'
@receiver(post_delete,sender=GpaVerification)
def delete_gpa_proof(sender,instance,**kwargs):
    # Covers record deletion and account deletion (CASCADE): the proof never outlives its record.
    if instance.proof:
        storage,name=instance.proof.storage,instance.proof.name
        transaction.on_commit(lambda: storage.delete(name))
class GpaAudit(models.Model):
    # Survives record deletion (record becomes NULL); stores status changes only, never the GPA value.
    record = models.ForeignKey(GpaVerification,on_delete=models.SET_NULL,null=True,related_name='audits')
    actor = models.ForeignKey(User,on_delete=models.SET_NULL,null=True,related_name='+')
    action = models.CharField(max_length=40)
    data = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)
class Team(models.Model):
    STATES = [('recruiting','招募中 / Recruiting'),('closed','暫停招募 / Not recruiting'),('disbanded','已解散 / Disbanded')]
    MODES = [('offline','線下 / In person'),('online','線上 / Online'),('hybrid','線上線下 / Hybrid')]
    leader = models.ForeignKey(User,on_delete=models.CASCADE,related_name='teams_led')
    university = models.ForeignKey(University,on_delete=models.PROTECT)
    kind = models.CharField(max_length=20,choices=TEAM_KINDS)
    course_code = models.CharField(max_length=20,blank=True)
    title = models.CharField(max_length=100)
    description = models.TextField(max_length=3000)
    size = models.PositiveIntegerField(default=3,validators=[MinValueValidator(1),MaxValueValidator(20)])
    skills = models.CharField(max_length=200,blank=True)
    duration = models.CharField(max_length=60,blank=True)
    deadline = models.DateField(null=True,blank=True)
    mode = models.CharField(max_length=10,choices=MODES,default='offline')
    cross_school = models.BooleanField(default=False)
    status = models.CharField(max_length=12,choices=STATES,default='recruiting')
    announcement = models.TextField(max_length=2000,blank=True)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=['status','university']),models.Index(fields=['course_code'])]
    def __str__(self): return self.title
    @property
    def skill_tags(self): return split_tags(self.skills,12)
class TeamApplication(models.Model):
    STATES = [('pending','待審核 / Pending'),('accepted','已加入 / Accepted'),('rejected','未獲接受 / Not accepted')]
    team = models.ForeignKey(Team,on_delete=models.CASCADE,related_name='applications')
    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name='team_applications')
    message = models.CharField(max_length=1000,blank=True)
    # Explicit, per-application consent to show this leader your academic profile.
    share_profile = models.BooleanField(default=False)
    status = models.CharField(max_length=10,choices=STATES,default='pending')
    created = models.DateTimeField(auto_now_add=True)
    decided = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['team','user'],name='one_application_each')]
class TeamMember(models.Model):
    ROLES = [('leader','隊長 / Leader'),('member','成員 / Member')]
    team = models.ForeignKey(Team,on_delete=models.CASCADE,related_name='members')
    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name='team_memberships')
    role = models.CharField(max_length=10,choices=ROLES,default='member')
    joined = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['team','user'],name='one_membership_each')]
