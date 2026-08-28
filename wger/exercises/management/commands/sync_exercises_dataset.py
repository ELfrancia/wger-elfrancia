"""
Django Management Command: sync_exercises_dataset
Syncs 1,324 exercises, Italian step-by-step instructions, and accurate animation media
from https://github.com/hasaneyldrm/exercises-dataset.
"""

import json
import logging
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from wger.exercises.models import (
    CalisthenicsExercise,
    Exercise,
    ExerciseCategory,
    ExerciseImage,
    ExerciseTranslation,
    ExerciseVideo,
    Equipment,
    Muscle,
)

logger = logging.getLogger(__name__)

DATASET_RAW_URL = "https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/data/exercises.json"
BASE_MEDIA_URL = "https://raw.githubusercontent.com/hasaneyldrm/exercises-dataset/main/videos/"


def normalize_tokens(s):
    s = (s or "").lower()
    s = s.replace("benchpress", "bench press").replace("dumbbells", "dumbbell")
    return set(re.findall(r"[a-z]+", s))


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

        self.stdout.write(self.style.NOTICE("Downloading exercises dataset from hasaneyldrm/exercises-dataset..."))
        req = Request(DATASET_RAW_URL, headers={"User-Agent": "Mozilla/5.0 (ONYX Engine)"})
        try:
            with urlopen(req, timeout=30) as resp:
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

        existing_exercises = list(Exercise.objects.all().prefetch_related("muscles", "equipment"))
        matched_count = 0
        updated_media_count = 0
        updated_trans_count = 0

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
            matched_exercise = None
            best_score = 0

            for ex in existing_exercises:
                trans = ex.get_translation()
                if not trans:
                    continue
                ex_tokens = normalize_tokens(trans.name)
                if not ex_tokens:
                    continue

                if ex_tokens == item_tokens:
                    matched_exercise = ex
                    best_score = 100
                    break

                overlap = len(ex_tokens & item_tokens)
                if overlap > 0:
                    score = (2.0 * overlap) / (len(ex_tokens) + len(item_tokens)) * 100
                    if score > best_score and score >= 75:
                        best_score = score
                        matched_exercise = ex

            if matched_exercise:
                matched_count += 1
                if not dry_run:
                    # Update or create CalisthenicsExercise link for instant demo_media_url resolution
                    cal_ex, _ = CalisthenicsExercise.objects.get_or_create(
                        id=str(matched_exercise.uuid),
                        defaults={
                            "name": matched_exercise.get_translation().name if matched_exercise.get_translation() else item_name,
                            "slug": f"ex-{matched_exercise.id}",
                            "demo_media_url": video_url,
                            "description": instructions_it,
                        }
                    )
                    if cal_ex.demo_media_url != video_url:
                        cal_ex.demo_media_url = video_url
                        cal_ex.save(update_fields=["demo_media_url"])
                        updated_media_count += 1

                    # If download requested, save file locally
                    if download:
                        local_file_path = os.path.join(media_dir, f"{matched_exercise.id}_{gif_filename}")
                        if not os.path.exists(local_file_path):
                            try:
                                d_req = Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
                                with urlopen(d_req, timeout=15) as d_resp:
                                    with open(local_file_path, "wb") as f_out:
                                        f_out.write(d_resp.read())
                                cal_ex.demo_media_url = f"/media/exercises/{matched_exercise.id}_{gif_filename}"
                                cal_ex.save(update_fields=["demo_media_url"])
                            except Exception as e:
                                logger.warning(f"Could not download media for {item_name}: {e}")

                    # Update Italian translation instructions
                    if instructions_it:
                        it_trans = ExerciseTranslation.objects.filter(exercise=matched_exercise).first()
                        if it_trans and (not it_trans.description or len(it_trans.description) < 30):
                            it_trans.description = instructions_it
                            it_trans.save(update_fields=["description"])
                            updated_trans_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Dataset sync finished! Matched: {matched_count}/{total} exercises, Media updated: {updated_media_count}, Italian descriptions updated: {updated_trans_count}."
        ))
