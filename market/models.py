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
    first = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_first')
    second = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_second')
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
class Survey(models.Model):
    ANSWERS = [('yes','會 / Yes'),('no','不會 / No'),('unsure','不確定 / Not sure')]
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name='surveys')
    answer = models.CharField(max_length=10,choices=ANSWERS)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order'],name='one_survey_each')]
class Report(models.Model):
    reporter = models.ForeignKey(User,on_delete=models.PROTECT)
    kind = models.CharField(max_length=20,choices=[('item','物品 / Item'),('user','用戶 / User'),('order','訂單 / Order')])
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
