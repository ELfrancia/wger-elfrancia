#!/bin/sh
set -e

echo "🔄 Esecuzione migrazioni database Django..."
python manage.py migrate --noinput

echo "🚀 Avvio server Django..."
exec python manage.py runserver 0.0.0.0:8000
