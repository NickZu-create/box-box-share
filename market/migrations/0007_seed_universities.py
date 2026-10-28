from decimal import Decimal
from django.db import migrations

POLICY = '上傳官方成績單或成績證明（PDF 或截圖），先遮蓋學號及證件號碼。審核員人工核對 GPA、滿分制及學期；屬平台審核，並非大學官方認證。 / Upload an official transcript or grade report (PDF or screenshot) with student and ID numbers covered. A reviewer checks the GPA, scale and term by hand. This is a platform review, not official university certification.'
# Only CityUHK is enabled. The others are placeholders: confirm their student email domains and grading scales before enabling them in admin.
SCHOOLS = [
    ('cityuhk','香港城市大學 CityUHK','my.cityu.edu.hk','4.30',True),
    ('hku','香港大學 HKU','connect.hku.hk','4.30',False),
    ('cuhk','香港中文大學 CUHK','link.cuhk.edu.hk','4.00',False),
    ('hkust','香港科技大學 HKUST','connect.ust.hk','4.30',False),
]

def seed(apps,schema_editor):
    University=apps.get_model('market','University'); Profile=apps.get_model('market','Profile')
    by_domain={}
    for code,name,domains,scale,enabled in SCHOOLS:
        u,_=University.objects.get_or_create(code=code,defaults={'name':name,'country':'HK','email_domains':domains,'grading_scale':Decimal(scale),'verification_policy':POLICY,'enabled':enabled})
        for d in domains.split(','): by_domain[d]=u
    for p in Profile.objects.filter(university__isnull=True).select_related('user'):
        school=by_domain.get(p.user.email.rsplit('@',1)[-1].lower())
        if school: p.university=school; p.save(update_fields=['university'])

class Migration(migrations.Migration):
    dependencies = [('market','0006_campus_connect')]
    operations = [migrations.RunPython(seed,migrations.RunPython.noop)]
