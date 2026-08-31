import os
import sys
import re
import requests

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.local_dev')

import django
django.setup()

from django.conf import settings
from wger.exercises.models import Exercise, CalisthenicsExercise
from wger.exercises.media_utils import safe_download_file, is_safe_path, sanitize_filename

def clean(text):
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())

def run():
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = 'https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/data/exercises.json'
    print('Loading ExerciseDB dataset...')
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print('Failed to load ExerciseDB dataset!')
        return

    edb_data = resp.json()
    print(f'Loaded {len(edb_data)} ExerciseDB items.')

    # A GIF may only be assigned to a one-to-one canonical-name match. The
    # previous fuzzy matcher accepted weak similarities and caused mismatches.
    edb_by_name = {}
    for item in edb_data:
        name_clean = clean(item.get('name'))
        if not name_clean:
            continue
        edb_by_name.setdefault(name_clean, []).append({
            'raw': item,
            'clean': name_clean,
            'gif_url': item.get('gif_url')
        })

    media_dir = os.path.join(settings.MEDIA_ROOT, 'exercises')
    os.makedirs(media_dir, exist_ok=True)
    existing_exercises = list(Exercise.objects.all())
    print(f'Matching ExerciseDB GIFs for {len(existing_exercises)} existing exercises...')

    assigned_count = 0
    skipped_has_video = 0
    already_had_gif = 0

    for idx, ex in enumerate(existing_exercises, 1):
        # 1. Check if exercise already has a valid official video on disk
        main_v = ex.main_video
        if main_v and main_v.video:
            try:
                storage = main_v.video.storage
                if hasattr(main_v.video, 'name') and main_v.video.name and storage.exists(main_v.video.name):
                    skipped_has_video += 1
                    continue
            except Exception:
                pass

        # 2. Gather names to match
        names = []
        for lang in ['en', 'it']:
            t = ex.get_translation(lang)
            if t and t.name:
                names.append(t.name)

        if not names:
            continue

        for n in names:
            c_name = clean(n)
            candidates = edb_by_name.get(c_name, [])
            if len(candidates) == 1:
                best_match = candidates[0]
                break
        else:
            best_match = None

        if best_match:
            gif_rel = best_match['gif_url']
            if gif_rel:
                safe_ex_id = sanitize_filename(str(ex.id))
                gif_filename = f'matched_{safe_ex_id}.gif'
                local_gif_path = os.path.join(media_dir, gif_filename)
                if not is_safe_path(media_dir, local_gif_path):
                    continue
                rel_url = f'{settings.MEDIA_URL}exercises/{gif_filename}'

                # Download GIF if missing
                if not os.path.exists(local_gif_path):
                    remote_gif_url = f'https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/{gif_rel}'
                    safe_download_file(remote_gif_url, local_gif_path, base_dir=media_dir, timeout=10, headers=headers)

                if os.path.exists(local_gif_path):
                    cal, _ = CalisthenicsExercise.objects.update_or_create(
                        id=str(ex.uuid),
                        defaults={
                            'name': names[0],
                            'slug': f'ex-{ex.id}',
                            'demo_media_url': rel_url,
                            'source': 'ExerciseDB-Matched'
                        }
                    )
                    assigned_count += 1

        if idx % 100 == 0 or idx == len(existing_exercises):
            print(f'[{idx}/{len(existing_exercises)}] Assigned ExerciseDB GIFs: {assigned_count} (Official videos kept: {skipped_has_video})')

    print(f'\nSUMMARY:')
    print(f'Total Existing Exercises: {len(existing_exercises)}')
    print(f'Kept Official MP4/MOV Videos: {skipped_has_video}')
    print(f'Assigned ExerciseDB GIFs: {assigned_count}')

if __name__ == '__main__':
    run()
