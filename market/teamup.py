import secrets
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from .models import *
from .services import throttle, notify, notify_once, blocked, clean_image, school_for

# Team Up and GPA review. Nothing here reads or writes dating data, and team membership never counts as
# "having met" for friends or crushes (services.met_ids), so a team can't be used to reach someone romantically.

def school(user):
    p=user.profile
    if not p.university_id:
        p.university=school_for(user.email)
        if p.university: p.save(update_fields=['university'])
    return p.university

def same_school_or_open(user,university,cross_school):
    return cross_school or school(user)==university

def can_view_academic(viewer,owner):
    if not viewer.is_authenticated: return False
    if viewer.pk==owner.pk: return True
    p=getattr(viewer,'profile',None)
    if not p or not p.verified or p.restricted or blocked(viewer,owner): return False
    academic=AcademicProfile.objects.filter(user=owner).first()
    if academic and academic.public: return True
    # A leader may see the profile of someone who applied to their team and ticked "share my academic profile".
    return TeamApplication.objects.filter(user=owner,team__leader=viewer,share_profile=True,status__in=['pending','accepted']).exists()

def shown_gpa(user): return GpaVerification.objects.filter(user=user,status='verified').exclude(visibility='hidden').order_by('-reviewed','-pk').first()

@transaction.atomic
def start_team(team):
    TeamMember.objects.create(team=team,user=team.leader,role='leader')
    Thread.objects.create(team=team)

def lock(team_id): return Team.objects.select_for_update().select_related('leader__profile').get(pk=team_id)

@transaction.atomic
def apply_team(team_id,user,message,share_profile):
    t=lock(team_id)
    if t.status!='recruiting': raise ValidationError('Not recruiting / 小組未在招募')
    if t.members.filter(user=user).exists(): raise ValidationError('Already in this team / 已是成員')
    if not same_school_or_open(user,t.university,t.cross_school): raise ValidationError('This team only takes students from its own school / 此小組只招募本校學生')
    if t.leader.profile.restricted or blocked(user,t.leader): raise ValidationError('Unavailable / 無法申請')
    if len(message)>1000: raise ValidationError('Up to 1000 characters / 留言上限 1000 字')
    if t.applications.filter(user=user).exists(): raise ValidationError('Already applied / 已申請')
    throttle('team-apply:'+str(user.pk),20,86400)
    a=TeamApplication.objects.create(team=t,user=user,message=message,share_profile=share_profile)
    notify(t.leader,'收到組隊申請 / New team application',f'/teams/{t.pk}/')
    return a

@transaction.atomic
def decide(application_id,leader,accept):
    team_id=TeamApplication.objects.values_list('team_id',flat=True).get(pk=application_id)
    t=lock(team_id)
    a=TeamApplication.objects.select_for_update().get(pk=application_id)
    if t.leader_id!=leader.pk: raise PermissionDenied()
    if a.status!='pending' or t.status=='disbanded': raise ValidationError('Already decided / 已處理')
    if accept:
        if t.members.filter(role='member').count()>=t.size: raise ValidationError('Team is full / 名額已滿')
        TeamMember.objects.create(team=t,user=a.user)
    a.status='accepted' if accept else 'rejected'; a.decided=timezone.now(); a.save()
    notify(a.user,'組隊申請已獲接受 / You joined the team' if accept else '組隊申請未獲接受 / Application not accepted',f'/teams/{t.pk}/')
    return a

@transaction.atomic
def withdraw(team_id,user):
    lock(team_id)
    if not TeamApplication.objects.filter(team_id=team_id,user=user,status='pending').delete()[0]: raise ValidationError('Nothing to withdraw / 沒有待審申請')

@transaction.atomic
def leave(team_id,user):
    t=lock(team_id)
    if t.leader_id==user.pk: raise ValidationError('Leaders disband the team instead / 隊長請改為解散小組')
    if not t.members.filter(user=user).delete()[0]: raise ValidationError('Not a member / 不是成員')
    # Clearing the application lets the student apply again later.
    t.applications.filter(user=user).delete()
    notify(t.leader,'有成員離開小組 / A member left',f'/teams/{t.pk}/')

@transaction.atomic
def remove_member(team_id,leader,member_id):
    t=lock(team_id)
    if t.leader_id!=leader.pk: raise PermissionDenied()
    if member_id==leader.pk or not t.members.filter(user_id=member_id).delete()[0]: raise ValidationError('Invalid member / 成員無效')
    t.applications.filter(user_id=member_id).delete()
    notify(User.objects.get(pk=member_id),'你已被移出小組 / You were removed from a team',f'/teams/{t.pk}/')

@transaction.atomic
def manage(team_id,leader,action,text=''):
    t=lock(team_id)
    if t.leader_id!=leader.pk: raise PermissionDenied()
    if t.status=='disbanded': raise ValidationError('Team disbanded / 小組已解散')
    others=[m.user for m in t.members.exclude(user=leader).select_related('user')]
    if action=='announce':
        if len(text)>2000: raise ValidationError('Up to 2000 characters / 公告上限 2000 字')
        t.announcement=text
        for u in others: notify_once(u,'小組公告已更新 / Team announcement updated',f'/teams/{t.pk}/')
    elif action in ('recruiting','closed'): t.status=action
    elif action=='disband':
        t.status='disbanded'
        t.applications.filter(status='pending').update(status='rejected',decided=timezone.now())
        for u in others: notify(u,'小組已解散 / Team disbanded',f'/teams/{t.pk}/')
    else: raise ValidationError('Unknown action / 操作無效')
    t.save()
    return t

