import re
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Count
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import *
from .forms import *
from .services import member, blocked, throttle, valid_email
from . import teamup

def error(request,exc): messages.error(request,'; '.join(exc.messages))

def hub(request):
    me=request.user
    mine=teamup.school(me) if me.is_authenticated and hasattr(me,'profile') else None
    teams=Team.objects.filter(status='recruiting')
    if mine: teams=teams.filter(Q(university=mine)|Q(cross_school=True))
    return render(request,'market/connect.html',{'team_count':teams.count(),'buddy_count':Buddy.objects.filter(active=True,when__gt=timezone.now()).count(),'my_teams':TeamMember.objects.filter(user=me).exclude(team__status='disbanded').select_related('team') if me.is_authenticated else []})

def teams(request):
    me=request.user
    mine=teamup.school(me) if me.is_authenticated and hasattr(me,'profile') else None
    scope=request.GET.get('scope',''); q=request.GET.get('q','').strip(); kind=request.GET.get('kind',''); course=re.sub(r'\s+','',request.GET.get('course','')).upper(); skill=request.GET.get('skill','').strip()
    rows=Team.objects.filter(status='recruiting',leader__profile__restricted=False)
    # Own school first; other schools only when the student asks for it and the team accepts cross-school members.
    if mine: rows=rows.filter(Q(university=mine)|Q(cross_school=True)) if scope=='all' else rows.filter(university=mine)
    if me.is_authenticated: rows=rows.exclude(leader__blocks_made__blocked=me).exclude(leader__blocks_received__blocker=me)
    if q: rows=rows.filter(Q(title__icontains=q)|Q(description__icontains=q))
    if kind: rows=rows.filter(kind=kind)
    if course: rows=rows.filter(course_code__icontains=course)
    if skill: rows=rows.filter(skills__icontains=skill)
    rows=rows.annotate(joined=Count('members',filter=Q(members__role='member'))).select_related('leader__profile','university').order_by('-created','-pk')[:100]
    return render(request,'market/teams.html',{'rows':rows,'kinds':TEAM_KINDS,'school':mine})

@member
def team_edit(request,pk=None):
    team=get_object_or_404(Team,pk=pk,leader=request.user) if pk else None
    if team and team.status=='disbanded': raise Http404()
    university=team.university if team else teamup.school(request.user)
    form=TeamForm(request.POST or None,instance=team)
    if not university: form.add_error(None,'你的學校尚未在平台設定，請聯絡管理員 / Your university is not set up yet; contact the moderators')
    elif request.method=='POST' and form.is_valid():
        try:
            if not team: throttle('team-new:'+str(request.user.pk),10,86400)
            with transaction.atomic():
                obj=form.save(commit=False)
                if not team: obj.leader=request.user; obj.university=university
                obj.save()
                if not team: teamup.start_team(obj)
            return redirect('team',pk=obj.pk)
        except ValidationError as exc: form.add_error(None,exc)
    return render(request,'market/form.html',{'form':form,'title':'發起／編輯組隊 / Start or edit a team','team_form':True})

