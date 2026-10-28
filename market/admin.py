from django.contrib import admin
from .models import *
from django.utils.html import format_html
admin.site.site_header='Box Box Share · 社群管理'
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display=['nickname','verified','restricted','user']
    readonly_fields=['user','verified','avatar']
    fields=['nickname','user','verified','restricted']
    search_fields=['nickname','user__email']
@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display=['title','owner','status','created']
    list_filter=['status','category']
    fields=['title','owner','description','status']
    readonly_fields=['title','owner','description']
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
@admin.register(Wanted)
class WantedAdmin(admin.ModelAdmin):
    list_display=['title','owner','active']
    fields=['title','owner','description','active']
    readonly_fields=['title','owner','description']
    def has_add_permission(self,request): return False
@admin.register(Buddy)
class BuddyAdmin(admin.ModelAdmin):
    list_display=['title','owner','kind','when','active']
    list_filter=['active','kind']
    fields=['title','owner','description','location','when','active']
    readonly_fields=['title','owner','description','location','when']
    def has_add_permission(self,request): return False
@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display=['kind','target','reporter','resolved','created']
    list_filter=['resolved','kind']
    readonly_fields=['reporter','kind','target','target_link','reason','created']
    def target_link(self,obj):
        route={'item':f'/admin/market/item/{obj.target}/change/','user':f'/people/{obj.target}/','order':f'/admin/market/order/{obj.target}/change/','buddy':f'/admin/market/buddy/{obj.target}/change/','team':f'/admin/market/team/{obj.target}/change/'}
        return format_html('<a href="{}">Open target</a>',route.get(obj.kind,'/admin/'))
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
from django.core.exceptions import ValidationError, PermissionDenied
from .services import resolve_dispute
class EvidenceInline(admin.TabularInline):
    model=Evidence
    fields=['actor','phase','created','preview']
    readonly_fields=fields
    extra=0
    can_delete=False
    def has_add_permission(self,request,obj=None): return False
    def preview(self,obj): return format_html('<a href="/media/evidence/{}/">View private photo</a>',obj.pk)
class AuditInline(admin.TabularInline):
    model=Audit
    fields=['actor','action','data','created']
    readonly_fields=fields
    extra=0
    can_delete=False
    def has_add_permission(self,request,obj=None): return False
@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display=['id','item','borrower','status','start','end']
    inlines=[EvidenceInline,AuditInline]
    list_filter=['status']
    actions=['resolve_completed','resolve_cancelled']
    @admin.action(description='Resolve dispute: both parties confirmed return / 雙方已歸還，結案',permissions=['resolve'])
    def resolve_completed(self,request,queryset): self.resolve(request,queryset,'completed')
    @admin.action(description='Resolve dispute: no handover, cancel / 未交接，取消',permissions=['resolve'])
    def resolve_cancelled(self,request,queryset): self.resolve(request,queryset,'cancelled')
    def has_resolve_permission(self,request): return request.user.has_perm('market.change_order')
    def resolve(self,request,queryset,outcome):
        for order in queryset:
            try: resolve_dispute(order.pk,request.user,outcome); self.message_user(request,f'#{order.pk} resolved')
            except ValidationError as exc: self.message_user(request,'; '.join(exc.messages),level='error')
admin.site.register(Audit,ReadOnlyAdmin)
admin.site.register(Review,ReadOnlyAdmin)
admin.site.register(Survey,ReadOnlyAdmin)

@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display=['name','code','country','email_domains','grading_scale','enabled']
    list_filter=['enabled','country']
    def has_delete_permission(self,request,obj=None): return False
@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display=['title','leader','university','kind','course_code','status','created']
    list_filter=['status','kind','university']
    fields=['title','leader','university','course_code','description','announcement','status']
    readonly_fields=['title','leader','university','course_code','description','announcement']
    def has_add_permission(self,request): return False
from .teamup import review_gpa
# GPA review: visible only to staff holding market.review_gpa. Values are read-only; decisions go through
# review_gpa(), which blocks self-review and writes the audit trail. Opening a proof is audited by the media view.
class GpaAuditInline(admin.TabularInline):
    model=GpaAudit
    fields=['actor','action','created']
    readonly_fields=fields
    extra=0
    can_delete=False
    def has_add_permission(self,request,obj=None): return False
@admin.register(GpaVerification)
class GpaVerificationAdmin(admin.ModelAdmin):
    list_display=['id','user','university','value','scale','term','status','submitted']
    list_filter=['status','university']
    fields=['user','university','value','scale','term','status','submitted','proof_link','proof_removed','reviewer','reviewed','note']
    readonly_fields=['user','university','value','scale','term','status','submitted','proof_link','proof_removed','reviewer','reviewed']
    inlines=[GpaAuditInline]
    actions=['approve','reject']
    def reviewer_only(self,request): return request.user.is_staff and request.user.has_perm('market.review_gpa')
    def has_module_permission(self,request): return self.reviewer_only(request)
    def has_view_permission(self,request,obj=None): return self.reviewer_only(request)
    def has_change_permission(self,request,obj=None): return self.reviewer_only(request)
    def has_review_permission(self,request): return self.reviewer_only(request)
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def get_queryset(self,request): return super().get_queryset(request).select_related('user','university')
    def proof_link(self,obj):
        if not obj.proof: return '—'
        return format_html('<a href="/media/gpa/{}/" target="_blank" rel="noopener">Open private proof (logged)</a>',obj.pk)
    @admin.action(description='Approve: GPA matches the proof / 核對無誤，通過',permissions=['review'])
    def approve(self,request,queryset): self.decide(request,queryset,True)
    @admin.action(description='Reject: proof does not match / 證明不符，不通過',permissions=['review'])
    def reject(self,request,queryset): self.decide(request,queryset,False)
    def decide(self,request,queryset,approve):
        for record in queryset:
            try: review_gpa(record.pk,request.user,approve,record.note); self.message_user(request,f'GPA #{record.pk} {"verified" if approve else "rejected"}')
            except (ValidationError,PermissionDenied) as exc: self.message_user(request,f'GPA #{record.pk}: {"; ".join(getattr(exc,"messages",[str(exc)]))}',level='error')