def invite(team_id,leader,target):
    t=Team.objects.get(pk=team_id,leader=leader)
    academic=AcademicProfile.objects.filter(user=target,public=True).first()
    # Only people who made their academic profile public can be invited; an invite is a notification, never a chat.
    if t.status!='recruiting' or not academic or target.pk==leader.pk or target.profile.restricted or blocked(leader,target): raise ValidationError('Cannot invite / 無法邀請')
    if not (t.cross_school and academic.cross_school) and school(target)!=t.university: raise ValidationError('Different school / 不同學校')
    if t.members.filter(user=target).exists() or t.applications.filter(user=target).exists(): raise ValidationError('Already applied or joined / 對方已申請或已加入')
    throttle('team-invite:'+str(leader.pk),20,86400)
    notify(target,'有小組邀請你申請加入 / A team invited you to apply',f'/teams/{t.pk}/')

# GPA review. Proofs are private files served only through the authorised /media/gpa/ view.
PDF_LIMIT=10*1024*1024
PDF_ACTIVE=(b'/JavaScript',b'/JS',b'/Launch',b'/EmbeddedFile',b'/RichMedia',b'/XFA')
def clean_proof(upload):
    if not upload: raise ValidationError('Choose a file / 請選擇檔案')
    if upload.content_type=='application/pdf' or upload.name.lower().endswith('.pdf'):
        if upload.size>PDF_LIMIT: raise ValidationError('PDF up to 10 MB / PDF 上限 10 MB')
        data=b''.join(upload.chunks())
        if not data.startswith(b'%PDF-'): raise ValidationError('Invalid PDF / PDF 無效')
        # Reviewers open these files, so refuse PDFs that carry scripts, launch actions or embedded files.
        if any(marker in data for marker in PDF_ACTIVE): raise ValidationError('PDF contains active content; export or screenshot it instead / PDF 含互動內容，請另存或截圖')
        return ContentFile(data,name=secrets.token_hex(16)+'.pdf')
    return clean_image(upload)

def audit(record,actor,action,**data): GpaAudit.objects.create(record=record,actor=actor,action=action,data=data)

def drop_proof(record):
    if record.proof:
        storage,name=record.proof.storage,record.proof.name
        transaction.on_commit(lambda: storage.delete(name))
        record.proof=''

@transaction.atomic
def submit_gpa(record_id,user,proof):
    r=GpaVerification.objects.select_for_update().get(pk=record_id,user=user)
    if r.status not in ('draft','rejected'): raise ValidationError('Already submitted / 已提交')
    if GpaVerification.objects.filter(user=user,status='pending').exists(): raise ValidationError('One review at a time / 每次只可有一份審核中的申請')
    throttle('gpa:'+str(user.pk),5,86400)
    drop_proof(r)
    r.proof=proof; r.status='pending'; r.submitted=timezone.now(); r.note=''; r.reviewed=None; r.reviewer=None; r.proof_removed=None; r.save()
    audit(r,user,'submitted')
    return r

@transaction.atomic
def withdraw_gpa(record_id,user):
    r=GpaVerification.objects.select_for_update().get(pk=record_id,user=user)
    if r.status!='pending': raise ValidationError('Not under review / 未在審核中')
    drop_proof(r); r.status='draft'; r.submitted=None; r.save()
    audit(r,user,'withdrawn')

@transaction.atomic
def review_gpa(record_id,reviewer,approve,note=''):
    if not reviewer.is_staff or not reviewer.has_perm('market.review_gpa'): raise PermissionDenied()
    r=GpaVerification.objects.select_for_update().get(pk=record_id)
    if r.user_id==reviewer.pk: raise PermissionDenied('No self-review / 不可審核自己的申請')
    if r.status!='pending': raise ValidationError('Not under review / 未在審核中')
    r.status='verified' if approve else 'rejected'; r.reviewed=timezone.now(); r.reviewer=reviewer; r.note=note[:300]; r.save()
    audit(r,reviewer,r.status)
    notify(r.user,'GPA 已通過平台審核 / GPA reviewed' if approve else 'GPA 審核未通過 / GPA not approved','/profile/gpa/')
    return r

def purge_proofs(now=None):
    # Retention: proofs are deleted GPA_PROOF_RETENTION_DAYS after the decision; the status and audit trail remain.
    cutoff=(now or timezone.now())-timedelta(days=settings.GPA_PROOF_RETENTION_DAYS)
    count=0
    for r in GpaVerification.objects.filter(status__in=['verified','rejected'],reviewed__lte=cutoff).exclude(proof=''):
        with transaction.atomic():
            drop_proof(r); r.proof_removed=timezone.now(); r.save(update_fields=['proof','proof_removed'])
            audit(r,None,'proof_removed')
        count+=1
    return count
