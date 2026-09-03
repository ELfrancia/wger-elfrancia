"""
Django Management Command: assign_exercisedb_gifs_to_existing_exercises

Matches existing exercises in the database with hasaneyldrm/exercises-dataset.
Assigns static preview images (ExerciseImage with is_main=True) and animated demo media
(CalisthenicsExercise.demo_media_url) so previews are rendered in:
1) /it/exercise/overview/ (React overview card)
2) Scheda esercizio (/it/exercise/<id>/view)
3) Card esercizio during workout (exercise_card.html)

STRICT RULE: If an exercise has no match in the dataset, DO NOT assign any default or placeholder.
"""

import json
import logging
import os
import re
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from wger.core.models import Language
from wger.exercises.models import (
    Alias,
    CalisthenicsExercise,
    Exercise,
    ExerciseImage,
    Translation,
)
from wger.utils.cache import reset_exercise_api_cache
from wger.utils.models import License

logger = logging.getLogger(__name__)


def norm_word(w):
    w = (w or '').lower()
    if w.endswith('es') and len(w) > 4:
        w = w[:-2]
    elif w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        w = w[:-1]
    return w


def token_set(n):
    words = re.findall(r'[a-z0-9]+', (n or '').lower())
    return set(norm_word(w) for w in words)


def clean_name(n):
    return re.sub(r'[^a-z0-9]', '', (n or '').lower())


def sanitize_filename(filename):
    """
    Prevents path traversal and unsafe characters.
    """
    base = os.path.basename(filename)
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', base)