def team_detail(request,pk):
    team=get_object_or_404(Team.objects.select_related('leader__profile','university'),pk=pk)
    me=request.user
    if team.leader.profile.restricted and me.pk!=team.leader_id and not me.is_staff: raise Http404()
    if request.method=='POST':
        if not me.is_authenticated: return redirect('login')
        if not me.profile.verified or me.profile.restricted: raise PermissionDenied()
        try: valid_email(me.email)
        except ValidationError: raise PermissionDenied()
        action=request.POST.get('action','')
        try:
            if action=='apply':
                teamup.apply_team(team.pk,me,request.POST.get('message','').strip(),request.POST.get('share_profile')=='on')
                messages.success(request,'已提交申請，等待隊長審核 / Application sent. Waiting for the leader.')
            elif action in ('accept','reject'):
                application=request.POST.get('application','')
                if not application.isdigit() or not team.applications.filter(pk=application).exists(): raise Http404()
                teamup.decide(int(application),me,action=='accept')
            elif action=='withdraw': teamup.withdraw(team.pk,me)
            elif action=='leave': teamup.leave(team.pk,me)
            elif action=='remove':
                target=request.POST.get('member','')
                if not target.isdigit(): raise Http404()
                teamup.remove_member(team.pk,me,int(target))
            elif action in ('announce','recruiting','closed','disband'): teamup.manage(team.pk,me,action,request.POST.get('announcement','').strip())
            else: raise Http404()
        except ValidationError as exc: error(request,exc)
        return redirect('team',pk=pk)
    leader=me.pk==team.leader_id
    membership=team.members.filter(user=me).first() if me.is_authenticated else None
    application=team.applications.filter(user=me).first() if me.is_authenticated else None
    members=list(team.members.select_related('user__profile').order_by('joined')) if membership else []
    applications=[]
    if leader:
        for a in team.applications.filter(status='pending').select_related('user__profile').order_by('created'):
            # Academic details only when the applicant ticked "share" for this application.
            a.academic=AcademicProfile.objects.filter(user=a.user).first() if a.share_profile else None
            a.gpa=teamup.shown_gpa(a.user) if a.share_profile else None
            applications.append(a)
    eligible=me.is_authenticated and hasattr(me,'profile') and not membership and not application and team.status=='recruiting' and teamup.same_school_or_open(me,team.university,team.cross_school) and not blocked(me,team.leader)
    return render(request,'market/team.html',{'team':team,'leader':leader,'membership':membership,'application':application,'members':members,'applications':applications,'joined':team.members.filter(role='member').count(),'eligible':eligible,'thread':Thread.objects.filter(team=team).first() if membership else None})

@member
def people(request):
    me=request.user; mine=teamup.school(me)
    scope=request.GET.get('scope',''); q=request.GET.get('q','').strip(); skill=request.GET.get('skill','').strip(); course=re.sub(r'\s+','',request.GET.get('course','')).upper(); kind=request.GET.get('kind','')
    rows=AcademicProfile.objects.filter(public=True,user__profile__restricted=False,user__profile__verified=True).exclude(user=me)
    rows=rows.filter(Q(user__profile__university=mine)|Q(cross_school=True,user__profile__university__isnull=False)) if scope=='all' else rows.filter(user__profile__university=mine)
    rows=rows.exclude(user__blocks_made__blocked=me).exclude(user__blocks_received__blocker=me)
    if q: rows=rows.filter(Q(major__icontains=q)|Q(areas__icontains=q)|Q(projects__icontains=q))
    if skill: rows=rows.filter(skills__icontains=skill)
    if course: rows=rows.filter(courses__icontains=course)
    if kind: rows=rows.filter(kinds__contains=kind)
    # Deliberately no GPA filter or sort: GPA is never a ranking signal.
    rows=rows.select_related('user__profile__university').order_by('-updated')[:100]
    return render(request,'market/people.html',{'rows':rows,'kinds':TEAM_KINDS,'school':mine})

@member
def academic(request,pk):
    owner=get_object_or_404(User,pk=pk,profile__restricted=False)
    if not teamup.can_view_academic(request.user,owner): raise Http404()
    profile=AcademicProfile.objects.filter(user=owner).first()
    my_teams=Team.objects.filter(leader=request.user,status='recruiting') if request.user.pk!=owner.pk and profile and profile.public else []
    return render(request,'market/academic.html',{'owner':owner,'academic':profile,'gpa':teamup.shown_gpa(owner),'my_teams':my_teams})

@member
@require_POST
def invite(request,pk):
    target=get_object_or_404(User,pk=pk,profile__restricted=False)
    team=get_object_or_404(Team,pk=request.POST.get('team') if str(request.POST.get('team','')).isdigit() else 0,leader=request.user)
    try: teamup.invite(team.pk,request.user,target); messages.success(request,'已發送邀請通知 / Invitation sent')
    except ValidationError as exc: error(request,exc)
    return redirect('academic',pk=pk)

