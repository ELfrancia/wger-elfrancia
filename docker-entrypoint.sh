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
" || true

echo "🚀 Avvio server Django..."
exec python manage.py runserver 0.0.0.0:8000
