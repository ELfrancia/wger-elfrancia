import os
import sys
import uuid
import re
import requests
from django.utils.text import slugify

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.local_dev')

import django
django.setup()

from django.conf import settings
from wger.exercises.models import CalisthenicsExercise, Exercise, Translation, ExerciseCategory, Muscle, Equipment
from wger.core.models import Language
from wger.core.models.license import License
from wger.exercises.media_utils import safe_download_file, is_safe_path, sanitize_filename

def import_all():
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = 'https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/data/exercises.json'
    print('Fetching ExerciseDB JSON dataset from GitHub...')
    
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f'Failed to fetch dataset: HTTP {resp.status_code}')
        return
        
    dataset = resp.json()
    print(f'Retrieved {len(dataset)} exercises from ExerciseDB!')
    
    media_dir = os.path.join(settings.MEDIA_ROOT, 'exercises')
    os.makedirs(media_dir, exist_ok=True)
    default_license = License.objects.first()
    lang_en, _ = Language.objects.get_or_create(short_name='en', defaults={'full_name': 'English', 'full_name_en': 'English'})
    lang_it, _ = Language.objects.get_or_create(short_name='it', defaults={'full_name': 'Italiano', 'full_name_en': 'Italian'})

    success_count = 0
    total = len(dataset)
    
    for idx, item in enumerate(dataset, 1):
        raw_id = str(item.get('id', str(idx)))
        safe_raw_id = sanitize_filename(raw_id)
        if not safe_raw_id:
            safe_raw_id = str(idx)
        ex_string_id = f'edb-{safe_raw_id}'
        ex_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, ex_string_id)
        
        name = item.get('name', 'Exercise').title()
        
        category_name = (item.get('category') or item.get('target') or item.get('muscle_group') or 'Bodybuilding').capitalize()
        target_m = item.get('target') or ''
        eq_name = item.get('equipment') or 'Bodyweight'
        instructions = item.get('instructions') or []
        
        gif_filename = f'{ex_string_id}.gif'
        gif_local_path = os.path.join(media_dir, gif_filename)
        if not is_safe_path(media_dir, gif_local_path):
            continue
        gif_rel_url = f'{settings.MEDIA_URL}exercises/{gif_filename}'
        
        # Download GIF asset if not present locally
        if item.get('gif_url') and not os.path.exists(gif_local_path):
            remote_gif_url = f'https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/{item["gif_url"]}'
            safe_download_file(remote_gif_url, gif_local_path, base_dir=media_dir, timeout=10, headers=headers)

        # Unique slug per exercise
        slug_val = slugify(f'{name}-{raw_id}')[:50]
        
        # 1. Update/Create CalisthenicsExercise entry
        cal, _ = CalisthenicsExercise.objects.update_or_create(
            id=str(ex_uuid),
            defaults={
                'name': name,
                'slug': slug_val,
                'instructions': instructions,
                'target_muscle': target_m,
                'secondary_muscles': item.get('secondary_muscles') or [],
                'equipment': eq_name,
                'category': category_name,
                'demo_media_url': gif_rel_url if os.path.exists(gif_local_path) else '',
                'source': 'ExerciseDB'
            }
        )

        # 2. Sync to Exercise & Translation DB tables
        cat_obj, _ = ExerciseCategory.objects.get_or_create(name=category_name)
        ex_obj, _ = Exercise.objects.get_or_create(
            uuid=ex_uuid,
            defaults={'category': cat_obj, 'license': default_license}
        )
        ex_obj.category = cat_obj
        ex_obj.save()
        
        desc_text = ' '.join(instructions) if isinstance(instructions, list) else str(instructions)
        
        # English translation
        Translation.objects.update_or_create(
            exercise=ex_obj,
            language=lang_en,
            defaults={
                'name': name,
                'description': desc_text,
                'license': default_license
            }
        )

        # Italian translation
        Translation.objects.update_or_create(
            exercise=ex_obj,
            language=lang_it,
            defaults={
                'name': name,
                'description': desc_text,
                'license': default_license
            }
        )

        # Equipment mapping
        if eq_name:
            eq_obj = Equipment.objects.filter(name__iexact=eq_name).first()
            if not eq_obj:
                eq_obj = Equipment.objects.create(name=eq_name.capitalize())
            ex_obj.equipment.add(eq_obj)

        # Muscle mapping
        if target_m:
            m_obj = Muscle.objects.filter(name__iexact=target_m).first()
            if not m_obj:
                m_obj = Muscle.objects.create(name=target_m.capitalize(), name_en=target_m, is_front=True)
            ex_obj.muscles.add(m_obj)

        success_count += 1
        if idx % 100 == 0 or idx == total:
            print(f'[{idx}/{total}] Processed: {name} (Total synced: {success_count})')

    print(f'\nFinished importing all {success_count} ExerciseDB exercises into database!')

if __name__ == '__main__':
    import_all()
