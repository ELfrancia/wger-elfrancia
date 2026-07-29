# -*- coding: utf-8 -*-
from django import forms
from django.utils.translation import gettext_lazy as _
from wger.manager.models import Routine, Day, SlotEntry
from wger.exercises.models import Exercise

class RoutineForm(forms.ModelForm):
    duration_weeks = forms.IntegerField(
        label=_('Duration (weeks)'),
        min_value=1,
        max_value=16,
        initial=6,
        widget=forms.NumberInput(attrs={'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold'})
    )

    class Meta:
        model = Routine
        fields = ['name', 'description', 'start', 'fit_in_week']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold focus:outline-none focus:border-primary-fixed',
                'placeholder': _('e.g. Push Pull Legs')
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary focus:outline-none focus:border-primary-fixed',
                'rows': 3,
                'placeholder': _('Describe your training program...')
            }),
            'start': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold focus:outline-none focus:border-primary-fixed'
            }),
            'fit_in_week': forms.CheckboxInput(attrs={
                'class': 'rounded bg-[#1c1b1b] border-surface-container-high text-primary-fixed focus:ring-0 focus:ring-offset-0'
            })
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start')
        duration_weeks = cleaned_data.get('duration_weeks')
        if start and duration_weeks:
            import datetime
            end = start + datetime.timedelta(weeks=duration_weeks)
            if (end - start).days > Routine.MAX_DURATION_DAYS:
                self.add_error('duration_weeks', f'A routine cannot span more than {Routine.MAX_DURATION_DAYS} days.')
        return cleaned_data


class DayForm(forms.ModelForm):
    class Meta:
        model = Day
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold focus:outline-none focus:border-primary-fixed',
                'placeholder': _('e.g. Day 1: Upper Body')
            }),
            'description': forms.TextInput(attrs={
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary focus:outline-none focus:border-primary-fixed',
                'placeholder': _('Optional day description')
            })
        }


class ExerciseModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        translation = obj.get_translation()
        return translation.name if translation else str(obj)


class AddExerciseForm(forms.Form):
    exercise = ExerciseModelChoiceField(
        queryset=Exercise.objects.none(),
        widget=forms.Select(attrs={
            'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold focus:outline-none focus:border-primary-fixed'
        })
    )
    sets = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=3,
        widget=forms.NumberInput(attrs={
            'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold text-center'
        })
    )
    reps = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=10,
        widget=forms.NumberInput(attrs={
            'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold text-center'
        })
    )
    weight = forms.DecimalField(
        min_value=0,
        max_value=1000,
        initial=20.0,
        decimal_places=1,
        widget=forms.NumberInput(attrs={
            'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold text-center'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Include all exercises, prioritizing those with translations
        qs = Exercise.objects.all().distinct()
        self.fields['exercise'].queryset = qs



