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
from django.core.management.base import BaseCommand
from django.db.models import Count

# wger
from wger.manager.models import WorkoutSession


class Command(BaseCommand):
    help = (
        'Deletes workout sessions that have no logged sets. These are leftover '
        'drafts / accidental "finish" actions that only clutter the reports.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only report what would be deleted, without touching the database.',
        )
        parser.add_argument(
            '--username',
            type=str,
            default=None,
            help='Limit the purge to a single user.',
        )
        parser.add_argument(
            '--include-active',
            action='store_true',
            help='Also delete empty sessions still marked as active (default: only finished/interrupted).',
        )

    def handle(self, *args, **options):
        statuses = ['finished', 'interrupted']
        if options['include_active']:
            statuses.append('active')

        qs = (
            WorkoutSession.objects.filter(status__in=statuses)
            .annotate(num_logs=Count('logs'))
            .filter(num_logs=0)
        )
        if options['username']:
            qs = qs.filter(user__username=options['username'])

        total = qs.count()
        self.stdout.write(f'Found {total} empty session(s) ({", ".join(statuses)}).')

        for session in qs.select_related('user', 'routine', 'day'):
            self.stdout.write(
                f'  - {session.user.username} | {session.date} '
                f'{session.time_start}-{session.time_end} | '
                f'{getattr(session.routine, "name", "?")} / {getattr(session.day, "name", "?")}'
            )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry run: nothing deleted.'))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} row(s) ({total} empty sessions).'))
