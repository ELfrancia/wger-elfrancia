# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from django.utils.text import slugify
import requests
import datetime
import os
from wger.exercises.models import ExerciseImportRaw, CalisthenicsExercise, ExerciseTag

class Command(BaseCommand):
    help = 'Fetch calisthenics exercises and push them to Baserow or import locally to SQLite'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=1000, help='Limit results fetched')
        parser.add_argument('--local-only', action='store_true', help='Force local SQLite import, ignore Baserow')

    def handle(self, *args, **options):
        import_batch = datetime.datetime.now().strftime('%Y-%m-%d-%H%M')
        api_key = os.environ.get('EXERCISEDB_API_KEY')
        
        # Baserow configuration
        baserow_url = os.environ.get('BASEROW_URL', 'http://localhost:8080').rstrip('/')
        baserow_email = os.environ.get('BASEROW_EMAIL')
        baserow_password = os.environ.get('BASEROW_PASSWORD')
        baserow_token = os.environ.get('BASEROW_TOKEN')
        baserow_db_id = os.environ.get('BASEROW_DB_ID')

        # Whitelist keywords for calisthenics exercises
        whitelist = [
            'push-up', 'pushup', 'dip', 'pull-up', 'pullup', 'chin-up', 'chinup',
            'muscle-up', 'muscleup', 'l-sit', 'lsit', 'v-sit', 'vsit', 'plank',
            'handstand', 'hollow body', 'hollowbody', 'front lever', 'frontlever',
            'back lever', 'backlever', 'planche', 'squat', 'pistol', 'shrimp',
            'burpee', 'leg raise', 'legraise', 'mountain climber', 'hanging knee',
            'dragon flag', 'lunge', 'hollow hold', 'human flag', 'arch body'
        ]

        # Blacklist keywords to exclude non-calisthenics/rehab movements
        blacklist = [
            'weighted', 'dumbell', 'barbell', 'kettlebell', 'medicine ball', 'band', 
            'cable', 'machine', 'stretching', 'yoga', 'foam roller', 'ball'
        ]

        # 1. Fetching data
        response_data = []
        if api_key:
            self.stdout.write("Fetching body weight exercises from ExerciseDB RapidAPI...")
            url = "https://exercisedb.p.rapidapi.com/exercises/equipment/body%20weight"
            headers = {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": "exercisedb.p.rapidapi.com"
            }
            params = {"limit": options['limit']}
            try:
                response = requests.get(url, headers=headers, params=params, timeout=20)
                response.raise_for_status()
                response_data = response.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error fetching from ExerciseDB API: {e}"))
                return
        else:
            self.stdout.write("No EXERCISEDB_API_KEY environment variable found. Downloading full public ExerciseDB JSON backup...")
            backup_url = "https://raw.githubusercontent.com/Webbanditten/exercisedb-api/main/src/data/exercises.json"
            try:
                response = requests.get(backup_url, timeout=25)
                response.raise_for_status()
                response_data = response.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error downloading public ExerciseDB backup: {e}"))
                return

        # 2. Filtering & Heuristics Processing
        processed_exercises = []
        raw_staging_count = 0

        for item in response_data:
            # Handle schema differences between RapidAPI and GitHub backup
            equipments = item.get('equipments', [])
            equipment_single = item.get('equipment', '')
            is_bodyweight = False
            if equipment_single and 'body weight' in equipment_single.lower():
                is_bodyweight = True
            elif any('body weight' in eq.lower() for eq in equipments):
                is_bodyweight = True

            if not is_bodyweight:
                continue

            name_lower = item['name'].lower()

            # Apply blacklist
            if any(bl in name_lower for bl in blacklist):
                continue

            # Apply whitelist keyword matching
            if not any(wl in name_lower for wl in whitelist):
                continue

            # Normalized fields
            eid = item.get('exerciseId') or item.get('id')
            if not eid:
                continue

            slug = slugify(item['name'])
            
            # Static Hold detection
            is_static = any(kw in name_lower for kw in ['plank', 'hold', 'lever', 'sit', 'stand', 'flag'])
            
            # Unilateral detection
            is_unilateral = any(kw in name_lower for kw in ['one-arm', 'single-leg', 'pistol', 'shrimp', 'archer', 'one arm', 'single leg'])
            
            # Difficulty mapping
            difficulty = 'intermediate'
            if any(kw in name_lower for kw in ['assisted', 'kneeling', 'incline', 'bench', 'support', 'wall']):
                difficulty = 'beginner'
            elif any(kw in name_lower for kw in ['one-arm', 'one arm', 'single-arm', 'lever', 'planche', 'muscle-up', 'muscleup', 'flag', 'impossible']):
                difficulty = 'advanced'

            # Skill Family detection
            skill_family = 'other'
            if 'push-up' in name_lower or 'pushup' in name_lower:
                skill_family = 'push_up'
            elif 'pull-up' in name_lower or 'pullup' in name_lower or 'chin-up' in name_lower or 'chinup' in name_lower:
                skill_family = 'pull_up'
            elif 'dip' in name_lower:
                skill_family = 'dip'
            elif 'handstand' in name_lower:
                skill_family = 'handstand'
            elif 'front lever' in name_lower or 'frontlever' in name_lower:
                skill_family = 'front_lever'
            elif 'back lever' in name_lower or 'backlever' in name_lower:
                skill_family = 'back_lever'
            elif 'l-sit' in name_lower or 'lsit' in name_lower:
                skill_family = 'l_sit'
            elif 'planche' in name_lower:
                skill_family = 'planche'
            elif 'squat' in name_lower:
                skill_family = 'squat'

            # Movement pattern
            pattern = 'other'
            if skill_family in ['push_up', 'dip']:
                pattern = 'horizontal_push' if 'push-up' in name_lower else 'vertical_push'
            elif skill_family == 'pull_up':
                pattern = 'vertical_pull'
            elif 'row' in name_lower:
                pattern = 'horizontal_pull'
            elif skill_family == 'squat' or 'lunge' in name_lower:
                pattern = 'legs_quads'
            elif 'plank' in name_lower or 'raise' in name_lower or 'sit' in name_lower or 'hollow' in name_lower:
                pattern = 'core_flexion' if 'raise' in name_lower else 'core_isometric'

            # Parse muscles and bodyparts arrays
            body_parts_list = item.get('bodyParts', [])
            body_part = item.get('bodyPart') or (body_parts_list[0] if body_parts_list else 'other')

            target_muscles_list = item.get('targetMuscles', [])
            target_muscle = item.get('target') or (target_muscles_list[0] if target_muscles_list else 'other')

            secondary_muscles = item.get('secondaryMuscles', [])

            # Instructions (clean steps)
            instructions_raw = item.get('instructions', [])
            instructions_clean = []
            for inst in instructions_raw:
                if inst.lower().startswith('step'):
                    parts = inst.split(' ', 1)
                    if len(parts) > 1:
                        clean_inst = parts[1].lstrip('0123456789:.- ')
                        instructions_clean.append(clean_inst)
                    else:
                        instructions_clean.append(inst)
                else:
                    instructions_clean.append(inst)

            gif_url = item.get('gifUrl', '')
            media_dir = os.path.join(os.getcwd(), 'media', 'exercises')
            os.makedirs(media_dir, exist_ok=True)

            local_filename = f"{eid}.gif"
            local_file_path = os.path.join(media_dir, local_filename)

            if gif_url and not os.path.exists(local_file_path):
                try:
                    res = requests.get(gif_url, timeout=10)
                    if res.status_code == 200 and len(res.content) > 1000:
                        with open(local_file_path, 'wb') as f:
                            f.write(res.content)
                except Exception:
                    pass

            if os.path.exists(local_file_path):
                demo_media_url = f'/media/exercises/{local_filename}'
            else:
                fallback_map = {
                    'push_up': '/media/exercises/x6KpKpq.gif',
                    'pull_up': '/media/exercises/4GqRrAk.gif',
                    'dip': '/media/exercises/LQFOrMn.gif',
                    'handstand': '/media/exercises/XooAdhl.gif',
                    'l_sit': '/media/exercises/5VXmnV5.gif',
                    'squat': '/media/exercises/05Cf2v8.gif',
                }
                demo_media_url = fallback_map.get(skill_family, '/media/exercises/4GqRrAk.gif')

            processed_exercises.append({
                'source_exercise_id': eid,
                'name': item['name'],
                'slug': slug,
                'instructions': "\n".join(instructions_clean),
                'body_part': body_part,
                'target_muscle': target_muscle,
                'secondary_muscles': ", ".join(secondary_muscles),
                'equipment': 'body weight',
                'difficulty': difficulty,
                'discipline': 'calisthenics',
                'skill_family': skill_family,
                'movement_pattern': pattern,
                'is_static_hold': is_static,
                'is_unilateral': is_unilateral,
                'is_compound': not is_static,
                'demo_media_url': demo_media_url,
                'raw_payload': item
            })

        # 3. Determine target: Baserow or Local SQLite
        use_baserow = (baserow_email and baserow_password) or (baserow_token)
        use_baserow = use_baserow and baserow_db_id and not options['local_only']

        if use_baserow:
            self.stdout.write(self.style.WARNING(f"Pushing to self-hosted Baserow at {baserow_url}..."))
            self.push_to_baserow(baserow_url, baserow_email, baserow_password, baserow_token, baserow_db_id, processed_exercises, import_batch)
        else:
            self.stdout.write(self.style.WARNING("Running import directly into local SQLite database..."))
            self.import_locally(processed_exercises, import_batch)

    def import_locally(self, exercises, import_batch):
        raw_count = 0
        promoted_count = 0

        for ex in exercises:
            ExerciseImportRaw.objects.update_or_create(
                source='exercisedb',
                source_exercise_id=ex['source_exercise_id'],
                defaults={
                    'payload': ex['raw_payload'],
                    'import_batch': import_batch
                }
            )
            raw_count += 1

            exercise, created = CalisthenicsExercise.objects.update_or_create(
                source='exercisedb',
                source_exercise_id=ex['source_exercise_id'],
                defaults={
                    'slug': ex['slug'],
                    'name': ex['name'],
                    'instructions': ex['instructions'].split('\n'),
                    'body_part': ex['body_part'],
                    'target_muscle': ex['target_muscle'],
                    'secondary_muscles': ex['secondary_muscles'].split(', ') if ex['secondary_muscles'] else [],
                    'equipment': ex['equipment'],
                    'difficulty': ex['difficulty'],
                    'discipline': ex['discipline'],
                    'skill_family': ex['skill_family'],
                    'movement_pattern': ex['movement_pattern'],
                    'is_static_hold': ex['is_static_hold'],
                    'is_unilateral': ex['is_unilateral'],
                    'is_compound': ex['is_compound'],
                    'demo_media_url': ex['demo_media_url']
                }
            )
            promoted_count += 1

            tags = ['bodyweight', 'calisthenics', ex['difficulty']]
            if ex['is_static_hold']:
                tags.append('static-hold')
            else:
                tags.append('reps')
            
            if ex['skill_family'] in ['push_up', 'dip']:
                tags.append('push')
            elif ex['skill_family'] == 'pull_up' or 'row' in ex['name'].lower():
                tags.append('pull')
            elif ex['skill_family'] == 'squat':
                tags.append('legs')
            elif 'core' in ex['movement_pattern']:
                tags.append('core')

            for t in tags:
                ExerciseTag.objects.get_or_create(exercise=exercise, tag=t)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully completed local import: Staged {raw_count} raw payloads, created/updated {promoted_count} calisthenics exercises."
            )
        )

    def push_to_baserow(self, url, email, password, token, db_id, exercises, import_batch):
        headers = {}
        is_admin_mode = False

        if email and password:
            self.stdout.write("Obtaining JWT admin token from Baserow...")
            auth_url = f"{url}/api/user/token-auth/"
            try:
                res = requests.post(auth_url, json={"username": email, "password": password}, timeout=10)
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

        if not is_admin_mode:
            if not token:
                self.stdout.write(self.style.ERROR("Error: No valid API Token or Admin credentials provided."))
                return
            headers = {
                "Authorization": f"Token {token}",
                "Content-Type": "application/json"
            }

        raw_table_id = None
        curated_table_id = None

        if is_admin_mode:
            tables_url = f"{url}/api/database/tables/database/{db_id}/"
            try:
                res = requests.get(tables_url, headers=headers, timeout=10)
                res.raise_for_status()
                tables = res.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to query Baserow tables: {e}"))
                return

            for t in tables:
                if t['name'] == 'exercises_raw':
                    raw_table_id = t['id']
                elif t['name'] == 'exercises_curated':
                    curated_table_id = t['id']

            if not raw_table_id:
                self.stdout.write("Creating 'exercises_raw' table in Baserow...")
                res = requests.post(tables_url, headers=headers, json={"name": "exercises_raw"}, timeout=10)
                res.raise_for_status()
                raw_table_id = res.json()['id']
                self.setup_raw_fields(url, headers, raw_table_id)

            if not curated_table_id:
                self.stdout.write("Creating 'exercises_curated' table in Baserow...")
                res = requests.post(tables_url, headers=headers, json={"name": "exercises_curated"}, timeout=10)
                res.raise_for_status()
                curated_table_id = res.json()['id']
                self.setup_curated_fields(url, headers, curated_table_id)

            self.ensure_fields_exist(url, headers, raw_table_id, 'raw')
            self.ensure_fields_exist(url, headers, curated_table_id, 'curated')
        else:
            curated_table_id = 322
            raw_table_id = None

        # Dynamically discover primary field name of 'exercises_curated'
        curated_primary_field = "Name"
        if curated_table_id:
            try:
                res = requests.get(f"{url}/api/database/fields/table/{curated_table_id}/", headers=headers, timeout=10)
                res.raise_for_status()
                for f in res.json():
                    if f.get('primary'):
                        curated_primary_field = f['name']
                        self.stdout.write(f"Detected curated table primary field: '{curated_primary_field}'")
                        break
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed to query field metadata: {e}. Defaulting to 'Name'"))

        # Fetch existing records
        existing_curated = {}
        if curated_table_id:
            self.stdout.write(f"Querying existing records from curated table (ID: {curated_table_id})...")
            next_url = f"{url}/api/database/rows/table/{curated_table_id}/?user_field_names=true&size=200"
            while next_url:
                try:
                    res = requests.get(next_url, headers=headers, timeout=15)
                    res.raise_for_status()
                    data = res.json()
                    for row in data.get('results', []):
                        eid = row.get('Source Exercise ID')
                        if eid:
                            existing_curated[eid] = row['id']
                    next_url = data.get('next')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to query curated rows: {e}"))
                    break

        existing_raw = {}
        if raw_table_id:
            self.stdout.write(f"Querying existing records from raw table (ID: {raw_table_id})...")
            next_url = f"{url}/api/database/rows/table/{raw_table_id}/?user_field_names=true&size=200"
            while next_url:
                try:
                    res = requests.get(next_url, headers=headers, timeout=15)
                    res.raise_for_status()
                    data = res.json()
                    for row in data.get('results', []):
                        eid = row.get('Source Exercise ID')
                        if eid:
                            existing_raw[eid] = row['id']
                    next_url = data.get('next')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to query raw rows: {e}"))
                    break

        # 3. Pushing rows
        staged_count = 0
        curated_count = 0

        for ex in exercises:
            # Push raw payload if raw table is set up
            if raw_table_id:
                raw_payload = {
                    "Source": "exercisedb",
                    "Source Exercise ID": ex['source_exercise_id'],
                    "Payload": str(ex['raw_payload']),
                    "Import Batch": import_batch
                }
                try:
                    if ex['source_exercise_id'] in existing_raw:
                        rid = existing_raw[ex['source_exercise_id']]
                        requests.patch(f"{url}/api/database/rows/table/{raw_table_id}/{rid}/?user_field_names=true", headers=headers, json=raw_payload, timeout=10)
                    else:
                        requests.post(f"{url}/api/database/rows/table/{raw_table_id}/?user_field_names=true", headers=headers, json=raw_payload, timeout=10)
                    staged_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to stage raw row: {e}"))

            # Push curated payload
            curated_payload = {
                curated_primary_field: ex['name'],
                "Source Exercise ID": ex['source_exercise_id'],
                "Slug": ex['slug'],
                "Instructions": ex['instructions'],
                "Body Part": ex['body_part'],
                "Target Muscle": ex['target_muscle'],
                "Secondary Muscles": ex['secondary_muscles'],
                "Equipment": ex['equipment'],
                "Difficulty": ex['difficulty'],
                "Discipline": ex['discipline'],
                "Skill Family": ex['skill_family'],
                "Movement Pattern": ex['movement_pattern'],
                "Is Static Hold": ex['is_static_hold'],
                "Is Unilateral": ex['is_unilateral'],
                "Is Published": True, # Automatically set to True since user wants all of them imported!
                "Demo Media URL": ex['demo_media_url']
            }

            if curated_table_id:
                try:
                    if ex['source_exercise_id'] in existing_curated:
                        rid = existing_curated[ex['source_exercise_id']]
                        requests.patch(f"{url}/api/database/rows/table/{curated_table_id}/{rid}/?user_field_names=true", headers=headers, json=curated_payload, timeout=10)
                    else:
                        requests.post(f"{url}/api/database/rows/table/{curated_table_id}/?user_field_names=true", headers=headers, json=curated_payload, timeout=10)
                    curated_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to push curated row to table {curated_table_id}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully completed: Populated {curated_count} exercises in Baserow table '{curated_table_id}' for manual curation."
            )
        )

    def setup_raw_fields(self, url, headers, table_id):
        fields = [
            {"name": "Source Exercise ID", "type": "text"},
            {"name": "Payload", "type": "long_text"},
            {"name": "Import Batch", "type": "text"}
        ]
        for f in fields:
            requests.post(f"{url}/api/database/fields/table/{table_id}/", headers=headers, json=f, timeout=5)

    def setup_curated_fields(self, url, headers, table_id):
        fields = [
            {"name": "Source Exercise ID", "type": "text"},
            {"name": "Slug", "type": "text"},
            {"name": "Instructions", "type": "long_text"},
            {"name": "Body Part", "type": "text"},
            {"name": "Target Muscle", "type": "text"},
            {"name": "Secondary Muscles", "type": "text"},
            {"name": "Equipment", "type": "text"},
            {"name": "Difficulty", "type": "text"},
            {"name": "Discipline", "type": "text"},
            {"name": "Skill Family", "type": "text"},
            {"name": "Movement Pattern", "type": "text"},
            {"name": "Is Static Hold", "type": "boolean"},
            {"name": "Is Unilateral", "type": "boolean"},
            {"name": "Is Published", "type": "boolean"},
            {"name": "Demo Media URL", "type": "url"}
        ]
        for f in fields:
            requests.post(f"{url}/api/database/fields/table/{table_id}/", headers=headers, json=f, timeout=5)

    def ensure_fields_exist(self, url, headers, table_id, table_type):
        res = requests.get(f"{url}/api/database/fields/table/{table_id}/", headers=headers, timeout=10)
        res.raise_for_status()
        existing_names = [f['name'] for f in res.json()]

        if table_type == 'raw':
            target_fields = [
                {"name": "Source Exercise ID", "type": "text"},
                {"name": "Payload", "type": "long_text"},
                {"name": "Import Batch", "type": "text"}
            ]
        else:
            target_fields = [
                {"name": "Source Exercise ID", "type": "text"},
                {"name": "Slug", "type": "text"},
                {"name": "Instructions", "type": "long_text"},
                {"name": "Body Part", "type": "text"},
                {"name": "Target Muscle", "type": "text"},
                {"name": "Secondary Muscles", "type": "text"},
                {"name": "Equipment", "type": "text"},
                {"name": "Difficulty", "type": "text"},
                {"name": "Discipline", "type": "text"},
                {"name": "Skill Family", "type": "text"},
                {"name": "Movement Pattern", "type": "text"},
                {"name": "Is Static Hold", "type": "boolean"},
                {"name": "Is Unilateral", "type": "boolean"},
                {"name": "Is Published", "type": "boolean"},
                {"name": "Demo Media URL", "type": "url"}
            ]

        for f in target_fields:
            if f['name'] not in existing_names:
                requests.post(f"{url}/api/database/fields/table/{table_id}/", headers=headers, json=f, timeout=5)
