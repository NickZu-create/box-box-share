from django.db import migrations

def install(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
        schema_editor.execute('''ALTER TABLE market_order ADD CONSTRAINT no_overlapping_reservations EXCLUDE USING gist (item_id WITH =, tstzrange("start", "end", '[)') WITH &&) WHERE (status IN ('accepted','active','return_pending','disputed'))''')
    elif schema_editor.connection.vendor=='sqlite':
        for operation in ('INSERT','UPDATE'):
            schema_editor.execute(f'''CREATE TRIGGER reservation_guard_{operation.lower()} BEFORE {operation} ON market_order WHEN NEW.status IN ('accepted','active','return_pending','disputed') BEGIN SELECT RAISE(ABORT,'overlapping reservation') WHERE EXISTS (SELECT 1 FROM market_order old WHERE old.item_id=NEW.item_id AND old.id!=NEW.id AND old.status IN ('accepted','active','return_pending','disputed') AND old.start<NEW.end AND old.end>NEW.start); END''')
def remove(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql': schema_editor.execute('ALTER TABLE market_order DROP CONSTRAINT no_overlapping_reservations')
    elif schema_editor.connection.vendor=='sqlite':
        for op in ('insert','update'): schema_editor.execute('DROP TRIGGER reservation_guard_'+op)
class Migration(migrations.Migration):
    dependencies=[('market','0001_initial')]
    operations=[migrations.RunPython(install,remove)]
