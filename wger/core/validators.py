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

# Django
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# wger
from wger.utils.username import generate_username_suggestions


def validate_username(username: str):
    """
    Checks that the username is not already taken and returns suggestions if it is.
    """
    if User.objects.filter(username__exact=username).exists():
        suggestions = generate_username_suggestions(username)
        suggestions_string = ', '.join(suggestions)
        raise forms.ValidationError(
            f'A user with this username already exists. Suggestions: {suggestions_string}'
        )


class UppercaseValidator:
    def validate(self, password, user=None):
        if not any(char.isupper() for char in password):
            raise ValidationError(
                _("Your password must contain at least one uppercase letter."),
                code='password_no_upper',
            )

    def get_help_text(self):
        return _("Your password must contain at least one uppercase letter.")


class LowercaseValidator:
    def validate(self, password, user=None):
        if not any(char.islower() for char in password):
            raise ValidationError(
                _("Your password must contain at least one lowercase letter."),
                code='password_no_lower',
            )

    def get_help_text(self):
        return _("Your password must contain at least one lowercase letter.")


class SymbolValidator:
    def validate(self, password, user=None):
        if not any(not char.isalnum() for char in password):
            raise ValidationError(
                _("Your password must contain at least one symbol."),
                code='password_no_symbol',
            )

    def get_help_text(self):
        return _("Your password must contain at least one symbol.")

