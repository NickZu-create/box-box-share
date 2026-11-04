from django import forms
from django.db import transaction
from django.forms.utils import ErrorList
from django.utils import timezone
from .models import *
from datetime import timedelta
from .services import interval, clean_image, derive_title
from .i18n import loc
LABELS = {'title':'物品名稱 / Title','category':'分類 / Category','description':'描述 / Description','condition':'物品狀況 / Condition','daily':'每日租金 HKD / Daily rent','deposit':'押金 HKD / Deposit','available_start':'可借開始 / Available from','available_end':'可借結束 / Available until','max_days':'最長借用天數 / Maximum days','location':'交接地點 / Meet-up location','status':'物品狀態 / Listing status','start':'開始時間 / Start','end':'結束時間 / End','budget':'總預算 HKD / Total budget','active':'公開尋物 / Active request','nickname':'暱稱 / Nickname','avatar':'頭像 / Avatar','bio':'自我介紹 / About me','interests':'興趣 / Interests','skills':'技能 / Skills','languages':'交流語言 / Languages'}
# Form text is written "繁中 / English"; these show it in the visitor's language, including validation errors.
class LocErrorList(ErrorList):
    def __getitem__(self,i): return loc(super().__getitem__(i))
def localize(form):
    for field in form.fields.values():
        field.label=loc(field.label)
        field.help_text=loc(field.help_text)
        if 'placeholder' in field.widget.attrs: field.widget.attrs['placeholder']=loc(field.widget.attrs['placeholder'])
        if isinstance(field,forms.ChoiceField) and not isinstance(field,forms.ModelChoiceField):
            field.choices=[(loc(k),[(kk,loc(vv)) for kk,vv in v]) if isinstance(v,(list,tuple)) else (k,loc(v)) for k,v in field.choices]
class Localized:
    def __init__(self,*a,**kw):
        kw.setdefault('error_class',LocErrorList)
        super().__init__(*a,**kw)
class DatesMixin(Localized):
    def setup(self,labels=LABELS):
        for name,field in self.fields.items():
            field.label=labels.get(name,field.label)
            if isinstance(field,forms.DateTimeField):
                field.widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M',attrs={'type':'datetime-local'})
                field.input_formats=['%Y-%m-%dT%H:%M']
            if isinstance(field,forms.CharField) and isinstance(field.widget,forms.Textarea): field.widget.attrs['rows']=4
        localize(self)
    def clean(self):
        d=super().clean()
        start=d.get('start',d.get('available_start')); end=d.get('end',d.get('available_end'))
        if start and end: interval(start,end)
        return d
class ItemForm(DatesMixin,forms.ModelForm):
    photo=forms.FileField(required=False,label='新增物品照片 / Add photo · JPEG, PNG, WebP ≤5MB')
    remove_photos=forms.ModelMultipleChoiceField(queryset=ItemPhoto.objects.none(),required=False,widget=forms.CheckboxSelectMultiple,label='移除照片 / Remove photos')
    class Meta:
        model=Item
        fields=['intent','title','category','description','condition','daily','deposit','available_start','available_end','max_days','location','status']
        widgets={'intent':forms.RadioSelect}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.setup()
        if self.instance.pk:
            self.fields['remove_photos'].queryset=self.instance.photos.all()
            # Existing orders were made under this listing type.
            self.fields['intent'].disabled=True
        else:
            self.fields.pop('remove_photos')
            now=timezone.localtime().replace(second=0,microsecond=0)
            self.initial.setdefault('available_start',now); self.initial.setdefault('available_end',now+timedelta(days=7))
            self.initial.setdefault('max_days',7); self.initial.setdefault('deposit',0); self.initial.setdefault('location','CityUHK campus'); self.initial.setdefault('category','other')
        # A price and a description are enough to post; the rest has sensible defaults.
        for name in ('title','category','deposit','available_start','available_end','max_days','location','status','intent'): self.fields[name].required=False
        self.fields['status'].choices=[c for c in self.fields['status'].choices if c[0]!='sold']
    def clean(self):
        d=super().clean()
        if 'description' not in d or 'daily' not in d: return d
        inst=self.instance if self.instance.pk else None
        fallback=lambda name,default: d.get(name) if d.get(name) not in (None,'') else (getattr(inst,name) if inst else default)
        now=timezone.now().replace(second=0,microsecond=0)
        d['intent']=d.get('intent') or (inst.intent if inst else 'rent')
        d['title']=d.get('title') or derive_title(d['description'])
        d['category']=fallback('category','other')
        d['location']=fallback('location','CityUHK campus')
        d['status']=fallback('status','listed')
        if d['intent']=='sale':
            d['deposit']=0; d['max_days']=365
            d['available_start']=inst.available_start if inst else now
            d['available_end']=inst.available_end if inst else now+timedelta(days=365)
        else:
            d['deposit']=fallback('deposit',0); d['max_days']=fallback('max_days',7)
            d['available_start']=fallback('available_start',now); d['available_end']=fallback('available_end',now+timedelta(days=7))
            if not self.has_error('available_end') and not self.has_error('available_start'): interval(d['available_start'],d['available_end'])
        old_count=self.instance.photos.count() if self.instance.pk else 0
        removed=len(d.get('remove_photos',[]))
        if old_count-removed+bool(d.get('photo'))>8: raise forms.ValidationError('最多 8 張照片 / Maximum 8 photos')
        return d
    def clean_photo(self): return clean_image(self.cleaned_data.get('photo'))