class Command(BaseCommand):
    help = "Assign ExerciseDB images and GIF animations to matching existing database exercises"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dataset-path',
            type=str,
            default='/app/exercises-dataset',
            help='Path to cloned exercises-dataset directory',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate matching without modifying DB or files',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing ExerciseImage/Calisthenics demo_media_url',
        )

    def handle(self, *args, **options):
        dataset_path = options['dataset_path']
        dry_run = options['dry_run']
        force = options['force']

        if not os.path.exists(dataset_path):
            alt_path = os.path.join(settings.BASE_DIR, 'exercises-dataset')
            if os.path.exists(alt_path):
                dataset_path = alt_path
            else:
                self.stderr.write(self.style.ERROR(f"Dataset path not found: {dataset_path}"))
                return

        json_file = os.path.join(dataset_path, 'data', 'exercises.json')
        if not os.path.exists(json_file):
            self.stderr.write(self.style.ERROR(f"exercises.json not found at: {json_file}"))
            return

        self.stdout.write(self.style.NOTICE(f"Loading dataset from {json_file}..."))
        with open(json_file, 'r', encoding='utf-8') as f:
            dataset = json.load(f)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(dataset)} items from dataset."))

        images_dir = os.path.join(dataset_path, 'images')
        videos_dir = os.path.join(dataset_path, 'videos')

        # Index dataset items
        dataset_by_clean = {}
        dataset_by_tokens = []
        for item in dataset:
            name = item.get('name') or ''
            c = clean_name(name)
            tokens = token_set(name)
            if c:
                dataset_by_clean[c] = item
            if tokens:
                dataset_by_tokens.append((tokens, item))

        # Index DB exercises with English and Italian names & aliases
        self.stdout.write(self.style.NOTICE("Indexing database exercises..."))
        ex_names = {}
        ex_by_id = {}
        for ex in Exercise.objects.all():
            ex_by_id[ex.id] = ex
            ex_names[ex.id] = []

        for t in Translation.objects.select_related('exercise').prefetch_related('alias_set').all():
            ex_id = t.exercise_id
            if ex_id in ex_names:
                if t.name:
                    ex_names[ex_id].append(t.name)
                for a in t.alias_set.all():
                    if a.alias:
                        ex_names[ex_id].append(a.alias)

        default_license = License.objects.filter(pk=1).first() or License.objects.first()

        media_exercises_dir = os.path.join(settings.MEDIA_ROOT, 'exercises')
        os.makedirs(media_exercises_dir, exist_ok=True)

        matched_count = 0
        images_created_count = 0
        gifs_assigned_count = 0
        instructions_updated_count = 0

        self.stdout.write(self.style.NOTICE("Matching exercises and assigning media..."))

        for ex_id, names in ex_names.items():
            ex = ex_by_id[ex_id]
            matched_item = None

            # 1. Exact cleaned name match
            for n in names:
                c = clean_name(n)
                if c in dataset_by_clean:
                    matched_item = dataset_by_clean[c]
                    break

            # 2. Token set match
            if not matched_item:
                for n in names:
                    tokens = token_set(n)
                    if not tokens or len(tokens) < 2:
                        continue
                    for d_tokens, item in dataset_by_tokens:
                        if tokens == d_tokens:
                            matched_item = item
                            break
                    if matched_item:
                        break

            # STRICT RULE: No match -> Skip completely! No placeholder!
            if not matched_item:
                continue

            matched_count += 1
            item_id = str(matched_item.get('id') or '')
            img_rel = matched_item.get('image') or ''
            gif_rel = matched_item.get('gif_url') or ''

            instructions_it = ""
            if isinstance(matched_item.get('instructions'), dict):
                instructions_it = matched_item['instructions'].get('it') or matched_item['instructions'].get('en') or ""
            elif isinstance(matched_item.get('instructions'), list):
                instructions_it = "\n".join(matched_item['instructions'])

            if dry_run:
                self.stdout.write(f"Matched ex #{ex.id} ('{names[0]}') -> '{matched_item.get('name')}'")
                continue

            with transaction.atomic():
                # --- A. Static preview image (ExerciseImage) ---
                has_main_image = ExerciseImage.objects.filter(exercise=ex, is_main=True).exists()
                if (not has_main_image or force) and img_rel:
                    src_img_path = os.path.join(dataset_path, img_rel)
                    if not os.path.exists(src_img_path):
                        src_img_path = os.path.join(images_dir, os.path.basename(img_rel))

                    if os.path.exists(src_img_path) and os.path.getsize(src_img_path) > 0:
                        safe_img_name = sanitize_filename(f"edb_{item_id}_{os.path.basename(img_rel)}")
                        rel_upload_path = f"exercise-images/{ex.id}/{safe_img_name}"
                        dest_img_path = os.path.join(settings.MEDIA_ROOT, 'exercise-images', str(ex.id))
                        os.makedirs(dest_img_path, exist_ok=True)
                        final_dest = os.path.join(dest_img_path, safe_img_name)

                        shutil.copyfile(src_img_path, final_dest)

                        if not has_main_image:
                            ExerciseImage.objects.create(
                                exercise=ex,
                                image=rel_upload_path,
                                is_main=True,
                                license=default_license,
                                license_author="hasaneyldrm/exercises-dataset",
                            )
                            images_created_count += 1
                        elif force:
                            img_obj = ExerciseImage.objects.filter(exercise=ex, is_main=True).first()
                            if img_obj:
                                img_obj.image = rel_upload_path
                                img_obj.save()
                                images_created_count += 1

                # --- B. Animated GIF demo (CalisthenicsExercise) ---
                if gif_rel:
                    src_gif_path = os.path.join(dataset_path, gif_rel)
                    if not os.path.exists(src_gif_path):
                        src_gif_path = os.path.join(videos_dir, os.path.basename(gif_rel))

                    if os.path.exists(src_gif_path) and os.path.getsize(src_gif_path) > 0:
                        safe_gif_name = sanitize_filename(f"edb_{item_id}_{os.path.basename(gif_rel)}")
                        dest_gif_path = os.path.join(media_exercises_dir, safe_gif_name)
                        if not os.path.exists(dest_gif_path) or force:
                            shutil.copyfile(src_gif_path, dest_gif_path)

                        rel_gif_url = f"/media/exercises/{safe_gif_name}"
                        cal_obj, created = CalisthenicsExercise.objects.update_or_create(
                            id=str(ex.uuid),
                            defaults={
                                'name': names[0] if names else matched_item.get('name'),
                                'slug': f"ex-{ex.id}",
                                'demo_media_url': rel_gif_url,
                                'description': instructions_it or '',
                                'source': 'hasaneyldrm/exercises-dataset',
                                'is_published': True,
                            }
                        )
                        gifs_assigned_count += 1

                # --- C. Italian translation instruction update ---
                if instructions_it:
                    it_lang = Language.objects.filter(short_name='it').first()
                    if it_lang:
                        t_it = Translation.objects.filter(exercise=ex, language=it_lang).first()
                        if t_it and (not t_it.description or len(t_it.description.strip()) < 20):
                            t_it.description = instructions_it
                            t_it.save()
                            instructions_updated_count += 1

                reset_exercise_api_cache(ex.uuid)

        # Clear global caches
        try:
            from django.core.cache import cache
            from wger.manager.services.exercise_catalog import bump_catalog_version
            bump_catalog_version()
            cache.clear()
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS(
            f"\n=== SUMMARY ===\n"
            f"Total Exercises in DB: {len(ex_names)}\n"
            f"Matched Exercises: {matched_count}\n"
            f"ExerciseImage (Static Previews Created): {images_created_count}\n"
            f"CalisthenicsExercise (GIF Demos Assigned): {gifs_assigned_count}\n"
            f"Italian Instructions Updated: {instructions_updated_count}\n"
            f"Unmatched Exercises (Untouched, no placeholder): {len(ex_names) - matched_count}\n"
        ))
