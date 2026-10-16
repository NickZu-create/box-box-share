from decimal import Decimal
from django.conf import settings
from django.db.models import Count
from .models import CATEGORIES, Item, Order, Survey

# Embodied carbon of one new item per category (kg CO2e), using one cited reference product each.
# Low-end figures are chosen on purpose; a category with no reliable source is left out (None) rather than guessed.
FACTORS = {
    'tech': (Decimal('98'), '入門平板電腦 (Apple iPad 2018)', 'Entry tablet (Apple iPad 2018)', 'Apple Product Environmental Report, iPad, Mar 2018', 'https://www.apple.com/environment/pdf/products/ipad/iPad_PER_mar2018.pdf'),
    'study': (Decimal('1.2'), '精裝書', 'Hardcover book', 'KTH CESC, climate-friendly paperbacks (hardcover comparison)', 'https://www.cesc.kth.se/news/news-archive/cesc-research-behind-climate-friendly-paperbacks-1.403311'),
    'outdoor': (Decimal('30'), '露營帳篷', 'Camping tent', 'Arbor, tent carbon footprint (typical value)', 'https://www.arbor.eco/carbon-footprint/tent'),
    'home': (Decimal('10'), '桌燈', 'Desk lamp', 'Arbor, desk lamp carbon footprint (typical value)', 'https://www.arbor.eco/carbon-footprint/desk-lamp'),
    'creative': (Decimal('14.1'), '木結他（廠商數據下限）', 'Acoustic guitar (maker-reported low end)', 'Furch Guitars, production footprint', 'https://www.renewableenergymagazine.com/panorama/furch-guitars-reduces-its-carbon-footprint-20200915'),
    'other': None,
}
METHOD_URL = 'https://libraryofthings.co.uk/blog/how-we-calculate-our-impact-2024-update'
# The platform's own post-borrow survey replaces the configured rate once this many yes/no answers exist; 'not sure' is left out of the rate.
SURVEY_MIN = 30

def avoided_rate():
    answers=dict(Survey.objects.values_list('answer').annotate(n=Count('pk')))
    yes,no=answers.get('yes',0),answers.get('no',0)
    survey={'yes':yes,'no':no,'unsure':answers.get('unsure',0),'counted':yes+no,'total':sum(answers.values()),'min':SURVEY_MIN,'used':yes+no>=SURVEY_MIN}
    rate=(Decimal(yes)/(yes+no)).quantize(Decimal('0.01')) if survey['used'] else Decimal(str(getattr(settings,'CARBON_AVOIDED_PURCHASE_RATE','0.25')))
    return rate,survey

def impact_summary():
    rate,survey=avoided_rate()
    done=dict(Order.objects.filter(status='completed').values_list('item__category').annotate(n=Count('pk')))
    listed=dict(Item.objects.filter(status='listed').values_list('category').annotate(n=Count('pk')))
    rows=[]; total=Decimal('0.0')
    for key,label in CATEGORIES:
        factor=FACTORS.get(key)
        borrows=done.get(key,0)
        kg=(factor[0]*rate*borrows).quantize(Decimal('0.1')) if factor else None
        if kg: total+=kg
        rows.append({'key':key,'label':label,'borrows':borrows,'listed':listed.get(key,0),'factor':factor,'kg':kg})
    return {'rows':rows,'total_kg':total,'borrows':sum(done.values()),'listed':sum(listed.values()),'rate_percent':int(rate*100),'survey':survey}
