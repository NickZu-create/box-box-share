from django.core.management.base import BaseCommand
from django.utils import timezone
from market.models import LoginToken, RateBucket
class Command(BaseCommand):
    help='Remove expired login tokens and rate buckets; run daily alongside clearsessions'
    def handle(self,*args,**options):
        a=LoginToken.objects.filter(expires__lt=timezone.now()).delete()[0]
        b=RateBucket.objects.filter(expires__lt=timezone.now()).delete()[0]
        self.stdout.write(f'Removed {a} expired tokens and {b} rate buckets')
