# This file is part of wger Workout Manager.
#
# wger Workout Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# wger Workout Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License

# Standard Library
import re
from decimal import (
    Decimal,
    InvalidOperation,
)

# Django
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    redirect,
    render,
)
from django.utils import timezone
from django.utils.translation import gettext as _

# wger
from wger.weight.models import WeightEntry


ACTIVITY_LEVELS = {'beginner', 'intermediate', 'advanced'}
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _complete(profile):
    profile.onboarding_completed = True
    profile.save()


@login_required
def onboarding(request):
    """
    First-login onboarding wizard: body weight, height, activity level and
    basic profile data. Every step is optional; submitting (or skipping) marks
    the profile as onboarded so the user is not asked again.
    """
    profile = request.user.userprofile

    # Explicit skip (top-right link or a `skip` form field)
    if request.GET.get('skip') or request.POST.get('skip'):
        _complete(profile)
        return redirect('core:dashboard')

    if request.method == 'POST':
        user = request.user

        # --- Body weight -> WeightEntry for today -------------------------
        raw_weight = (request.POST.get('weight') or '').replace(',', '.').strip()
        if raw_weight:
            try:
                weight = Decimal(raw_weight)
                if Decimal(30) <= weight <= Decimal(600):
                    WeightEntry.objects.update_or_create(
                        user=user,
                        date=timezone.localdate(),
                        defaults={'weight': weight},
                    )
            except (InvalidOperation, ValueError, TypeError):
                pass

        # --- Height (cm) -------------------------------------------------
        raw_height = (request.POST.get('height') or '').strip()
        if raw_height:
            try:
                height = int(round(float(raw_height.replace(',', '.'))))
                if 100 <= height <= 250:
                    profile.height = height
            except (ValueError, TypeError):
                pass

        # --- Activity level -------------------------------------------------
        activity_level = (request.POST.get('activity_level') or '').strip()
        if activity_level in ACTIVITY_LEVELS:
            profile.activity_level = activity_level

        # --- Basic profile data -------------------------------------------
        first_name = (request.POST.get('first_name') or '').strip()
        last_name = (request.POST.get('last_name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        if first_name:
            user.first_name = first_name[:150]
        if last_name:
            user.last_name = last_name[:150]
        if email and EMAIL_RE.match(email):
            user.email = email

        user.save()
        _complete(profile)
        messages.success(request, _('Welcome! Your profile is ready.'))
        return redirect('core:dashboard')

    return render(request, 'user/onboarding.html', {
        'profile': profile,
    })
