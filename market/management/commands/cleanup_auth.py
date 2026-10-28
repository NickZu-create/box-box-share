from django.core.management.base import BaseCommand
from django.utils import timezone
from market.models import LoginToken, RateBucket
from market.teamup import purge_proofs
class Command(BaseCommand):
    help='Remove expired login tokens, rate buckets and GPA proofs past retention; run daily alongside clearsessions'
    def handle(self,*args,**options):
        a=LoginToken.objects.filter(expires__lt=timezone.now()).delete()[0]
        b=RateBucket.objects.filter(expires__lt=timezone.now()).delete()[0]
        c=purge_proofs()
        self.stdout.write(f'Removed {a} expired tokens, {b} rate buckets and {c} GPA proofs past retention')
