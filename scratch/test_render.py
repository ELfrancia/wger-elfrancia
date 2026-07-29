import os, sys, django, datetime

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.main')
django.setup()

from wger.manager.views import routine
from django.test import RequestFactory
from django.contrib.auth.models import User
from wger.manager.models import Day, Routine
from wger.core.models import UserProfile
from wger.gym.models import Gym

u = User.objects.first()
up, _ = UserProfile.objects.get_or_create(user=u)
try:
    g = up.gym
except Exception:
    g = Gym.objects.create(name="Default Gym", userprofile=up)

r, _ = Routine.objects.get_or_create(
    name="Test Routine",
    user=u,
    defaults={"start": datetime.date.today(), "end": datetime.date.today() + datetime.timedelta(days=30)}
)
d, _ = Day.objects.get_or_create(routine=r, name="Day 1")

req = RequestFactory().get('/')
req.user = u
req.session = {}
res = routine.add_exercise_tailwind(req, r.pk, d.pk)
html = res.content.decode('utf-8')

print("Rendered HTML length:", len(html))
print("data-calisthenics=\"false\" count:", html.count('data-calisthenics="false"'))
print("data-calisthenics=\"true\" count:", html.count('data-calisthenics="true"'))
