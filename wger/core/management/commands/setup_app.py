# Standard Library
import os

# Django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Inizializza automaticamente il database, scarica gli esercizi e genera dati di prova per il primo avvio.
    """

    help = 'Inizializza il database da zero senza bisogno di copiare file sqlite o media manuali'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 [1/5] Creazione schema tabelle database...'))
        call_command('migrate')

        self.stdout.write(self.style.SUCCESS('📦 [2/5] Caricamento categorie, muscoli ed equipaggiamento...'))
        try:
            call_command('loaddata', 'categories', 'equipment', 'muscles', 'exercise-base-data')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Info loaddata: {e}'))

        self.stdout.write(self.style.SUCCESS('🏋️ [3/5] Sincronizzazione esercizi ufficiali...'))
        try:
            call_command('sync-exercises')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Info sync-exercises: {e}'))

        self.stdout.write(self.style.SUCCESS('📊 [4/5] Popolamento dati di prova (schede, peso, utenti)...'))
        try:
            call_command('dummy-generator')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Info dummy-generator: {e}'))

        User = get_user_model()
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123')

        if not User.objects.filter(username=username).exists():
            self.stdout.write(self.style.SUCCESS(f"🔐 [5/5] Creazione superuser '{username}'..."))
            User.objects.create_superuser(username, email, password)
        else:
            self.stdout.write(self.style.SUCCESS(f"🔐 [5/5] Utente '{username}' già presente."))

        self.stdout.write(self.style.SUCCESS('✨ Inizializzazione completata con successo!'))
