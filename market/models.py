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
    university = models.CharField(max_length=120,blank=True,default='')
    major = models.CharField(max_length=160,blank=True,default='')
    academic_year = models.CharField(max_length=40,blank=True,default='')
    faculty = models.CharField(max_length=160,blank=True,default='')
    # Reserved for a future approved identity integration; never accepted by ProfileForm.
    university_verified_at = models.DateTimeField(null=True,blank=True,editable=False)
    # Never shown on public pages. Only revealed inside a conversation, see social.contact_state().
    contact_whatsapp = models.CharField(max_length=80,blank=True,default='')
    contact_phone = models.CharField(max_length=80,blank=True,default='')
    contact_wechat = models.CharField(max_length=80,blank=True,default='')
    contact_instagram = models.CharField(max_length=80,blank=True,default='')
    request_emails = models.BooleanField('借用申請郵件提醒 / Borrow request emails',default=True,help_text='有人申請借用你的物品時發送郵件提醒 / Email me when someone asks to borrow my item')
    def __str__(self): return self.nickname
class LoginToken(models.Model):
    email = models.EmailField()
    digest = models.CharField(max_length=64,unique=True)
    expires = models.DateTimeField()
    used = models.BooleanField(default=False)
    # Where to return after sign-in, e.g. the item the visitor wanted to buy.
    next_url = models.CharField(max_length=300,blank=True,default='')
    # The same sign-in as a short code, for mail apps whose built-in browser does not keep the session.
    code_digest = models.CharField(max_length=64,blank=True,default='')
    code_attempts = models.PositiveSmallIntegerField(default=0)
class RateBucket(models.Model):
    key = models.CharField(max_length=100,unique=True)
    count = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField()
ITEM_INTENTS = [('rent','租借 / Rent'),('sale','出售 / For sale')]
WANTED_INTENTS = [('borrow','求借 / Want to borrow'),('buy','求購 / Want to buy')]
class Item(models.Model):
    owner = models.ForeignKey(User,on_delete=models.CASCADE)
    intent = models.CharField(max_length=10,choices=ITEM_INTENTS,default='rent')
    title = models.CharField(max_length=100)
    category = models.CharField(max_length=20,choices=CATEGORIES)
    description = models.TextField(max_length=4000)
    condition = models.CharField(max_length=200,blank=True)
    # Daily rent for a rental; the one-off price for a sale.
    daily = models.DecimalField(max_digits=9,decimal_places=2,validators=[MinValueValidator(0)])
    deposit = models.DecimalField(max_digits=9,decimal_places=2,validators=[MinValueValidator(0)])
    available_start = models.DateTimeField()
    available_end = models.DateTimeField()
    max_days = models.PositiveIntegerField(default=14,validators=[MinValueValidator(1),MaxValueValidator(365)])
    location = models.CharField(max_length=160)
    status = models.CharField(max_length=15,choices=[('listed','上架 / Listed'),('paused','暫停 / Paused'),('removed','下架 / Removed'),('sold','已售出 / Sold')],default='listed')
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.title
    @property
    def is_sale(self): return self.intent=='sale'
    @property
    def needs_payment(self): return self.daily>0 or (not self.is_sale and self.deposit>0)
    @property
    def payment_methods(self):
        # Channel names only. The QR images stay behind payments.can_view.
        accepted={code.channel for code in self.owner.payment_codes.all()}
        return [{'channel':channel,'label':label,'icon':PAYMENT_ICONS[channel]} for channel,label in PAYMENT_CHANNELS if channel in accepted]
class ItemPhoto(models.Model):
    item = models.ForeignKey(Item,on_delete=models.CASCADE,related_name='photos')
    image = models.ImageField(upload_to='items/')
    def __str__(self): return f'Photo #{self.pk}'
class Wanted(models.Model):
    owner = models.ForeignKey(User,on_delete=models.CASCADE)
    intent = models.CharField(max_length=10,choices=WANTED_INTENTS,default='borrow')
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
class BuddyFeedback(models.Model):
    # One bounded row per viewed/dismissed post; joining remains in BuddyApplication.
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    post = models.ForeignKey(BuddyPost,on_delete=models.CASCADE)
    dismissed = models.BooleanField(default=False)
    viewed_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','post'],name='one_buddy_feedback_each')]
