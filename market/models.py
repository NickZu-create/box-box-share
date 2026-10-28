import uuid, math
from django.db import models
from django.db.models import Q, F
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

CATEGORIES = [('tech','電子器材 / Tech'),('study','學習用品 / Study'),('outdoor','戶外運動 / Outdoors'),('home','生活用品 / Living'),('creative','創作音樂 / Creative'),('other','其他 / Other')]
class Profile(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    nickname = models.CharField(max_length=40, default='Campus member')
    avatar = models.ImageField(upload_to='avatars/',blank=True)
    verified = models.BooleanField(default=False)
    restricted = models.BooleanField(default=False)
    # Optional, user-written and shown only to signed-in members; used to introduce yourself on Buddy.
    bio = models.CharField(max_length=300,blank=True)
    interests = models.CharField(max_length=200,blank=True)
    skills = models.CharField(max_length=200,blank=True)
    languages = models.CharField(max_length=100,blank=True)
    def __str__(self): return self.nickname
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
# Buddy: recruiting people for an activity (找搭子) or a project team (找隊友). Separate from borrowing.
BUDDY_CATEGORIES = [('buddy','找搭子 / Find a buddy'),('team','找隊友 / Find teammates')]
BUDDY_KINDS = [('study','學習 / Study'),('sports','運動 / Sports'),('meal','吃飯 / Meals'),('event','校園活動 / Campus events'),('course','課程項目 / Course project'),('competition','比賽 / Competition'),('hackathon','Hackathon'),('startup','創業項目 / Startup'),('other','其他 / Other')]
KINDS_BY_CATEGORY = {'buddy':['study','sports','meal','event','other'],'team':['course','competition','hackathon','startup','other']}
class BuddyPost(models.Model):
    STATES = [('open','招募中 / Recruiting'),('full','已滿 / Full'),('closed','已關閉 / Closed'),('ended','已結束 / Ended')]
    owner = models.ForeignKey(User,on_delete=models.CASCADE,related_name='buddy_posts')
    category = models.CharField(max_length=10,choices=BUDDY_CATEGORIES)
    kind = models.CharField(max_length=20,choices=BUDDY_KINDS)
    title = models.CharField(max_length=100)
    description = models.TextField(max_length=2000)
    starts = models.DateTimeField()
    ends = models.DateTimeField(null=True,blank=True)
    location = models.CharField(max_length=160)
    # People to recruit, NOT counting the host. Every page and check uses this one rule.
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1),MaxValueValidator(50)])
    skills = models.CharField(max_length=200,blank=True)
    languages = models.CharField(max_length=100,blank=True)
    status = models.CharField(max_length=10,choices=[('open','開放 / Open'),('closed','已關閉 / Closed')],default='open')
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(ends__isnull=True)|Q(ends__gt=F('starts')),name='buddy_ends_after_start')]
        indexes = [models.Index(fields=['status','starts']),models.Index(fields=['category','kind'])]
    def __str__(self): return self.title
    @property
    def finish(self): return self.ends or self.starts
    def joined(self): return self.applications.filter(status='accepted').count()
    def state(self,joined=None):
        if self.status=='closed': return 'closed'
        if self.finish<=timezone.now(): return 'ended'
        return 'full' if (self.joined() if joined is None else joined)>=self.capacity else 'open'
    def get_state_display(self,joined=None): return dict(self.STATES)[self.state(joined)]
class BuddyApplication(models.Model):
    STATES = [('pending','待審核 / Pending'),('accepted','已加入 / Joined'),('declined','未獲接受 / Declined'),('withdrawn','已撤回 / Withdrawn'),('removed','已被移出 / Removed')]
    post = models.ForeignKey(BuddyPost,on_delete=models.CASCADE,related_name='applications')
    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name='buddy_applications')
    message = models.CharField(max_length=500,blank=True)
    status = models.CharField(max_length=10,choices=STATES,default='pending')
    created = models.DateTimeField(auto_now_add=True)
    decided = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['post','user'],name='one_buddy_application_each')]
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
    # Host <-> accepted applicant. A thread with no item, order or buddy post is a chat between friends.
    buddy = models.ForeignKey(BuddyPost,on_delete=models.CASCADE,null=True,blank=True,related_name='threads')
    first = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_first')
    second = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_second')
class Message(models.Model):
    thread = models.ForeignKey(Thread,on_delete=models.CASCADE,related_name='messages')
    sender = models.ForeignKey(User,on_delete=models.CASCADE)
    text = models.TextField(max_length=2000)
    created = models.DateTimeField(auto_now_add=True)
class Friendship(models.Model):
    # One row per pair of people. Friends only after the recipient accepts; nobody is added automatically.
    sender = models.ForeignKey(User,on_delete=models.CASCADE,related_name='friend_requests_sent')
    recipient = models.ForeignKey(User,on_delete=models.CASCADE,related_name='friend_requests_received')
    status = models.CharField(max_length=10,choices=[('pending','待回覆 / Pending'),('accepted','好友 / Friends'),('declined','未接受 / Not accepted')],default='pending')
    created = models.DateTimeField(auto_now_add=True)
    responded = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['sender','recipient'],name='one_friend_request_each'),models.CheckConstraint(condition=~Q(sender=F('recipient')),name='no_self_friendship')]
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
class Survey(models.Model):
    ANSWERS = [('yes','會 / Yes'),('no','不會 / No'),('unsure','不確定 / Not sure')]
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name='surveys')
    answer = models.CharField(max_length=10,choices=ANSWERS)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order'],name='one_survey_each')]
class Report(models.Model):
    reporter = models.ForeignKey(User,on_delete=models.PROTECT)
    kind = models.CharField(max_length=20,choices=[('item','物品 / Item'),('user','用戶 / User'),('order','訂單 / Order'),('buddy','Buddy 招募 / Buddy post')])
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
