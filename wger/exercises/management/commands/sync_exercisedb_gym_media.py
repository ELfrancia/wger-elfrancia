"""Safely add ExerciseDB GIF previews to the gym exercise catalog."""

import os
import re
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from wger.exercises.models import CalisthenicsExercise, Exercise
from wger.exercises.media_utils import is_safe_path, is_safe_url, sanitize_filename


DATASET_URL = "https://raw.githubusercontent.com/Webbanditten/exercisedb-api/main/src/data/exercises.json"
MEDIA_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://exercisedb.dev/"}
EQUIPMENT = {"barbell", "dumbbell", "cable", "machine", "kettlebell", "band", "bodyweight", "ez"}
MUSCLE_ALIASES = {"pectoralis": "pectorals", "chest": "pectorals", "lats": "lats"}
# These UI labels omit the implement. Keep the mapping explicit rather than
# letting a broad name matcher pick an incline, decline, or Smith variation.
EXACT_ALIASES = {
    "bench press": "barbell bench press",
    "benchpress dumbbells": "dumbbell bench press",
}


def tokens(value):
    value = str(value or "").lower()
    value = value.replace("benchpress", "bench press").replace("dumbbells", "dumbbell")
    return set(re.findall(r"[a-z]+", value))


def canonical_muscles(values):
    result = set()
    for value in values:
        for token in tokens(value):
            result.add(MUSCLE_ALIASES.get(token, token))
    return result


def match_exercise(exercise, source_items):
    name = exercise.get_translation().name if exercise.get_translation() else ""
    name_tokens = tokens(name)
    if not name_tokens:
        return None
    equipment = tokens(" ".join(e.name for e in exercise.equipment.all())) & EQUIPMENT
    muscles = canonical_muscles(m.name for m in exercise.muscles.all())
    alias = EXACT_ALIASES.get(name.lower().strip())
    if alias:
        alias_tokens = tokens(alias)
        for item in source_items:
            if item["name_tokens"] == alias_tokens and (not equipment or equipment & item["equipment"]):
                return item, 100
    scored = []
    for item in source_items:
        item_tokens = item["name_tokens"]
        overlap = name_tokens & item_tokens
        if not overlap:
            continue
        # F1 favours the exact movement over a broader variation with extra words.
        name_score = 2 * len(overlap) / (len(name_tokens) + len(item_tokens))
        item_equipment = item["equipment"]
        if equipment and item_equipment and not (equipment & item_equipment):
            continue
        equipment_score = 1 if equipment and (equipment & item_equipment) else 0
        muscle_score = 1 if muscles and (muscles & item["muscles"]) else 0
        score = 70 * name_score + 20 * equipment_score + 10 * muscle_score
        scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    score, item = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0
    # A match must be specific enough and materially better than the next variant.
    if score < 75 or score - runner_up < 5:
        return None
    return item, score


class Command(BaseCommand):
    help = "Download verified ExerciseDB GIF previews for gym exercises"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Download and persist accepted matches")
        parser.add_argument("--limit", type=int, default=0, help="Only inspect the first N gym exercises")

    def handle(self, *args, **options):
        response = requests.get(DATASET_URL, headers=MEDIA_HEADERS, timeout=60)
        response.raise_for_status()
        source_items = []
        for item in response.json():
            if not item.get("gifUrl"):
                continue
            source_items.append({
                "id": item["exerciseId"],
                "name": item["name"],
                "gif_url": item["gifUrl"],
                "name_tokens": tokens(item["name"]),
                "equipment": tokens(" ".join(item.get("equipments", []))) & EQUIPMENT,
                "muscles": canonical_muscles(item.get("targetMuscles", [])),
            })

        exercises = Exercise.objects.exclude(category__name="Calisthenics").prefetch_related("translations", "equipment", "muscles")
        if options["limit"]:
            exercises = exercises[: options["limit"]]
        matches = [(exercise, match_exercise(exercise, source_items)) for exercise in exercises]
        matches = [(exercise, match) for exercise, match in matches if match]
        self.stdout.write(f"Verified matches: {len(matches)}")
        for exercise, (item, score) in matches[:10]:
            self.stdout.write(f"{exercise.get_translation().name} -> {item['name']} ({score:.1f})")
        if not options["apply"]:
            self.stdout.write("Dry run only. Re-run with --apply to download GIFs.")
            return

        media_dir = Path(settings.MEDIA_ROOT) / "exercises"
        media_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for exercise, (item, _score) in matches:
            safe_item_id = sanitize_filename(item['id'])
            if not safe_item_id:
                continue
            filename = f"exercisedb-{safe_item_id}.gif"
            path = media_dir / filename
            if not is_safe_path(str(media_dir), str(path)):
                continue
            if not path.exists():
                if not is_safe_url(item.get("gif_url")):
                    continue
                try:
                    media = requests.get(item["gif_url"], headers=MEDIA_HEADERS, timeout=30, stream=True)
                    if media.status_code != 200:
                        continue
                    content = media.content[:50 * 1024 * 1024]
                    if not content.startswith((b"GIF87a", b"GIF89a")):
                        continue
                    path.write_bytes(content)
                except Exception:
                    continue
            if not path.exists():
                continue
            CalisthenicsExercise.objects.update_or_create(
                id=exercise.uuid,
                defaults={
                    "name": exercise.get_translation().name if exercise.get_translation() else f"Exercise {exercise.id}",
                    "slug": f"gym-media-{exercise.id}",
                    "discipline": "gym",
                    "source": "ExerciseDB-verified-media",
                    "source_exercise_id": safe_item_id,
                    "demo_media_url": f"{settings.MEDIA_URL}exercises/{filename}",
                },
            )
            saved += 1
        self.stdout.write(self.style.SUCCESS(f"Saved {saved} verified GIF previews."))