LOSTFOUND_KINDS = [('found','撿到物品 / Found an item'),('lost','丟失物品 / Lost an item')]
LOSTFOUND_CATEGORIES = [('phones','手機 / Phones'),('electronics','電子配件 / Electronics'),('wallets','錢包與現金 / Wallets and cash'),('cards','證件與卡片 / IDs and cards'),('keys','鑰匙 / Keys'),('bags','袋與背包 / Bags'),('clothing','衣物 / Clothing'),('books','書籍與文具 / Books and stationery'),('jewellery','首飾與手錶 / Jewellery and watches'),('sports','運動用品 / Sports gear'),('bottles','水樽與餐具 / Bottles and lunchware'),('other','其他 / Other')]
class LostFoundPost(models.Model):
    owner = models.ForeignKey(User,on_delete=models.CASCADE,related_name='lostfound_posts')
    kind = models.CharField(max_length=10,choices=LOSTFOUND_KINDS)
    category = models.CharField(max_length=20,choices=LOSTFOUND_CATEGORIES)
    title = models.CharField(max_length=100)
    description = models.TextField(max_length=3000)
    occurred_at = models.DateTimeField()
    location = models.CharField(max_length=160)
    color = models.CharField(max_length=60,blank=True)
    photo = models.ImageField(upload_to='lostfound/',blank=True)
    status = models.CharField(max_length=12,choices=[('open','尋找中 / Open'),('resolved','已找回或交還 / Reunited')],default='open')
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=['kind','status','occurred_at']),models.Index(fields=['category','occurred_at'])]
    def __str__(self): return self.title

class UserBlock(models.Model):
    blocker = models.ForeignKey(User,on_delete=models.CASCADE,related_name='blocks_sent')
    blocked = models.ForeignKey(User,on_delete=models.CASCADE,related_name='blocks_received')
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['blocker','blocked'],name='one_user_block_each'),models.CheckConstraint(condition=~Q(blocker=F('blocked')),name='no_self_user_block')]

class Order(models.Model):
    STATES = [('pending','待確認 / Pending'),('accepted','已接受 / Accepted'),('active','借用中 / On loan'),('return_pending','歸還待確認 / Return pending'),('completed','已完成 / Completed'),('cancelled','已取消 / Cancelled'),('disputed','糾紛中 / Disputed')]
    LOCKED = ['accepted','active','return_pending','disputed']
    KINDS = [('rental','租借 / Rental'),('purchase','購買 / Purchase')]
    kind = models.CharField(max_length=10,choices=KINDS,default='rental')
    item = models.ForeignKey(Item,on_delete=models.PROTECT)
    # The buyer, for a purchase. A purchase's price is held in rent, and deposit is zero.
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
    def total(self): return self.rent+self.deposit
    @property
    def is_purchase(self): return self.kind=='purchase'
    @property
    def status_label(self):
        return '待交接 / Awaiting handover' if self.is_purchase and self.status=='accepted' else self.get_status_display()
    @property
    def overdue(self):
        if not self.is_purchase and self.status in self.LOCKED and self.end < timezone.now():
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
    lostfound = models.ForeignKey(LostFoundPost,on_delete=models.CASCADE,null=True,blank=True,related_name='threads')
    wanted = models.ForeignKey(Wanted,on_delete=models.CASCADE,null=True,blank=True,related_name='threads')
    first = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_first')
    second = models.ForeignKey(User,on_delete=models.CASCADE,related_name='threads_second')
class ChatLine:
    # Shared by private and group messages.
    RECALL_SECONDS = 120
    @property
    def recall_deadline(self): return int(self.created.timestamp())+self.RECALL_SECONDS
    @property
    def recall_open(self): return not self.recalled and timezone.now().timestamp()<self.recall_deadline
