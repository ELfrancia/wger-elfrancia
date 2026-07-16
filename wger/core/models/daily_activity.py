#  This file is part of wger Workout Manager <https://github.com/wger-project>.
#  Copyright (C) 2013 - 2021 wger Team
#
#  wger Workout Manager is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  wger Workout Manager is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Django
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class DailyActivity(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='daily_activities',
        verbose_name=_('User'),
    )
    date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('Date'),
    )
    steps = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Steps'),
    )
    calories = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Calories'),
    )
    water = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        verbose_name=_('Water (L)'),
    )

    class Meta:
        verbose_name = _('Daily activity')
        verbose_name_plural = _('Daily activities')
        unique_together = ('user', 'date')

    def __str__(self):
        return f'{self.user.username} - {self.date}'

    def get_owner_object(self):
        return self
