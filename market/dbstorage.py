from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

# Photos live in PostgreSQL for hosts without a persistent disk (e.g. Render free). Files are only served
# through the authorised /media/ view, so there is deliberately no public url().
@deconstructible
class DatabaseStorage(Storage):
    def _open(self,name,mode='rb'):
        from .models import StoredFile
        try: data=StoredFile.objects.values_list('content',flat=True).get(name=name)
        except StoredFile.DoesNotExist: raise FileNotFoundError(name)
        return ContentFile(bytes(data),name=name)
    def _save(self,name,content):
        from .models import StoredFile
        if hasattr(content,'seek'): content.seek(0)
        data=b''.join(content.chunks())
        StoredFile.objects.create(name=name,content=data,size=len(data))
        return name
    def exists(self,name):
        from .models import StoredFile
        return StoredFile.objects.filter(name=name).exists()
    def delete(self,name):
        from .models import StoredFile
        StoredFile.objects.filter(name=name).delete()
    def size(self,name):
        from .models import StoredFile
        try: return StoredFile.objects.values_list('size',flat=True).get(name=name)
        except StoredFile.DoesNotExist: raise FileNotFoundError(name)
    def url(self,name): raise NotImplementedError('Served through the /media/ view')
