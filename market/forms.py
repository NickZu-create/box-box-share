from django import forms
from django.utils import timezone
from .models import *
from .services import interval, clean_image
LABELS = {'title':'物品名稱 / Title','category':'分類 / Category','description':'描述 / Description','condition':'物品狀況 / Condition','daily':'每日租金 HKD / Daily rent','deposit':'押金 HKD / Deposit','available_start':'可借開始 / Available from','available_end':'可借結束 / Available until','max_days':'最長借用天數 / Maximum days','location':'交接地點 / Meet-up location','status':'物品狀態 / Listing status','start':'開始時間 / Start','end':'結束時間 / End','budget':'總預算 HKD / Total budget','active':'公開尋物 / Active request','nickname':'暱稱 / Nickname','avatar':'頭像 / Avatar','bio':'自我介紹 / About me','interests':'興趣標籤，以逗號分隔 / Interests, comma separated','social':'開放交友：願意透過借物和搭子活動認識新朋友 / Open to new friends','dating':'開放心動配對（須年滿 18 歲） / Open to dating (18+)','kind':'搭子類型 / Buddy type','when':'活動時間 / When','item':'可借出的物品（選填） / An item you can lend (optional)','spots':'名額 / Spots'}
class DatesMixin:
    def setup(self):
        for name,field in self.fields.items():
            field.label=LABELS.get(name,field.label)
            if isinstance(field,forms.DateTimeField):
                field.widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M',attrs={'type':'datetime-local'})
                field.input_formats=['%Y-%m-%dT%H:%M']
            if isinstance(field,forms.CharField) and isinstance(field.widget,forms.Textarea): field.widget.attrs['rows']=4
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
        fields=['title','category','description','condition','daily','deposit','available_start','available_end','max_days','location','status']
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.setup()
        if self.instance.pk: self.fields['remove_photos'].queryset=self.instance.photos.all()
        else: self.fields.pop('remove_photos')
    def clean(self):
        d=super().clean()
        old_count=self.instance.photos.count() if self.instance.pk else 0
        removed=len(d.get('remove_photos',[]))
        if old_count-removed+bool(d.get('photo'))>8: raise forms.ValidationError('最多 8 張照片 / Maximum 8 photos')
        return d
    def clean_photo(self): return clean_image(self.cleaned_data.get('photo'))
class WantedForm(DatesMixin,forms.ModelForm):
    class Meta:
        model=Wanted
        fields=['title','category','description','start','end','budget','location','active']
    def __init__(self,*a,**kw): super().__init__(*a,**kw); self.setup()
class BookingForm(DatesMixin,forms.Form):
    start=forms.DateTimeField()
    end=forms.DateTimeField()
    def __init__(self,*a,**kw): super().__init__(*a,**kw); self.setup()
class BuddyForm(DatesMixin,forms.ModelForm):
    class Meta:
        model=Buddy
        fields=['kind','title','description','when','location','item','spots','active']
    def __init__(self,user,*a,**kw):
        super().__init__(*a,**kw); self.setup()
        self.fields['item'].queryset=Item.objects.filter(owner=user,status='listed')
        self.fields['active'].label='公開招募 / Open for joining'
        self.fields['description'].widget.attrs['placeholder']='想做什麼、適合誰、需要帶什麼 / What, who it suits, what to bring'
    def clean_when(self):
        when=self.cleaned_data['when']
        if 'when' in self.changed_data and when<=timezone.now(): raise forms.ValidationError('活動時間須在未來 / Must be in the future')
        return when
class ProfileForm(forms.ModelForm):
    adult=forms.BooleanField(required=False,label='我確認已年滿 18 歲 / I confirm I am 18 or older')
    class Meta:
        model=Profile
        fields=['nickname','avatar','bio','interests','social','dating']
        labels=LABELS
        widgets={'bio':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.fields['adult'].initial=self.instance.dating
        self.fields['dating'].help_text='心動是秘密的：只有雙方都對彼此心動才會通知。關閉後會撤回你送出的心動。 / Crushes stay secret unless mutual. Turning this off withdraws the crushes you sent.'
    def clean(self):
        d=super().clean()
        if d.get('dating') and not d.get('adult'): self.add_error('adult','開放心動配對須確認年滿 18 歲 / Confirm you are 18 or older to turn on dating')
        return d
    def clean_avatar(self):
        avatar=self.cleaned_data.get('avatar')
        return clean_image(avatar) if hasattr(avatar,'content_type') else avatar
