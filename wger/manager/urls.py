# -*- coding: utf-8 -*-

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
# along with Workout Manager.  If not, see <http://www.gnu.org/licenses/>.

# Django
from django.conf.urls import include
from django.urls import path

# wger
from wger.core.views.react import ReactView
from wger.manager.views import (
    ical,
    pdf,
    routine,
    workout,
)


# sub patterns for templates
patterns_templates = [
    path(
        'overview/private',
        ReactView.as_view(login_required=True),
        name='overview',
    ),
    path(
        'overview/public',
        ReactView.as_view(login_required=True),
        name='public',
    ),
    path(
        '<int:pk>/view',
        ReactView.as_view(login_required=True),
        name='view',
    ),
]

# sub patterns for days
patterns_days = [
    path(
        '<int:day_pk>/add-logs',
        workout.log_tailwind,
        name='overview',
    ),
]

# sub patterns for routines
patterns_routine = [
    path(
        'overview',
        routine.overview_tailwind,
        name='overview',
    ),
    path(
        'add',
        routine.add_routine_tailwind,
        name='add',
    ),
    path(
        '<int:pk>/edit',
        routine.edit_routine_tailwind,
        name='edit',
    ),
    path(
        '<int:pk>/delete',
        routine.delete_routine_tailwind,
        name='delete',
    ),
    path(
        '<int:routine_pk>/day/add',
        routine.add_day_tailwind,
        name='add-day',
    ),
    path(
        '<int:routine_pk>/day/<int:day_pk>/delete',
        routine.delete_day_tailwind,
        name='delete-day',
    ),
    path(
        '<int:routine_pk>/day/<int:day_pk>/exercise/add',
        routine.add_exercise_tailwind,
        name='add-exercise',
    ),
    path(
        '<int:routine_pk>/day/<int:day_pk>/exercise/<int:slot_pk>/delete',
        routine.delete_exercise_tailwind,
        name='delete-exercise',
    ),
    path(
        '<int:routine_pk>/day/<int:day_pk>/exercise/<int:slot_pk>/set/add',
        routine.add_set_tailwind,
        name='add-set',
    ),
    path(
        '<int:routine_pk>/day/<int:day_pk>/exercise/<int:slot_pk>/set/<int:entry_pk>/delete',
        routine.delete_set_tailwind,
        name='delete-set',
    ),
    path(
        '<int:routine_pk>/day/<int:day_pk>/exercise/<int:slot_pk>/notes/update',
        routine.update_notes_tailwind,
        name='update-notes',
    ),
    path(
        '<int:pk>/edit/progression/<int:progression_pk>',
        ReactView.as_view(login_required=True),
        name='edit-progression',
    ),
    path(
        '<int:pk>/statistics',
        ReactView.as_view(login_required=True),
        name='statistics',
    ),
    path(
        '<int:pk>/logs',
        ReactView.as_view(login_required=True),
        name='logs',
    ),
    path(
        '<int:pk>/view',
        routine.view_tailwind,
        name='view',
    ),
    path(
        '<int:pk>/table',
        ReactView.as_view(login_required=True),
        name='table',
    ),
    path(
        '<int:pk>/copy',
        routine.copy_routine,
        name='copy',
    ),
    path(
        '<int:pk>/pdf/log',
        pdf.workout_log,
        name='pdf-log',
    ),
    path(
        '<int:pk>/pdf/table',
        pdf.workout_view,
        name='pdf-table',
    ),
    path(
        '<int:pk>/ical',
        ical.export,
        name='ical',
    ),
    path(
        'calendar',
        ReactView.as_view(login_required=True),
        name='calendar',
    ),
]

urlpatterns = [
    path('', include((patterns_routine, 'routine'), namespace='routine')),
    path('templates/', include((patterns_templates, 'template'), namespace='template')),
    path('<int:routine_pk>/day/', include((patterns_days, 'day'), namespace='day')),
]
