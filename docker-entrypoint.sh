#!/bin/sh
set -e

echo "🔄 Esecuzione controlli e migrazioni automatiche DB..."

# Esegue le migrazioni standard
python manage.py migrate --noinput

# Assicura le colonne per i database SQLite già presistenti che potrebbero aver saltato la migrazione
python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    # manager_workoutsession columns
    cursor.execute(\"PRAGMA table_info(manager_workoutsession)\")
    cols = [row[1] for row in cursor.fetchall()]
    if 'status' not in cols:
        cursor.execute(\"ALTER TABLE manager_workoutsession ADD COLUMN status VARCHAR(20) DEFAULT 'finished'\")
    if 'condition_photo_id' not in cols:
        cursor.execute(\"ALTER TABLE manager_workoutsession ADD COLUMN condition_photo_id INTEGER NULL REFERENCES gallery_image(id)\")

    # manager_routine columns
    cursor.execute(\"PRAGMA table_info(manager_routine)\")
    r_cols = [row[1] for row in cursor.fetchall()]
    if 'current_week' not in r_cols:
        cursor.execute(\"ALTER TABLE manager_routine ADD COLUMN current_week INTEGER DEFAULT 1\")
    if 'total_weeks' not in r_cols:
        cursor.execute(\"ALTER TABLE manager_routine ADD COLUMN total_weeks INTEGER DEFAULT 4\")

# Auto-cleanup any stale active sessions from past days
try:
    from django.utils import timezone
    from wger.manager.models import WorkoutSession
    stale_count = WorkoutSession.objects.filter(status='active', date__lt=timezone.now().date()).update(status='interrupted')
    if stale_count > 0:
        print(f'🧹 Ripulite {stale_count} sessioni workout rimaste attive da giorni precedenti.')
except Exception as e:
    print(f'Nota cleanup sessioni: {e}')
" || true

echo "📦 Raccolta file statici (collectstatic)..."
python manage.py collectstatic --noinput || true

echo "🚀 Avvio server di produzione (Gunicorn)..."
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    exec gunicorn wger.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 2
fi
