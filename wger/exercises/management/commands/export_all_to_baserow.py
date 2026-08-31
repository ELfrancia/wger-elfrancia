# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from django.conf import settings
import requests
import os

from wger.exercises.models import Exercise, CalisthenicsExercise, ExerciseVideo, ExerciseImage

class Command(BaseCommand):
    help = 'Export/Sync all local Django exercises (1114 total) into self-hosted local Baserow'

    def handle(self, *args, **options):
        baserow_url = os.environ.get('BASEROW_URL', 'http://localhost:8080').rstrip('/')
        baserow_email = os.environ.get('BASEROW_EMAIL')
        baserow_password = os.environ.get('BASEROW_PASSWORD')
        table_id = os.environ.get('BASEROW_TABLE_ID')

        if not baserow_email or not baserow_password:
            raise CommandError("BASEROW_EMAIL and BASEROW_PASSWORD environment variables must be set.")
        if not table_id:
            raise CommandError("BASEROW_TABLE_ID environment variable must be set.")

        self.stdout.write(f"Authenticating with local Baserow at {baserow_url} as {baserow_email}...")
        
        auth_url = f"{baserow_url}/api/user/token-auth/"
        try:
            res = requests.post(auth_url, json={"username": baserow_email, "password": baserow_password}, timeout=10)
            res.raise_for_status()
            jwt_token = res.json()["token"]
            headers = {
                "Authorization": f"JWT {jwt_token}",
                "Content-Type": "application/json"
            }
            self.stdout.write(self.style.SUCCESS("Authenticated successfully with Baserow!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to authenticate with Baserow: {e}"))
            return

        # Fetch existing rows in Baserow table 322 to prevent duplicates
        self.stdout.write(f"Fetching existing rows from Baserow Table {table_id}...")
        existing_rows_url = f"{baserow_url}/api/database/rows/table/{table_id}/?user_field_names=true&size=200"
        existing_source_ids = set()

        while existing_rows_url:
            try:
                r = requests.get(existing_rows_url, headers=headers, timeout=15)
                r.raise_for_status()
                data = r.json()
                for row in data.get('results', []):
                    src_id = row.get('Source Exercise ID')
                    if src_id:
                        existing_source_ids.add(str(src_id))
                existing_rows_url = data.get('next')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error fetching existing rows: {e}"))
                break

        self.stdout.write(f"Found {len(existing_source_ids)} existing exercises in Baserow.")

        # Build payload of exercises to export
        items_to_create = []

        # 1. Calisthenics Exercises (146 total)
        for c in CalisthenicsExercise.objects.all():
            src_id = str(c.source_exercise_id or c.id)
            if src_id in existing_source_ids:
                continue

            instr = c.instructions
            if isinstance(instr, list):
                instr_text = "\n".join(instr)
            else:
                instr_text = str(instr or '')

            sec_muscles = c.secondary_muscles
            if isinstance(sec_muscles, list):
                sec_text = ", ".join(sec_muscles)
            else:
                sec_text = str(sec_muscles or '')

            media_url = c.demo_media_url or ''
            if media_url.startswith('/'):
                media_url = f"http://localhost:8000{media_url}"

            items_to_create.append({
                "Nome": c.name,
                "Source Exercise ID": src_id,
                "Slug": c.slug or slugify(c.name),
                "Instructions": instr_text,
                "Body Part": c.body_part or 'other',
                "Target Muscle": c.target_muscle or 'other',
                "Secondary Muscles": sec_text,
                "Equipment": c.equipment or 'body weight',
                "Difficulty": c.difficulty or 'intermediate',
                "Discipline": c.discipline or 'calisthenics',
                "Skill Family": c.skill_family or 'other',
                "Movement Pattern": c.movement_pattern or 'other',
                "Is Static Hold": bool(c.is_static_hold),
                "Is Unilateral": bool(c.is_unilateral),
                "Is Published": True,
                "Attivo": True,
                "Demo Media URL": media_url if media_url.startswith('http') else None
            })

        # 2. Native Wger Exercises (968 total)
        for e in Exercise.objects.prefetch_related('muscles', 'muscles_secondary', 'equipment', 'category').all():
            src_id = f"wger-{e.id}"
            if src_id in existing_source_ids:
                continue

            translation = e.get_translation()
            name = translation.name if translation else f"Exercise {e.id}"
            instructions = translation.description if translation else ''

            category_name = e.category.name if e.category else 'other'
            primary_muscles = ", ".join([m.name_en or m.name for m in e.muscles.all()]) or 'other'
            secondary_muscles = ", ".join([m.name_en or m.name for m in e.muscles_secondary.all()])
            equipment_list = ", ".join([eq.name for eq in e.equipment.all()]) or 'body weight'

            video_obj = ExerciseVideo.objects.filter(exercise=e).first()
            image_obj = ExerciseImage.objects.filter(exercise=e).first()

            media_url = ''
            if video_obj and video_obj.video:
                media_url = video_obj.video.url
            elif image_obj and image_obj.image:
                media_url = image_obj.image.url
            
            if media_url.startswith('/'):
                media_url = f"http://localhost:8000{media_url}"

            items_to_create.append({
                "Nome": name,
                "Source Exercise ID": src_id,
                "Slug": f"{slugify(name)}-{e.id}",
                "Instructions": instructions or '',
                "Body Part": category_name,
                "Target Muscle": primary_muscles,
                "Secondary Muscles": secondary_muscles,
                "Equipment": equipment_list,
                "Difficulty": 'intermediate',
                "Discipline": 'bodybuilding',
                "Skill Family": 'other',
                "Movement Pattern": 'other',
                "Is Static Hold": False,
                "Is Unilateral": False,
                "Is Published": True,
                "Attivo": True,
                "Demo Media URL": media_url if media_url.startswith('http') else None
            })

        self.stdout.write(f"Prepared {len(items_to_create)} new exercises to export to Baserow.")

        if not items_to_create:
            self.stdout.write(self.style.SUCCESS("All exercises are already synchronized with Baserow!"))
            return

        # Batch push to Baserow (chunk size 100)
        batch_url = f"{baserow_url}/api/database/rows/table/{table_id}/batch/?user_field_names=true"
        chunk_size = 100
        pushed_count = 0

        for i in range(0, len(items_to_create), chunk_size):
            chunk = items_to_create[i:i + chunk_size]
            try:
                res = requests.post(batch_url, json={"items": chunk}, headers=headers, timeout=30)
                res.raise_for_status()
                pushed_count += len(chunk)
                self.stdout.write(f"  [{pushed_count}/{len(items_to_create)}] Pushed batch to Baserow...")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error pushing batch {i}: {e}. Retrying row-by-row..."))
                # Fallback row-by-row if batch fails
                row_url = f"{baserow_url}/api/database/rows/table/{table_id}/?user_field_names=true"
                for item in chunk:
                    try:
                        r = requests.post(row_url, json=item, headers=headers, timeout=10)
                        if r.status_code in (200, 201):
                            pushed_count += 1
                    except Exception:
                        pass

        self.stdout.write(self.style.SUCCESS(f"✨ Successfully exported {pushed_count} exercises to Baserow Table {table_id}!"))
