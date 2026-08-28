"""
Django Management Command: sync_exercises_dataset
Syncs 1,324 exercises, Italian step-by-step instructions, and accurate animation media
from https://github.com/hasaneyldrm/exercises-dataset.
"""

import json
import logging
import re
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand
from django.db import transaction

from wger.exercises.models import (
    Exercise,
    ExerciseCategory,
    ExerciseTranslation,
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
        parser.add_argument("--limit", type=int, default=0, help="Limit exercises processed")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        self.stdout.write(self.style.NOTICE("Downloading exercises dataset..."))
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

        existing_exercises = list(Exercise.objects.all().prefetch_related("muscles", "equipment"))
        matched_count = 0
        updated_media_count = 0

        with transaction.atomic():
            for item in data:
                item_name = (item.get("name") or "").strip()
                gif_filename = item.get("gif_url") or f"{item.get('id')}.gif"
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
                        if hasattr(matched_exercise, "demo_media_url"):
                            matched_exercise.demo_media_url = video_url
                            matched_exercise.save(update_fields=["demo_media_url"])
                            updated_media_count += 1

                        if instructions_it:
                            it_trans = ExerciseTranslation.objects.filter(exercise=matched_exercise).first()
                            if it_trans and (not it_trans.description or len(it_trans.description) < 20):
                                it_trans.description = instructions_it
                                it_trans.save(update_fields=["description"])

            self.stdout.write(self.style.SUCCESS(f"Sync complete! Matched {matched_count} exercises, updated {updated_media_count} media URLs."))
