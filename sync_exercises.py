import os
import sys

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.local_dev')

import django
django.setup()

from wger.exercises.models import Exercise, CalisthenicsExercise, Translation, ExerciseCategory, Muscle, Equipment
from wger.core.models import Language
from wger.core.models.license import License

def sync():
    cat, _ = ExerciseCategory.objects.get_or_create(name='Calisthenics')
    default_license = License.objects.first()
    lang_en = Language.objects.get(short_name='en')
    
    cal_list = list(CalisthenicsExercise.objects.all())
    synced_count = 0
    
    for cal in cal_list:
        ex, created = Exercise.objects.get_or_create(
            uuid=cal.id,
            defaults={'category': cat, 'license': default_license}
        )
        if created or not ex.translations.exists():
            Translation.objects.get_or_create(
                exercise=ex,
                language=lang_en,
                defaults={
                    'name': cal.name,
                    'description': ' '.join(cal.instructions or []) if isinstance(cal.instructions, list) else str(cal.instructions or ''),
                    'license': default_license
                }
            )
            synced_count += 1
            
        if cal.target_muscle:
            muscle_name = cal.target_muscle.strip().capitalize()
            m = Muscle.objects.filter(name__iexact=cal.target_muscle).first()
            if not m:
                m = Muscle.objects.create(name=muscle_name, name_en=cal.target_muscle, is_front=True)
            ex.muscles.add(m)
            
    print(f"Successfully synced {synced_count} CalisthenicsExercise items to Exercise and Translation DB tables.")

if __name__ == '__main__':
    sync()
