# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.conf import settings
import requests
import os
from wger.exercises.models import (
    CalisthenicsExercise, 
    ExerciseTag, 
    Exercise, 
    Translation, 
    ExerciseCategory, 
    Equipment, 
    Muscle, 
    ExerciseImage
)
from wger.core.models.license import License
from wger.core.models import Language

class Command(BaseCommand):
    help = 'Sync curated, published exercises from self-hosted Baserow to local Django SQLite database and download GIFs'

    def handle(self, *args, **options):
        baserow_url = os.environ.get('BASEROW_URL', 'http://localhost:8080').rstrip('/')
        baserow_email = os.environ.get('BASEROW_EMAIL')
        baserow_password = os.environ.get('BASEROW_PASSWORD')
        baserow_token = os.environ.get('BASEROW_TOKEN')
        baserow_db_id = os.environ.get('BASEROW_DB_ID')
        baserow_table_id = os.environ.get('BASEROW_TABLE_ID')

        primary_field_name = "Name"
        headers = {}
        is_admin_mode = False

        # If email and password are provided, get the JWT token (Admin credentials)
        if baserow_email and baserow_password:
            self.stdout.write("Obtaining JWT admin token from Baserow...")
            auth_url = f"{baserow_url}/api/user/token-auth/"
            try:
                res = requests.post(auth_url, json={"username": baserow_email, "password": baserow_password}, timeout=10)
                res.raise_for_status()
                jwt_token = res.json()["token"]
                headers = {
                    "Authorization": f"JWT {jwt_token}",
                    "Content-Type": "application/json"
                }
                is_admin_mode = True
                self.stdout.write(self.style.SUCCESS("Authenticated successfully as administrator."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Baserow Admin Authentication failed: {e}. Falling back to database token..."))

        # Fallback to Database Token if admin auth failed or not provided
        if not is_admin_mode:
            if not baserow_token:
                self.stdout.write(self.style.ERROR("Error: No valid API Token or Admin credentials provided."))
                return
            headers = {
                "Authorization": f"Token {baserow_token}",
                "Content-Type": "application/json"
            }

        curated_table_id = None

        # 1. Determine curated table ID
        if is_admin_mode and baserow_db_id:
            tables_url = f"{baserow_url}/api/database/tables/database/{baserow_db_id}/"
            try:
                res = requests.get(tables_url, headers=headers, timeout=10)
                res.raise_for_status()
                tables = res.json()
                for t in tables:
                    if t['name'] == 'exercises_curated':
                        curated_table_id = t['id']
                        break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to query Baserow tables list: {e}"))

        # Fallback to direct environment variable or guess
        if not curated_table_id:
            if baserow_table_id:
                curated_table_id = baserow_table_id
            else:
                curated_table_id = 322
                self.stdout.write(self.style.WARNING(f"Using default table ID: {curated_table_id}"))

        self.stdout.write(f"Fetching published exercises from Baserow table ID {curated_table_id}...")

        # 2. Fetch all published rows
        rows_url = f"{baserow_url}/api/database/rows/table/{curated_table_id}/?user_field_names=true&size=200"
        published_exercises = []

        while rows_url:
            try:
                res = requests.get(rows_url, headers=headers, timeout=15)
                res.raise_for_status()
                data = res.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to fetch rows from Baserow: {e}"))
                return

            for row in data.get('results', []):
                if row.get('Is Published') is True:
                    published_exercises.append(row)

            rows_url = data.get('next')

        self.stdout.write(f"Found {len(published_exercises)} published exercises in Baserow. Syncing to local SQLite and downloading media...")

        # Prepare local media directories
        media_dir = os.path.join(settings.MEDIA_ROOT, 'exercises')
        os.makedirs(media_dir, exist_ok=True)

        # Get or create Calisthenics category
        category, _ = ExerciseCategory.objects.get_or_create(name='Calisthenics')

        # Get or create Body weight equipment
        bodyweight_eq, _ = Equipment.objects.get_or_create(name='Body weight')

        # Get default license for wger (required fields)
        default_license = License.objects.first()

        # Get English language
        english_lang = Language.objects.get(short_name='en')

        sync_count = 0
        for row in published_exercises:
            name = row.get('Nome') or row.get('Name') or row.get(primary_field_name)
            source_id = row.get('Source Exercise ID')
            if not name or not source_id:
                continue

            slug = f"{slugify(name)}-{source_id}"
            
            # Download Demo Media URL locally if it is set and is an external URL
            external_media_url = row.get('Demo Media URL')
            local_media_url = ''

            if external_media_url and external_media_url.startswith('http'):
                ext = 'gif'
                if '.' in external_media_url.split('/')[-1]:
                    possible_ext = external_media_url.split('/')[-1].split('.')[-1].lower()
                    if possible_ext in ['gif', 'mp4', 'png', 'jpg', 'jpeg']:
                        ext = possible_ext
                
                filename = f"{source_id}.{ext}"
                local_file_path = os.path.join(media_dir, filename)
                local_media_url = f"{settings.MEDIA_URL}exercises/{filename}"

                # Download only if it doesn't already exist locally
                if not os.path.exists(local_file_path):
                    self.stdout.write(f"  Downloading GIF for '{name}'...")
                    try:
                        r = requests.get(external_media_url, timeout=20)
                        r.raise_for_status()
                        with open(local_file_path, 'wb') as f:
                            f.write(r.content)
                        self.stdout.write(self.style.SUCCESS(f"    Saved media locally to {local_media_url}"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"    Failed to download GIF: {e}"))
                        local_media_url = external_media_url
            else:
                local_media_url = external_media_url or ''

            instructions_raw = row.get('Instructions') or ''
            instructions_list = [line.strip() for line in instructions_raw.split('\n') if line.strip()]

            secondary_raw = row.get('Secondary Muscles') or ''
            secondary_list = [m.strip() for m in secondary_raw.split(',') if m.strip()]

            # 1. Update/Create CalisthenicsExercise record
            exercise, created = CalisthenicsExercise.objects.update_or_create(
                source='exercisedb',
                source_exercise_id=source_id,
                defaults={
                    'slug': slug,
                    'name': name,
                    'description': row.get('Description'),
                    'instructions': instructions_list,
                    'body_part': row.get('Body Part'),
                    'target_muscle': row.get('Target Muscle'),
                    'secondary_muscles': secondary_list,
                    'equipment': row.get('Equipment') or 'body weight',
                    'difficulty': row.get('Difficulty'),
                    'discipline': row.get('Discipline') or 'calisthenics',
                    'skill_family': row.get('Skill Family') or 'other',
                    'movement_pattern': row.get('Movement Pattern') or 'other',
                    'is_static_hold': bool(row.get('Is Static Hold')),
                    'is_unilateral': bool(row.get('Is Unilateral')),
                    'is_compound': not bool(row.get('Is Static Hold')),
                    'is_published': True,
                    'demo_media_url': local_media_url
                }
            )

            # 2. Update/Create wger native models for routine visibility
            # Create/update base wger Exercise record linked by UUID
            base_exercise, base_created = Exercise.objects.update_or_create(
                uuid=exercise.id,
                defaults={
                    'category': category,
                    'license': default_license,
                }
            )

            # Associate native equipment
            base_exercise.equipment.add(bodyweight_eq)

            # Associate native muscles
            if exercise.target_muscle:
                muscle_name = exercise.target_muscle.strip().capitalize()
                muscle, _ = Muscle.objects.get_or_create(
                    name=muscle_name,
                    defaults={'name_en': exercise.target_muscle.strip(), 'is_front': True}
                )
                base_exercise.muscles.add(muscle)

            for sm in secondary_list:
                if sm.strip():
                    muscle_sec_name = sm.strip().capitalize()
                    muscle_sec, _ = Muscle.objects.get_or_create(
                        name=muscle_sec_name,
                        defaults={'name_en': sm.strip(), 'is_front': True}
                    )
                    base_exercise.muscles_secondary.add(muscle_sec)

            # Create/update Translation (English)
            description_text = "\n".join(instructions_list)
            Translation.objects.update_or_create(
                exercise=base_exercise,
                language=english_lang,
                defaults={
                    'name': name,
                    'description': description_text,
                    'license': default_license,
                }
            )

            # Associate native ExerciseImage for local GIF rendering in wger
            if local_media_url and local_media_url.startswith(settings.MEDIA_URL):
                relative_image_path = local_media_url.replace(settings.MEDIA_URL, '')
                full_local_path = os.path.join(settings.MEDIA_ROOT, relative_image_path)
                if os.path.exists(full_local_path):
                    ExerciseImage.objects.update_or_create(
                        exercise=base_exercise,
                        image=relative_image_path,
                        defaults={
                            'is_main': True,
                            'license': default_license,
                        }
                    )

            # Re-generate tags based on Baserow values
            ExerciseTag.objects.filter(exercise=exercise).delete()
            tags = ['bodyweight', 'calisthenics']
            
            if row.get('Difficulty'):
                tags.append(row.get('Difficulty'))
            if row.get('Is Static Hold'):
                tags.append('static-hold')
            else:
                tags.append('reps')
            
            sf = (row.get('Skill Family') or '').lower()
            if sf in ['push_up', 'dip']:
                tags.append('push')
            elif sf == 'pull_up' or 'row' in name.lower():
                tags.append('pull')
            elif sf == 'squat':
                tags.append('legs')
            
            pattern = (row.get('Movement Pattern') or '').lower()
            if 'core' in pattern:
                tags.append('core')

            for t in tags:
                ExerciseTag.objects.get_or_create(exercise=exercise, tag=t)

            sync_count += 1
            self.stdout.write(f"- Curated and synced '{name}' (and synced natively to wger)")

        # Mark other exercises as unpublished
        synced_source_ids = [row.get('Source Exercise ID') for row in published_exercises]
        removed_count = CalisthenicsExercise.objects.exclude(source_exercise_id__in=synced_source_ids).update(is_published=False)
        if removed_count:
            self.stdout.write(self.style.WARNING(f"Marked {removed_count} local exercises as unpublished."))

        from wger.manager.services.exercise_catalog import bump_catalog_version
        new_ver = bump_catalog_version()

        self.stdout.write(
            self.style.SUCCESS(
                f"Sync completed successfully. Synced {sync_count} exercises and saved their media locally! Catalog cache bumped to {new_ver}."
            )
        )

