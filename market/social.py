from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import *
from .services import throttle, notify

# Buddy recruiting and friends. Every state change locks the post (or friendship) row first and only
# notifies on a real transition, so a refresh or a double click never repeats a notification.

def lock_post(post_id): return BuddyPost.objects.select_for_update().select_related('owner__profile').get(pk=post_id)

@transaction.atomic
def apply(post_id,user,message):
    post=lock_post(post_id)
    if post.owner_id==user.pk: raise ValidationError('不能申請自己的招募 / You cannot apply to your own post')
    if post.owner.profile.restricted: raise ValidationError('招募暫時無法申請 / This post is unavailable')
    state=post.state()
    if state!='open': raise ValidationError({'full':'名額已滿 / This post is full','closed':'招募已關閉 / This post is closed','ended':'活動已結束 / This activity has ended'}[state])
    if len(message)>500: raise ValidationError('留言上限 500 字 / Up to 500 characters')
    existing=BuddyApplication.objects.filter(post=post,user=user).first()
    if existing and existing.status in ('pending','accepted'): raise ValidationError('你已申請這個招募 / You have already applied')
    if existing and existing.status in ('declined','removed'): raise ValidationError('發起人已處理你的申請，不能再次申請 / The host has already answered; you cannot apply again')
    throttle('buddy-apply:'+str(user.pk),20,86400)
    if existing:
        existing.status,existing.message,existing.decided='pending',message,None; existing.save()
    else: existing=BuddyApplication.objects.create(post=post,user=user,message=message)
    notify(post.owner,'有人申請加入你的 Buddy 招募 / New Buddy application',f'/buddy/{post.pk}/')
    return existing

@transaction.atomic
def withdraw(post_id,user):
    post=lock_post(post_id)
    a=BuddyApplication.objects.select_for_update().filter(post=post,user=user,status__in=['pending','accepted']).first()
    if not a: raise ValidationError('沒有可撤回的申請 / Nothing to withdraw')
    was_member=a.status=='accepted'
    a.status,a.decided='withdrawn',timezone.now(); a.save()
    if was_member: notify(post.owner,'有成員退出你的 Buddy 招募 / A member left your Buddy post',f'/buddy/{post.pk}/')

@transaction.atomic
def decide(post_id,host,application_id,accept):
    # The post row lock serialises concurrent accepts, so the capacity check cannot be raced past.
    post=lock_post(post_id)
    if post.owner_id!=host.pk: raise PermissionDenied()
    a=BuddyApplication.objects.select_for_update().filter(pk=application_id,post=post).first()
    if not a: raise ValidationError('找不到申請 / Application not found')
    if a.status!='pending': raise ValidationError('這份申請已處理 / This application was already answered')
    if accept:
        state=post.state()
        if state!='open': raise ValidationError({'full':'名額已滿 / This post is full','closed':'招募已關閉 / This post is closed','ended':'活動已結束 / This activity has ended'}[state])
        a.status='accepted'
        Thread.objects.get_or_create(buddy=post,first=a.user,second=post.owner,item=None,order=None)
        notify(a.user,'你的 Buddy 申請已獲接受 / Your Buddy application was accepted',f'/buddy/{post.pk}/')
    else:
        a.status='declined'
        notify(a.user,'你的 Buddy 申請未獲接受 / Your Buddy application was declined',f'/buddy/{post.pk}/')
    a.decided=timezone.now(); a.save()
    return a

@transaction.atomic
def remove_member(post_id,host,application_id):
    post=lock_post(post_id)
    if post.owner_id!=host.pk: raise PermissionDenied()
    a=BuddyApplication.objects.select_for_update().filter(pk=application_id,post=post,status='accepted').first()
    if not a: raise ValidationError('找不到成員 / Member not found')
    a.status,a.decided='removed',timezone.now(); a.save()
    notify(a.user,'你已被移出一個 Buddy 招募 / You were removed from a Buddy post',f'/buddy/{post.pk}/')

