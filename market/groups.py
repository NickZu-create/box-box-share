"""Buddy-only, opt-in group chat. Pairwise Threads stay unchanged.

All writes serialize on the Buddy post before the group, sharing the lock order
used by acceptance/removal. Joining snapshots the last message ID, so rejoining
cannot reveal messages from an earlier membership period.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone
from .models import BuddyPost, BuddyGroup, BuddyGroupMember, BuddyGroupMessage, BuddyApplication, UserBlock, Notification
from .social import lock_post, is_blocked
from .services import throttle, notify


def eligible(group,user):
    post=group.post
    if not user.is_authenticated or not hasattr(user,'profile') or not user.profile.verified or user.profile.restricted or not user.is_active:
        return False
    if post.owner.profile.restricted or not post.owner.is_active: return False
    return post.owner_id==user.pk or (not is_blocked(user,post.owner) and post.applications.filter(user=user,status='accepted').exists())


def membership(group,user):
    if not eligible(group,user): raise PermissionDenied()
    row=group.memberships.filter(user=user,left_at__isnull=True).first()
    if not row: raise PermissionDenied()
    return row


def active_memberships(user):
    if not user.is_authenticated: return BuddyGroupMember.objects.none()
    rows=BuddyGroupMember.objects.filter(user=user,left_at__isnull=True).select_related('group__post__owner__profile')
    # Apply the same current approval and host-block checks as the chat endpoint.
    return [row for row in rows if eligible(row.group,user)]


def visible_messages(group,user,row=None):
    row=row or membership(group,user)
    blocks=UserBlock.objects.filter(Q(blocker=user)|Q(blocked=user))
    hidden={b.blocked_id if b.blocker_id==user.pk else b.blocker_id for b in blocks}
    return group.messages.filter(pk__gt=row.history_after).exclude(sender_id__in=hidden).filter(sender__profile__restricted=False).select_related('sender__profile')


def locked_group(group_id):
    post_id=BuddyGroup.objects.values_list('post_id',flat=True).get(pk=group_id)
    post=lock_post(post_id)
    group=BuddyGroup.objects.select_for_update().get(pk=group_id)
    group.post=post
    return group


@transaction.atomic
def create(post_id,host):
    post=lock_post(post_id)
    if post.owner_id!=host.pk or host.profile.restricted or not host.profile.verified: raise PermissionDenied()
    group=BuddyGroup.objects.filter(post=post).first()
    if group: return group
    if not post.applications.filter(status='accepted').exists():
        raise ValidationError('至少接受一位成員後才可建群 / Accept at least one member before creating a group')
    group=BuddyGroup.objects.create(post=post)
    BuddyGroupMember.objects.create(group=group,user=host)
    for a in post.applications.filter(status='accepted',user__profile__restricted=False).select_related('user__profile'):
        if not is_blocked(host,a.user): notify(a.user,'Buddy 群聊已建立，可自願加入 / A Buddy group is ready; join if you wish',f'/buddy/{post.pk}/')
    return group


@transaction.atomic
def join(group_id,user):
    group=locked_group(group_id)
    if not eligible(group,user): raise PermissionDenied()
    row=group.memberships.filter(user=user).first()
    if row and row.left_at is None: return row
    boundary=group.messages.aggregate(last=Max('pk'))['last'] or 0
    if row:
        row.joined_at,row.left_at,row.history_after=timezone.now(),None,boundary
        row.save(update_fields=['joined_at','left_at','history_after'])
    else: row=BuddyGroupMember.objects.create(group=group,user=user,history_after=boundary)
    return row


@transaction.atomic
def leave(group_id,user):
    group=locked_group(group_id)
    if group.post.owner_id==user.pk: raise ValidationError('發起人保留群聊管理權 / The host retains group management')
    membership(group,user)
    group.memberships.filter(user=user,left_at__isnull=True).update(left_at=timezone.now())
    Notification.objects.filter(user=user,url=f'/messages/groups/{group.pk}/').update(read=True)


def revoke_for_post(post,user):
    # Called while holding the post lock by Buddy withdrawal/removal.
    BuddyGroupMember.objects.filter(group__post=post,user=user,left_at__isnull=True).update(left_at=timezone.now())


@transaction.atomic
def send(group_id,user,text):
    group=locked_group(group_id)
    membership(group,user)
    text=text.strip()
    if not text or len(text)>2000: raise ValidationError('1–2000 characters / 請輸入 1–2000 字')
    throttle('message:'+str(user.pk),30,60)
    message=BuddyGroupMessage.objects.create(group=group,sender=user,text=text)
    url=f'/messages/groups/{group.pk}/'
    for row in group.memberships.filter(left_at__isnull=True).exclude(user=user).select_related('user__profile'):
        if eligible(group,row.user) and not is_blocked(user,row.user) and not Notification.objects.filter(user=row.user,url=url,read=False).exists():
            notify(row.user,'Buddy 群聊有新訊息 / New Buddy group message',url)
    return message
