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
        initial=4,
        widget=forms.NumberInput(attrs={'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold'})
    )

    class Meta:
        model = Routine
        fields = ['name', 'description', 'start', 'current_week', 'total_weeks', 'fit_in_week']
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
            'start': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold focus:outline-none focus:border-primary-fixed'
            }),
            'current_week': forms.NumberInput(attrs={
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold focus:outline-none focus:border-primary-fixed',
                'min': 1
            }),
            'total_weeks': forms.NumberInput(attrs={
                'class': 'w-full bg-[#1c1b1b] border border-surface-container-high rounded-2xl p-3 text-primary font-bold focus:outline-none focus:border-primary-fixed',
                'min': 1
            }),
            'fit_in_week': forms.CheckboxInput(attrs={
                'class': 'rounded bg-[#1c1b1b] border-surface-container-high text-primary-fixed focus:ring-0 focus:ring-offset-0'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['current_week'].required = False
        self.fields['total_weeks'].required = False
        self.fields['start'].input_formats = ['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d']

    def clean(self):
        cleaned_data = super().clean()
        duration_weeks = cleaned_data.get('duration_weeks')
        cleaned_data['total_weeks'] = duration_weeks or 4

        start = cleaned_data.get('start')
        total_weeks = cleaned_data.get('total_weeks')
        current_week = cleaned_data.get('current_week')

        if start:
            import datetime
            today = datetime.date.today()
            if start <= today:
                calc_week = ((today - start).days // 7) + 1
            else:
                calc_week = 1
            if total_weeks and calc_week > total_weeks:
                calc_week = total_weeks
            if calc_week < 1:
                calc_week = 1
            
            if not current_week:
                cleaned_data['current_week'] = calc_week
            elif total_weeks and current_week > total_weeks:
                cleaned_data['current_week'] = total_weeks
        else:
            if not current_week:
                cleaned_data['current_week'] = 1

        if start and total_weeks:
            import datetime
            end = start + datetime.timedelta(weeks=total_weeks)
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