# Settings forms bind on any POST: switching every checkbox off can legitimately send an empty body.
def settings_page(request,form,section,title):
    return render(request,'market/settings.html',{'form':form,'section':section,'title':title})

@member
def social_edit(request):
    form=SocialForm(request.POST if request.method=='POST' else None,instance=request.user.profile)
    if request.method=='POST' and form.is_valid(): form.save(); messages.success(request,'已儲存 / Saved'); return redirect('profile_social')
    return settings_page(request,form,'social','交友資料 · Meet / Social profile')

@member
def dating_edit(request):
    form=DatingForm(request.POST if request.method=='POST' else None,instance=request.user.profile)
    if request.method=='POST' and form.is_valid():
        profile=form.save()
        if not profile.dating: Connection.objects.filter(sender=request.user,kind='crush').delete()
        messages.success(request,'已儲存 / Saved'); return redirect('profile_dating')
    return settings_page(request,form,'dating','戀愛模式 · Dating')

@member
def academic_edit(request):
    teamup.school(request.user)
    profile,_=AcademicProfile.objects.get_or_create(user=request.user)
    form=AcademicForm(request.POST if request.method=='POST' else None,instance=profile)
    if request.method=='POST' and form.is_valid(): form.save(); messages.success(request,'已儲存 / Saved'); return redirect('profile_academic')
    return settings_page(request,form,'academic','學術資料 · Team Up / Academic profile')

@member
def gpa(request):
    me=request.user; mine=teamup.school(me)
    form=GpaForm(request.POST or None,initial={'university':mine,'scale':mine.grading_scale if mine else None})
    if request.method=='POST':
        action=request.POST.get('action','create')
        try:
            if action=='create':
                if form.is_valid():
                    if GpaVerification.objects.filter(user=me).count()>=10: raise ValidationError('Up to 10 records / 最多 10 筆紀錄')
                    record=form.save(commit=False); record.user=me; record.save()
                    if request.POST.get('submit')=='review': return redirect('gpa_submit',pk=record.pk)
                    messages.success(request,'已儲存為私密草稿，未經審核不會顯示 / Saved as a private draft; nothing is shown until reviewed')
                    return redirect('gpa')
            else:
                record=get_object_or_404(GpaVerification,pk=request.POST.get('record') if str(request.POST.get('record','')).isdigit() else 0,user=me)
                if action=='withdraw': teamup.withdraw_gpa(record.pk,me)
                elif action=='delete':
                    if record.status=='pending': raise ValidationError('Withdraw the review first / 請先撤回審核')
                    teamup.audit(record,me,'deleted'); record.delete()
                elif action=='visibility':
                    choice=request.POST.get('visibility','')
                    if record.status!='verified' or choice not in dict(GpaVerification.SHOW): raise ValidationError('Only reviewed GPAs can be shown / 只有已審核的 GPA 可以公開')
                    record.visibility=choice; record.save(update_fields=['visibility'])
                else: raise Http404()
                return redirect('gpa')
        except ValidationError as exc: error(request,exc); return redirect('gpa')
    records=GpaVerification.objects.filter(user=me).select_related('university').order_by('-created')
    return render(request,'market/gpa.html',{'form':form,'records':records,'section':'gpa','retention':settings.GPA_PROOF_RETENTION_DAYS})

@member
def gpa_submit(request,pk):
    record=get_object_or_404(GpaVerification.objects.select_related('university'),pk=pk,user=request.user)
    if record.status not in ('draft','rejected'): return redirect('gpa')
    if request.method=='POST':
        try:
            teamup.submit_gpa(record.pk,request.user,teamup.clean_proof(request.FILES.get('proof')))
            messages.success(request,'已提交平台審核 / Submitted for review'); return redirect('gpa')
        except ValidationError as exc: error(request,exc)
    return render(request,'market/gpa_submit.html',{'record':record,'section':'gpa','retention':settings.GPA_PROOF_RETENTION_DAYS})
