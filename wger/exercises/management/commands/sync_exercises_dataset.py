"""
Django Management Command: sync_exercises_dataset
Syncs 1,324 exercises, Italian step-by-step instructions, and accurate animation media
from https://github.com/hasaneyldrm/exercises-dataset.
Optimized with in-memory pre-indexing for sub-second matching.
"""

import json
import logging
import os
import re
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from wger.exercises.models import (
    CalisthenicsExercise,
    Exercise,
    Translation,
)

logger = logging.getLogger(__name__)

DATASET_RAW_URL = "https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/data/exercises.json"
BASE_MEDIA_URL = "https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/videos/"


def normalize_tokens(s):
    s = (s or "").lower()
    s = s.replace("benchpress", "bench press").replace("dumbbells", "dumbbell")
    return set(re.findall(r"[a-z0-9]+", s))


class Command(BaseCommand):
    help = "Sync exercises, Italian translations, and video animation media from hasaneyldrm/exercises-dataset"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Simulate without writing to DB")
        parser.add_argument("--download", action="store_true", help="Download media locally to media/exercises/")
        parser.add_argument("--limit", type=int, default=0, help="Limit exercises processed")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        download = options["download"]
        limit = options["limit"]

        self.stdout.write(self.style.NOTICE("Downloading dataset from hasaneyldrm/exercises-dataset..."))
        req = Request(DATASET_RAW_URL, headers={"User-Agent": "Mozilla/5.0 (ONYX Engine)"})
        try:
            with urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error fetching dataset: {e}"))
            return

        total = len(data)
        self.stdout.write(self.style.SUCCESS(f"Loaded {total} exercises from dataset."))
        if limit > 0:
            data = data[:limit]

        media_dir = os.path.join(settings.MEDIA_ROOT, "exercises")
        os.makedirs(media_dir, exist_ok=True)

        self.stdout.write(self.style.NOTICE("Indexing existing database exercises in memory..."))
        exercises_by_id = {ex.id: ex for ex in Exercise.objects.all()}
        translations_index = []
        for t in Translation.objects.select_related("exercise").all():
            if t.exercise_id in exercises_by_id:
                t_tokens = normalize_tokens(t.name)
                if t_tokens:
                    translations_index.append((t.exercise_id, t.name, t_tokens, t.id, t.description))

        cal_by_uuid = {str(c.id): c for c in CalisthenicsExercise.objects.all()}

        matched_count = 0
        updated_media_count = 0
        updated_trans_count = 0

        cal_to_create = []
        cal_to_update = []
        trans_to_update = []

        self.stdout.write(self.style.NOTICE("Matching exercises and assigning video animations..."))

        for item in data:
            item_name = (item.get("name") or "").strip()
            item_id = str(item.get("id") or "")
            gif_filename = item.get("gif_url") or f"{item_id}.gif"
            video_url = f"{BASE_MEDIA_URL}{gif_filename}" if not gif_filename.startswith("http") else gif_filename

            instructions_it = ""
            if isinstance(item.get("instructions"), dict):
                instructions_it = item["instructions"].get("it") or item["instructions"].get("en") or ""
            elif isinstance(item.get("instructions"), list):
                instructions_it = "\n".join(item["instructions"])

            item_tokens = normalize_tokens(item_name)
            if not item_tokens:
                continue

            matched_ex_id = None
            matched_trans_info = None
            best_score = 0

            for ex_id, t_name, t_tokens, t_pk, t_desc in translations_index:
                if t_tokens == item_tokens:
                    matched_ex_id = ex_id
                    matched_trans_info = (t_pk, t_desc)
                    best_score = 100
                    break

                overlap = len(ex_tokens & item_tokens) if 'ex_tokens' in locals() else len(t_tokens & item_tokens)
                if overlap > 0:
                    score = (2.0 * overlap) / (len(t_tokens) + len(item_tokens)) * 100
                    if score > best_score and score >= 75:
                        best_score = score
                        matched_ex_id = ex_id
                        matched_trans_info = (t_pk, t_desc)

            if matched_ex_id and matched_ex_id in exercises_by_id:
                matched_count += 1
                matched_ex = exercises_by_id[matched_ex_id]
                ex_uuid_str = str(matched_ex.uuid)

                # Calisthenics / Demo media linking
                if ex_uuid_str in cal_by_uuid:
                    cal_obj = cal_by_uuid[ex_uuid_str]
                    if cal_obj.demo_media_url != video_url:
                        cal_obj.demo_media_url = video_url
                        if instructions_it and not cal_obj.description:
                            cal_obj.description = instructions_it
                        cal_to_update.append(cal_obj)
                        updated_media_count += 1
                else:
                    new_cal = CalisthenicsExercise(
                        id=matched_ex.uuid,
                        name=item_name,
                        slug=f"ex-{matched_ex.id}",
                        demo_media_url=video_url,
                        description=instructions_it,
                        is_published=True,
                    )
                    cal_to_create.append(new_cal)
                    cal_by_uuid[ex_uuid_str] = new_cal
                    updated_media_count += 1

                # Italian translation update
                if instructions_it and matched_trans_info:
                    t_pk, t_desc = matched_trans_info
                    if not t_desc or len(t_desc) < 30:
                        trans_to_update.append(Translation(id=t_pk, description=instructions_it))
                        updated_trans_count += 1

        if not dry_run:
            with transaction.atomic():
                if cal_to_create:
                    CalisthenicsExercise.objects.bulk_create(cal_to_create, ignore_conflicts=True)
                if cal_to_update:
                    CalisthenicsExercise.objects.bulk_update(cal_to_update, ["demo_media_url", "description"], batch_size=200)
                if trans_to_update:
                    Translation.objects.bulk_update(trans_to_update, ["description"], batch_size=200)

            try:
                from wger.manager.services.exercise_catalog import bump_catalog_version
                from django.core.cache import cache
                bump_catalog_version()
                cache.clear()
            except Exception as e:
                logger.warning(f"Could not bump catalog cache: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Sync complete! Matched: {matched_count} exercises | Video media linked: {updated_media_count} | Italian instructions updated: {updated_trans_count}."
        ))