class WantedForm(DatesMixin,forms.ModelForm):
    class Meta:
        model=Wanted
        fields=['intent','title','category','description','start','end','budget','location','active']
        widgets={'intent':forms.RadioSelect}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.setup()
        if not self.instance.pk:
            self.fields.pop('active')
            now=timezone.localtime().replace(second=0,microsecond=0)
            self.initial.setdefault('start',now); self.initial.setdefault('end',now+timedelta(days=7)); self.initial.setdefault('location','CityUHK campus'); self.initial.setdefault('category','other')
        for name in ('title','category','start','end','location','intent'): self.fields[name].required=False
    def clean(self):
        d=super().clean()
        if 'description' not in d or 'budget' not in d: return d
        inst=self.instance if self.instance.pk else None
        fallback=lambda name,default: d.get(name) if d.get(name) not in (None,'') else (getattr(inst,name) if inst else default)
        now=timezone.now().replace(second=0,microsecond=0)
        d['intent']=d.get('intent') or (inst.intent if inst else 'borrow')
        d['title']=d.get('title') or derive_title(d['description'])
        d['category']=fallback('category','other'); d['location']=fallback('location','CityUHK campus')
        # Buying has no dates; a request stays open for a month.
        horizon=30 if d['intent']=='buy' else 7
        d['start']=fallback('start',now); d['end']=fallback('end',now+timedelta(days=horizon))
        return d
class BookingForm(DatesMixin,forms.Form):
    start=forms.DateTimeField()
    end=forms.DateTimeField()
    def __init__(self,*a,**kw): super().__init__(*a,**kw); self.setup()
class ProfileForm(Localized,forms.ModelForm):
    remove_avatar=forms.BooleanField(required=False,label='移除目前頭像 / Remove current avatar')
    class Meta:
        model=Profile
        fields=['nickname','avatar','bio','interests','skills','languages','university','major','academic_year','faculty','contact_whatsapp','contact_phone','contact_wechat','contact_instagram','request_emails']
        labels={**LABELS,'university':'大學（選填） / University (optional)','major':'主修或課程（選填） / Major or Programme (optional)','academic_year':'年級（選填） / Academic year (optional)','faculty':'學院（選填） / Faculty or College (optional)','contact_whatsapp':'WhatsApp（選填） / WhatsApp (optional)','contact_phone':'電話（選填） / Phone (optional)','contact_wechat':'WeChat（選填） / WeChat (optional)','contact_instagram':'Instagram（選填） / Instagram (optional)'}
        # A plain file input. Django's default widget links to the current file's public URL, but photos are
        # private: DatabaseStorage (MEDIA_STORAGE=db, used on Render) has no public URL and raised, so
        # /profile/ returned a server error for every account that had uploaded an avatar.
        widgets={'avatar':forms.FileInput(attrs={'accept':'image/jpeg,image/png,image/webp'}),'bio':forms.Textarea(attrs={'rows':3})}
        help_texts={'bio':'只向已登入的成員顯示，例如主修、想認識怎樣的搭子。 / Shown to signed-in members only, e.g. your major or the buddies you hope to meet.','interests':'以逗號分隔 / Comma separated','skills':'以逗號分隔，例如 Python, 攝影 / Comma separated, e.g. Python, photography','languages':'例如 廣東話, English, 普通話 / e.g. Cantonese, English, Mandarin'}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        if not self.instance.avatar: self.fields.pop('remove_avatar')
        localize(self)
    def clean_avatar(self):
        avatar=self.cleaned_data.get('avatar')
        return clean_image(avatar) if hasattr(avatar,'content_type') else avatar
    def save(self,commit=True):
        old=Profile.objects.filter(pk=self.instance.pk).values_list('avatar',flat=True).first()
        profile=super().save(commit=False)
        if self.cleaned_data.get('remove_avatar') and 'avatar' not in self.files: profile.avatar=''
        if commit: profile.save()
        if old and old!=profile.avatar.name:
            storage=profile.avatar.storage
            transaction.on_commit(lambda: storage.delete(old))
        return profile