@transaction.atomic
def set_open(post_id,host,open_):
    post=lock_post(post_id)
    if post.owner_id!=host.pk: raise PermissionDenied()
    if open_:
        if post.status=='open': return post
        if post.finish<=timezone.now(): raise ValidationError('活動已結束，不能重新開放 / This activity has ended and cannot reopen')
        post.status='open'
    else:
        if post.status=='closed': return post
        post.status='closed'
        # Closing turns down whoever is still waiting; members who already joined stay.
        for a in BuddyApplication.objects.select_for_update().filter(post=post,status='pending').select_related('user'):
            a.status,a.decided='declined',timezone.now(); a.save()
            notify(a.user,'你申請的 Buddy 招募已關閉 / A Buddy post you applied to was closed',f'/buddy/{post.pk}/')
    post.save(update_fields=['status','updated'])
    return post

def member_of(post,user): return post.applications.filter(user_id=user.pk,status='accepted').exists()

# Friends
def friendship(a,b): return Friendship.objects.filter(Q(sender=a,recipient=b)|Q(sender=b,recipient=a)).first()
def are_friends(a,b): return Friendship.objects.filter(Q(sender=a,recipient=b)|Q(sender=b,recipient=a),status='accepted').exists()

@transaction.atomic
def request_friend(sender,recipient):
    if sender.pk==recipient.pk: raise ValidationError('不能加自己為好友 / You cannot add yourself')
    if recipient.profile.restricted or not recipient.profile.verified: raise ValidationError('無法加為好友 / This member cannot be added')
    # Lock both profiles in a fixed order so crossing requests resolve to a single friendship.
    list(Profile.objects.select_for_update().filter(user__in=[sender,recipient]).order_by('pk'))
    f=friendship(sender,recipient)
    if f and f.status=='accepted': raise ValidationError('你們已是好友 / You are already friends')
    if f and f.sender_id==recipient.pk and f.status=='pending': return respond(sender,f.pk,True)
    if f and f.sender_id==sender.pk: raise ValidationError('已送出好友申請 / Request already sent' if f.status=='pending' else '對方暫未接受你的申請 / They have not accepted your request')
    throttle('friend:'+str(sender.pk),20,86400)
    if f: f.delete()  # they turned you down earlier and you are now the one asking: start fresh
    f=Friendship.objects.create(sender=sender,recipient=recipient)
    notify(recipient,'收到好友申請 / New friend request','/messages/#friends')
    return f

@transaction.atomic
def respond(user,friendship_id,accept):
    f=Friendship.objects.select_for_update().filter(pk=friendship_id,recipient=user,status='pending').first()
    if not f: raise ValidationError('找不到好友申請 / Friend request not found')
    f.status,f.responded='accepted' if accept else 'declined',timezone.now(); f.save()
    if accept: notify(f.sender,'好友申請已獲接受 / Friend request accepted',f'/people/{user.pk}/')
    return f

def cancel_request(user,friendship_id):
    if not Friendship.objects.filter(pk=friendship_id,sender=user,status='pending').delete()[0]: raise ValidationError('找不到好友申請 / Friend request not found')

def remove_friend(user,other):
    if not Friendship.objects.filter(Q(sender=user,recipient=other)|Q(sender=other,recipient=user),status='accepted').delete()[0]: raise ValidationError('你們不是好友 / You are not friends')

def direct_thread(a,b):
    first,second=sorted((a,b),key=lambda u:u.pk)
    return Thread.objects.get_or_create(first=first,second=second,item=None,order=None,buddy=None)[0]

def can_message(thread,user):
    # Read access is in_thread; this decides whether the conversation still accepts new messages.
    other=thread.second if thread.first_id==user.pk else thread.first
    if thread.order_id or thread.item_id: return True
    if thread.buddy_id: return thread.buddy.applications.filter(user_id=thread.first_id,status='accepted').exists()
    return are_friends(user,other)
