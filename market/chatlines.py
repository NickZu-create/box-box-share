"""One conversation per pair of people, and what can be done to one message in it.

A pair may have several Thread rows underneath (one per order or listing, which is what orders and closing rules
hang on), but people see one conversation, with each borrow request as a message in it. Private and Buddy group
messages behave the same: quote, photo, forward, recall. A recall hides the message from both people but keeps the
row, because a harassment report may need it. "Delete from this device" never reaches the server: see chat.js.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from . import groups, social
from .models import BuddyGroup, BuddyGroupMessage, Message, Order, Profile, Thread
from .services import throttle

KINDS = {'message':Message,'group':BuddyGroupMessage}
MAX_TEXT = 2000
IMAGES_PER_HOUR = 20
TIMELINE = 300


def conversation_threads(me,other_id):
    return Thread.objects.filter(Q(first=me,second_id=other_id)|Q(first_id=other_id,second=me))


def timeline(threads,me):
    """The conversation's messages and borrow requests, oldest first. A request reads as a message."""
    rows=Message.objects.filter(thread__in=threads).select_related('sender__profile','reply_to__sender__profile').order_by('-pk')[:TIMELINE]
    orders=Order.objects.filter(thread__in=threads).select_related('borrower__profile','item')
    # Two rows can share a timestamp, so the id settles which came first.
    return sorted([*rows,*orders],key=lambda row:(row.created,row.pk))


def writable_thread(threads,preferred,user):
    # Where a new message goes: the page's own thread if it is open, otherwise the newest one that is.
    for thread in [preferred,*threads]:
        if social.can_message(thread,user): return thread
    return None


def clean_text(text,has_image):
    text=(text or '').strip()
    if len(text)>MAX_TEXT or (not text and not has_image): raise ValidationError('1–2000 characters / 請輸入 1–2000 字')
    return text


def check_image_quota(user):
    throttle('chat-image:'+str(user.pk),IMAGES_PER_HOUR,3600)


def reply_target(raw,thread,user):
    if not str(raw or '').isdigit(): return None
    other=thread.second_id if thread.first_id==user.pk else thread.first_id
    return Message.objects.filter(pk=int(raw),thread__in=conversation_threads(user,other),recalled=False).first()


def post_private(thread,user,text='',image=None,reply_to=None,forwarded=False):
    other=thread.second if thread.first_id==user.pk else thread.first
    with transaction.atomic():
        # Use the same lock order as blocking, so a block cannot race a new message.
        list(Profile.objects.select_for_update().filter(user__in=[user,other]).order_by('pk'))
        if not social.can_message(thread,user): raise ValidationError('此對話已關閉 / This conversation is closed')
        throttle('message:'+str(user.pk),30,60)
        text=clean_text(text,bool(image))
        return Message.objects.create(thread=thread,sender=user,text=text,image=image or '',reply_to=reply_to,forwarded=forwarded)


def group_reply_target(raw,group,user,row=None):
    if not str(raw or '').isdigit(): return None
    return groups.visible_messages(group,user,row).filter(pk=int(raw),recalled=False).first()


def find_line(kind,pk,user):
    """(message, where its conversation lives), for someone who can see it."""
    if kind=='message':
        message=get_object_or_404(Message.objects.select_related('thread'),pk=pk)
        if user.pk not in (message.thread.first_id,message.thread.second_id): raise PermissionDenied()
        return message,f'/messages/{message.thread_id}/'
    if kind=='group':
        message=get_object_or_404(BuddyGroupMessage.objects.select_related('group__post__owner__profile'),pk=pk)
        row=groups.membership(message.group,user)
        if not groups.visible_messages(message.group,user,row).filter(pk=pk).exists(): raise PermissionDenied()
        return message,f'/messages/groups/{message.group_id}/'
    raise PermissionDenied()


@transaction.atomic
def recall(kind,pk,user):
    find_line(kind,pk,user)
    message=KINDS[kind].objects.select_for_update().get(pk=pk)
    if message.sender_id!=user.pk: raise PermissionDenied()
    if not message.recall_open: raise ValidationError('超過 2 分鐘，不能撤回 / Messages can only be recalled within 2 minutes')
    message.recalled=True
    message.recalled_at=timezone.now()
    message.save(update_fields=['recalled','recalled_at'])
    return message


def forward(kind,pk,user,target):
    """target is 'thread:12' or 'group:3'. Returns where the forwarded copy landed."""
    source,_=find_line(kind,pk,user)
    if source.recalled: raise ValidationError('此訊息已撤回 / This message was recalled')
    place,_,raw=str(target).partition(':')
    if not raw.isdigit(): raise ValidationError('請選擇對話 / Choose a conversation')
    image=source.image.name if source.image else None
    if place=='thread':
        thread=get_object_or_404(Thread,pk=int(raw))
        if user.pk not in (thread.first_id,thread.second_id): raise PermissionDenied()
        post_private(thread,user,source.text,image,forwarded=True)
        return f'/messages/{thread.pk}/'
    if place=='group':
        group=get_object_or_404(BuddyGroup,pk=int(raw))
        groups.send(group.pk,user,source.text,image=image,forwarded=True)
        return f'/messages/groups/{group.pk}/'
    raise ValidationError('請選擇對話 / Choose a conversation')