BUDDY_LABELS={'category':'類別 / Category','kind':'類型 / Type','title':'標題 / Title','description':'描述 / Description','starts':'開始時間 / Starts','ends':'結束時間（選填） / Ends (optional)','location':'地點 / Place','capacity':'所需人數（不含發起人） / People needed (not counting you)','skills':'技能要求（選填） / Skills wanted (optional)','languages':'交流語言（選填） / Languages (optional)'}
class BuddyForm(DatesMixin,forms.ModelForm):
    class Meta:
        model=BuddyPost
        fields=['category','kind','title','description','starts','ends','location','capacity','skills','languages']
        help_texts={'capacity':'名額不含你這位發起人。例如需要 3 位隊友就填 3。 / Spots do not include you, the host. Need 3 teammates? Enter 3.','ends':'不填則以開始時間計算是否已結束。 / Leave empty and the post ends at its start time.','location':'可填校園地點或「線上」 / A campus location, or “Online”'}
    def __init__(self,*a,joined=0,**kw):
        super().__init__(*a,**kw)
        self.joined=joined
        names=dict(BUDDY_KINDS)
        self.fields['kind'].choices=[('',  '---------')]+[(label,[(k,names[k]) for k in KINDS_BY_CATEGORY[key]]) for key,label in BUDDY_CATEGORIES]
        self.fields['capacity'].widget.attrs.update(min=1,max=50)
        self.setup(BUDDY_LABELS)
    def clean(self):
        d=super().clean()
        category,kind,starts,ends=d.get('category'),d.get('kind'),d.get('starts'),d.get('ends')
        if category and kind and kind not in KINDS_BY_CATEGORY[category]: self.add_error('kind','類型與類別不符 / This type does not belong to the chosen category')
        if starts and ('starts' in self.changed_data or not self.instance.pk) and starts<=timezone.now(): self.add_error('starts','開始時間須在未來 / Must be in the future')
        if starts and ends and ends<=starts: self.add_error('ends','結束時間須晚於開始時間 / Must be after the start')
        if d.get('capacity') and d['capacity']<self.joined: self.add_error('capacity',f'已有 {self.joined} 人加入，名額不能少於此數 / {self.joined} people have already joined; spots cannot be fewer')
        return d

LOSTFOUND_LABELS={'kind':'發布類型 / Post type','category':'物品分類 / Item category','title':'物品名稱 / Item name','description':'物品特徵與情況 / Description and identifying details','occurred_at':'丟失或拾到時間 / Lost or found at','location':'丟失或拾到地點 / Lost or found near','color':'顏色（選填） / Colour (optional)','photo':'照片（選填） / Photo (optional)','status':'狀態 / Status'}
class LostFoundForm(DatesMixin,forms.ModelForm):
    class Meta:
        model=LostFoundPost
        fields=['kind','category','title','description','occurred_at','location','color','photo','status']
        widgets={'photo':forms.FileInput(attrs={'accept':'image/jpeg,image/png,image/webp'})}
        help_texts={'description':'請勿公開證件號碼、完整姓名、電話或住址；保留部分特徵讓對方核對。 / Do not publish ID numbers, full names, phone numbers or home addresses; keep some details private for verification.','photo':'上限 5 MB；請遮蓋證件和個人資料。 / Up to 5 MB; cover identity and personal details.'}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.setup(LOSTFOUND_LABELS)
    def clean_occurred_at(self):
        when=self.cleaned_data['occurred_at']
        if when>timezone.now(): raise forms.ValidationError('時間不能晚於現在 / The time cannot be in the future')
        return when
    def clean_photo(self):
        value=self.cleaned_data.get('photo')
        return clean_image(value) if hasattr(value,'content_type') else value
