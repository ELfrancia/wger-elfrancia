# -*- coding: utf-8 -*-
import os
import re
import subprocess
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from wger.exercises.models import CalisthenicsExercise, Exercise, ExerciseVideo
from wger.core.models.license import License
from wger.exercises.media_utils import safe_download_file, is_safe_path, sanitize_filename

try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = None

class Command(BaseCommand):
    help = 'Download and convert all exercise media (GIFs/URLs) to high quality MP4 videos for bodybuilding and calisthenics exercises'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Limit number of exercises to process (0 = all)')

    def handle(self, *args, **options):
        if not FFMPEG_EXE:
            self.stdout.write(self.style.ERROR('FFmpeg engine not available. Please install imageio-ffmpeg.'))
            return

        self.stdout.write(self.style.SUCCESS(f'🎬 Starting MP4 video generation using FFmpeg: {FFMPEG_EXE}'))

        media_dir = os.path.join(settings.MEDIA_ROOT, 'exercises')
        os.makedirs(media_dir, exist_ok=True)

        default_license = License.objects.first()
        exercises = CalisthenicsExercise.objects.all()

        limit = options.get('limit', 0)
        if limit > 0:
            exercises = exercises[:limit]

        total = exercises.count()
        self.stdout.write(f'Processing {total} exercises...')

        converted_count = 0
        skipped_count = 0
        error_count = 0

        for idx, ex in enumerate(exercises, 1):
            demo_url = ex.demo_media_url or ''
            safe_source_id = sanitize_filename(ex.source_exercise_id or str(ex.id))
            if not safe_source_id:
                continue

            mp4_filename = f"{safe_source_id}.mp4"
            mp4_path = os.path.join(media_dir, mp4_filename)
            if not is_safe_path(media_dir, mp4_path):
                continue
            relative_mp4_url = f"/media/exercises/{mp4_filename}"

            # If MP4 already exists, make sure URLs are set
            if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 1000:
                ex.demo_media_url = relative_mp4_url
                ex.save()
                skipped_count += 1
                self.stdout.write(f"[{idx}/{total}] MP4 already present for '{ex.name}'")
                continue

            # Determine source GIF path or download remote URL
            gif_path = None
            filename = os.path.basename(demo_url) if demo_url else ""
            safe_filename = sanitize_filename(filename.rsplit('.', 1)[0]) + ('.' + filename.rsplit('.', 1)[1] if '.' in filename else '')
            candidates = [
                os.path.join(media_dir, safe_filename) if safe_filename else None,
                os.path.join(media_dir, f"{safe_source_id}.gif"),
            ]
            for c in candidates:
                if c and is_safe_path(media_dir, c) and os.path.exists(c) and os.path.getsize(c) > 100:
                    gif_path = c
                    break

            if not gif_path and demo_url.startswith('http'):
                gif_path_candidate = os.path.join(media_dir, f"{safe_source_id}.gif")
                if is_safe_path(media_dir, gif_path_candidate):
                    if safe_download_file(demo_url, gif_path_candidate, base_dir=media_dir, timeout=15):
                        gif_path = gif_path_candidate
                    else:
                        self.stdout.write(self.style.WARNING(f"[{idx}/{total}] Failed downloading media for '{ex.name}' (SSRF or download error)"))

            if not gif_path or not os.path.exists(gif_path):
                fallback_gif = os.path.join(media_dir, '4GqRrAk.gif')
                if os.path.exists(fallback_gif):
                    gif_path = fallback_gif
                else:
                    self.stdout.write(self.style.WARNING(f"[{idx}/{total}] No source media found for '{ex.name}', skipping..."))
                    error_count += 1
                    continue

            # Convert GIF to MP4 using FFmpeg
            cmd = [
                FFMPEG_EXE,
                '-y',
                '-i', gif_path,
                '-movflags', 'faststart',
                '-pix_fmt', 'yuv420p',
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                '-b:v', '1M',
                mp4_path
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 1000:
                    ex.demo_media_url = relative_mp4_url
                    ex.save()

                    # Link to native ExerciseVideo if base exercise exists
                    try:
                        base_ex = Exercise.objects.filter(uuid=ex.id).first()
                        if base_ex:
                            relative_media_field = f"exercises/{mp4_filename}"
                            ExerciseVideo.objects.update_or_create(
                                exercise=base_ex,
                                defaults={
                                    'video': relative_media_field,
                                    'is_main': True,
                                    'license': default_license
                                }
                            )
                    except Exception as ve:
                        pass

                    converted_count += 1
                    self.stdout.write(self.style.SUCCESS(f"[{idx}/{total}] Converted '{ex.name}' to MP4! ({os.path.getsize(mp4_path)} bytes)"))
                else:
                    self.stdout.write(self.style.ERROR(f"[{idx}/{total}] FFmpeg conversion failed for '{ex.name}': {result.stderr[:200]}"))
                    error_count += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"[{idx}/{total}] Exception during conversion of '{ex.name}': {exc}"))
                error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✨ MP4 Video Generation Completed!\n"
                f"• Converted to MP4: {converted_count}\n"
                f"• Already MP4: {skipped_count}\n"
                f"• Errors/Skipped: {error_count}\n"
            )
        )