class Message(ChatLine,models.Model):
    thread = models.ForeignKey(Thread,on_delete=models.CASCADE,related_name='messages')
    sender = models.ForeignKey(User,on_delete=models.CASCADE)
    text = models.TextField(max_length=2000,blank=True)
    image = models.ImageField(upload_to='chat/',blank=True)
    reply_to = models.ForeignKey('self',on_delete=models.SET_NULL,null=True,blank=True,related_name='+')
    forwarded = models.BooleanField(default=False)
    # A recalled message stays in the database for harassment reports; nobody in the chat can read it.
    recalled = models.BooleanField(default=False)
    recalled_at = models.DateTimeField(null=True,blank=True)
    created = models.DateTimeField(auto_now_add=True)
class ThreadRead(models.Model):
    # How far one person has read one conversation. Nothing unread means this reaches the latest message.
    thread = models.ForeignKey(Thread,on_delete=models.CASCADE,related_name='read_markers')
    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name='+')
    last_read = models.PositiveBigIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['thread','user'],name='one_read_marker_each')]
class BuddyGroup(models.Model):
    post = models.OneToOneField(BuddyPost,on_delete=models.CASCADE,related_name='group_chat')
    created = models.DateTimeField(auto_now_add=True)

class BuddyGroupMember(models.Model):
    group = models.ForeignKey(BuddyGroup,on_delete=models.CASCADE,related_name='memberships')
    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name='buddy_group_memberships')
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True,blank=True)
    # Snapshot under the post lock; repeat join cannot move this boundary backwards.
    history_after = models.PositiveBigIntegerField(default=0)
    last_read = models.PositiveBigIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['group','user'],name='one_buddy_group_member_each')]

class BuddyGroupMessage(ChatLine,models.Model):
    group = models.ForeignKey(BuddyGroup,on_delete=models.CASCADE,related_name='messages')
    sender = models.ForeignKey(User,on_delete=models.PROTECT)
    text = models.TextField(max_length=2000,blank=True)
    image = models.ImageField(upload_to='chat/',blank=True)
    reply_to = models.ForeignKey('self',on_delete=models.SET_NULL,null=True,blank=True,related_name='+')
    forwarded = models.BooleanField(default=False)
    # A recalled message stays in the database for harassment reports; nobody in the chat can read it.
    recalled = models.BooleanField(default=False)
    recalled_at = models.DateTimeField(null=True,blank=True)
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
    KINDS = [('system','系統更新 / System'),('item','物品通知 / Items'),('friend','好友 / Friends'),('request','借用申請 / Borrowing')]
    kind = models.CharField(max_length=10,choices=KINDS,default='system')
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    text = models.CharField(max_length=240)
    url = models.CharField(max_length=200)
    # User-written context shown after the label, e.g. who asked to borrow what.
    detail = models.CharField(max_length=200,blank=True,default='')
    read = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=['user','read'],name='market_note_user_read')]
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
    kind = models.CharField(max_length=20,choices=[('item','物品 / Item'),('user','用戶 / User'),('order','訂單 / Order'),('buddy','Buddy 招募 / Buddy post'),('lostfound','失物招領 / Lost and found'),('thread','對話騷擾 / Conversation harassment'),('group_message','群聊訊息 / Group message')])
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
# A lender's own receiving QR codes. The platform only shows them to the borrower; it never handles the money.
PAYMENT_CHANNELS = [('wechat','微信支付 / WeChat Pay'),('alipay_cn','支付寶（內地） / Alipay (Mainland)'),('alipay_hk','Alipay HK（支付寶香港） / Alipay HK'),('fps','FPS 轉數快 / FPS')]
PAYMENT_ICONS = {'wechat':'wechat.svg','alipay_cn':'alipay-cn.svg','alipay_hk':'alipay-hk.png','fps':'fps.png'}
class PaymentCode(models.Model):
    owner = models.ForeignKey(User,on_delete=models.CASCADE,related_name='payment_codes')
    channel = models.CharField(max_length=20,choices=PAYMENT_CHANNELS)
    image = models.ImageField(upload_to='payment-codes/')
    updated = models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['owner','channel'],name='one_payment_code_per_channel')]

# Machine translations of public posts, keyed by a hash of the source text. Private messages are never stored.
class ContentTranslation(models.Model):
    source_hash = models.CharField(max_length=64)
    lang = models.CharField(max_length=8)
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['source_hash','lang'],name='one_translation_per_language')]
