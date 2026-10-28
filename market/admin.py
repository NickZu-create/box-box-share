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
@admin.register(BuddyPost)
class BuddyPostAdmin(admin.ModelAdmin):
    list_display=['title','owner','category','kind','starts','capacity','status']
    list_filter=['status','category','kind']
    fields=['title','owner','category','kind','description','location','starts','ends','capacity','status']
    readonly_fields=['title','owner','category','kind','description','location','starts','ends','capacity']
    search_fields=['title','owner__profile__nickname']
    def has_add_permission(self,request): return False
@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display=['kind','target','reporter','resolved','created']
    list_filter=['resolved','kind']
    readonly_fields=['reporter','kind','target','target_link','reason','created']
    def target_link(self,obj):
        route={'item':f'/admin/market/item/{obj.target}/change/','user':f'/people/{obj.target}/','order':f'/admin/market/order/{obj.target}/change/','buddy':f'/admin/market/buddypost/{obj.target}/change/'}
        return format_html('<a href="{}">Open target</a>',route.get(obj.kind,'/admin/'))
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
from django.core.exceptions import ValidationError
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
