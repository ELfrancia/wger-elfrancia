# -*- coding: utf-8 -*-
import datetime
import decimal
from decimal import Decimal, DecimalException
import json
import logging
import re
import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db import models as django_models
from django.http import HttpResponseForbidden, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from wger.manager.models import (
    Routine,
    Day,
    WorkoutSession,
    WorkoutLog,
    Slot,
    SlotEntry,
    SetsConfig,
    RepetitionsConfig,
    WeightConfig,
)
from wger.manager.helpers import reset_routine_cache, create_day_from_session
from wger.gallery.models.image import Image
from wger.gallery.forms import ImageForm

logger = logging.getLogger(__name__)

def parse_duration_minutes(val_str):
    if not val_str:
        return None
    val = str(val_str).strip().lower()
    if ':' in val:
        parts = val.split(':')
        try:
            if len(parts) == 3:
                return int(parts[0]) * 60 + int(parts[1]) + (1 if int(parts[2]) >= 30 else 0)
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass

    total_mins = 0
    h_match = re.search(r'(\d+)\s*h', val)
    m_match = re.search(r'(\d+)\s*m', val)
    if h_match:
        total_mins += int(h_match.group(1)) * 60
    if m_match:
        total_mins += int(m_match.group(1))
    if not h_match and not m_match:
        clean_num = re.sub(r'[^\d]', '', val)
        if clean_num:
            total_mins = int(clean_num)
            
    return total_mins if total_mins > 0 else None


def make_overview_redirect(request):
    redirect_url = reverse('weight:overview')
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = redirect_url
        return response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'redirect': redirect_url})
    return redirect('weight:overview')


@login_required
def log_tailwind(request, routine_pk, day_pk):
    day = get_object_or_404(Day, pk=day_pk, routine_id=routine_pk)
    if day.routine.user != request.user:
        return HttpResponseForbidden()

    # Track active session ID for this day using django session cookies
    session_key = f'active_session_{day_pk}'
    session = None
    cutoff_24h = timezone.now() - datetime.timedelta(hours=24)

    with transaction.atomic():
        # 0. Single Active Workout Restriction: Check if user has an active session for another day/routine
        other_active = WorkoutSession.objects.select_for_update().filter(
            user=request.user,
            status='active',
            day__isnull=False,
            routine__isnull=False,
        ).exclude(day=day).order_by('-date', '-time_start', '-id').first()

        if other_active:
            o_dt = datetime.datetime.combine(other_active.date, other_active.time_start or datetime.time.min)
            if timezone.is_naive(o_dt):
                o_dt = timezone.make_aware(o_dt)
            if o_dt >= cutoff_24h and other_active.logs.exists():
                if other_active.day_id and other_active.routine_id:
                    messages.warning(
                        request,
                        _("Hai già un allenamento in corso! Completa o interrompi la sessione corrente prima di avviarne un'altra.")
                    )
                    return redirect('manager:day:overview', routine_pk=other_active.routine_id, day_pk=other_active.day_id)
            else:
                WorkoutSession.objects.filter(id=other_active.id).update(status='interrupted')

        # If ?start=true is passed, we explicitly want to start a brand new session
        if request.GET.get('start') == 'true':
            WorkoutSession.objects.filter(
                user=request.user,
                status='active'
            ).update(status='interrupted')

            session = WorkoutSession.objects.create(
                user=request.user,
                routine_id=routine_pk,
                day=day,
                date=datetime.date.today(),
                time_start=timezone.localtime(timezone.now()).time(),
                status='active',
            )
            request.session[session_key] = str(session.id)
            return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

        # 1. Try to load existing active session from session key
        session_id = request.session.get(session_key)
        if session_id:
            s = WorkoutSession.objects.select_for_update().filter(id=session_id, user=request.user, status='active').first()
            if s:
                s_dt = datetime.datetime.combine(s.date, s.time_start or datetime.time.min)
                if timezone.is_naive(s_dt):
                    s_dt = timezone.make_aware(s_dt)
                if s_dt >= cutoff_24h:
                    session = s

        # 2. Server-Side Draft Lookup: Any active WorkoutSession created in the last 24h for this day/user
        if not session:
            active_candidates = WorkoutSession.objects.select_for_update().filter(
                user=request.user,
                routine_id=routine_pk,
                day=day,
                status='active',
            ).order_by('-date', '-time_start', '-id')

            for candidate in active_candidates:
                c_dt = datetime.datetime.combine(candidate.date, candidate.time_start or datetime.time.min)
                if timezone.is_naive(c_dt):
                    c_dt = timezone.make_aware(c_dt)
                if c_dt >= cutoff_24h:
                    session = candidate
                    break

        # 3. Create a new active session draft if none found within 24h
        if not session:
            session = WorkoutSession.objects.create(
                user=request.user,
                routine_id=routine_pk,
                day=day,
                date=datetime.date.today(),
                time_start=timezone.localtime(timezone.now()).time(),
                status='active',
            )
        request.session[session_key] = str(session.id)

    if session and not session.time_start:
        session.time_start = timezone.localtime(timezone.now()).time()
        session.save()

    if session.user != request.user:
        return HttpResponseForbidden()

    if request.method == 'POST':
        action = request.POST.get('action')
        exercise_id = request.POST.get('exercise_id')
        slot_entry_id = request.POST.get('slot_entry_id')
        slot_id = request.POST.get('slot_id')

        # Sanitize integer IDs in case of localized formatting
        if exercise_id and str(exercise_id).isdigit():
            exercise_id = int(exercise_id)
        if slot_entry_id and str(slot_entry_id).isdigit():
            slot_entry_id = int(slot_entry_id)
        if slot_id and str(slot_id).isdigit():
            slot_id = int(slot_id)

        # Determine target slot first, if possible
        slot = None
        if slot_id:
            slot = day.slots.filter(id=slot_id).first()
        if not slot and slot_entry_id:
            slot_entry_obj = SlotEntry.objects.filter(id=slot_entry_id, slot__day=day).first()
            if slot_entry_obj:
                slot = slot_entry_obj.slot
        if not slot and exercise_id:
            slot = day.slots.filter(entries__exercise_id=exercise_id).distinct().first()

        with transaction.atomic():
            if action == 'restart_workout':
                session.logs.all().delete()
                session.condition_photo = None
                session.status = 'active'
                session.time_start = timezone.localtime(timezone.now()).time()
                session.time_end = None
                session.save()
                return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

            elif action == 'upload_condition_photo':
                photo = request.FILES.get('image')
                description = request.POST.get('description', '')
                finish_after = request.POST.get('finish_workout') == 'true'

                img_obj = None
                if photo:
                    default_desc = f"Foto condizione: {day.routine.name} - {day.name} ({datetime.date.today().strftime('%d/%m/%Y')})"
                    final_desc = description.strip() if description.strip() else default_desc

                    img_obj = Image(
                        user=request.user,
                        date=datetime.date.today(),
                        description=final_desc,
                    )
                    img_obj.image.save(photo.name, photo, save=True)
                    session.condition_photo = img_obj
                    session.save()

                if finish_after:
                    session.status = 'finished'
                    session.time_end = timezone.localtime(timezone.now()).time()
                    session.save()
                    WorkoutSession.objects.filter(user=request.user, day=day, status='active').update(status='finished')
                    if session_key in request.session:
                        del request.session[session_key]
                    return make_overview_redirect(request)

                session_photos_count = 1 if session.condition_photo else 0
                if request.headers.get('HX-Request') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'ok',
                        'message': 'Foto caricata con successo!',
                        'photos_count': session_photos_count,
                    })
            elif action == 'auto_save_snapshot':
                payload_str = request.POST.get('snapshot_payload')
                if payload_str:
                    try:
                        data = json.loads(payload_str)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Invalid JSON in snapshot_payload: {e}")
                        data = None

                    if data and isinstance(data, dict):
                        try:
                            elapsed = int(data.get('elapsed_seconds', 0))
                            if elapsed > 0:
                                now_dt = timezone.localtime(timezone.now())
                                session.time_end = now_dt.time()
                                start_dt = now_dt - datetime.timedelta(seconds=elapsed)
                                session.time_start = start_dt.time()
                            notes = data.get('notes')
                            if notes:
                                session.notes = notes.strip()
                            session.save()

                            # Batch sync any completed sets in payload
                            completed_sets = data.get('completed_sets', [])
                            for cs in completed_sets:
                                s_entry_id = cs.get('slot_entry_id')
                                ex_id = cs.get('exercise_id')
                                client_id = cs.get('client_id') or cs.get('clientId') or cs.get('id')
                                log_uuid = None
                                if client_id:
                                    try:
                                        log_uuid = uuid.UUID(str(client_id))
                                    except (ValueError, TypeError):
                                        log_uuid = None

                                if s_entry_id and ex_id:
                                    try:
                                        s_entry = SlotEntry.objects.filter(id=s_entry_id, slot__day=day).first()
                                        if not s_entry:
                                            continue
                                        try:
                                            clean_r = str(cs.get('repetitions', 10)).strip().replace(',', '.')
                                            reps_val = Decimal(clean_r)
                                        except (decimal.DecimalException, ValueError, TypeError):
                                            reps_val = Decimal('10')
                                        try:
                                            clean_w = str(cs.get('weight', 0)).strip().replace(',', '.')
                                            wt_val = Decimal(clean_w)
                                        except (decimal.DecimalException, ValueError, TypeError):
                                            wt_val = Decimal('0')

                                        log_datetime = datetime.datetime.combine(session.date, timezone.localtime(timezone.now()).time())
                                        if timezone.is_naive(log_datetime):
                                            log_datetime = timezone.make_aware(log_datetime)

                                        if log_uuid and WorkoutLog.objects.filter(id=log_uuid).exists():
                                            log_obj = WorkoutLog.objects.get(id=log_uuid)
                                            log_obj.repetitions = reps_val
                                            log_obj.weight = wt_val
                                            log_obj.session = session
                                            log_obj.save()
                                        else:
                                            defaults = {
                                                'user': request.user,
                                                'routine_id': session.routine_id,
                                                'repetitions': reps_val,
                                                'weight': wt_val,
                                                'date': log_datetime,
                                            }
                                            if log_uuid:
                                                defaults['id'] = log_uuid
                                            WorkoutLog.objects.update_or_create(
                                                session=session,
                                                slot_entry=s_entry,
                                                exercise_id=ex_id,
                                                defaults=defaults,
                                            )
                                    except Exception as e:
                                        logger.error(f"Error syncing set in auto_save_snapshot: {e}")
                        except Exception as e:
                            logger.error(f"Error processing auto_save_snapshot: {e}")
                return JsonResponse({'status': 'ok', 'saved_at': timezone.now().isoformat()})

            elif action == 'finish_workout':
                custom_date_str = request.POST.get('custom_date')
                custom_duration_str = request.POST.get('custom_duration')
                notes_str = request.POST.get('notes')

                if custom_date_str:
                    try:
                        session.date = datetime.datetime.strptime(custom_date_str.strip(), '%Y-%m-%d').date()
                    except ValueError:
                        pass

                if custom_duration_str:
                    duration_mins = parse_duration_minutes(custom_duration_str)
                    if duration_mins and duration_mins > 0:
                        now_dt = timezone.localtime(timezone.now())
                        session.time_end = now_dt.time()
                        start_dt = now_dt - datetime.timedelta(minutes=duration_mins)
                        session.time_start = start_dt.time()

                if notes_str:
                    session.notes = notes_str.strip()

                full_payload_str = request.POST.get('full_payload')
                if full_payload_str:
                    try:
                        data = json.loads(full_payload_str)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Invalid JSON in full_payload: {e}")
                        data = None

                    if data and isinstance(data, dict):
                        try:
                            completed_sets = data.get('completed_sets', [])
                            for cs in completed_sets:
                                s_entry_id = cs.get('slot_entry_id')
                                ex_id = cs.get('exercise_id')
                                client_id = cs.get('client_id') or cs.get('clientId') or cs.get('id')
                                log_uuid = None
                                if client_id:
                                    try:
                                        log_uuid = uuid.UUID(str(client_id))
                                    except (ValueError, TypeError):
                                        log_uuid = None

                                if s_entry_id and ex_id:
                                    try:
                                        s_entry = SlotEntry.objects.filter(id=s_entry_id, slot__day=day).first()
                                        if not s_entry:
                                            continue
                                        try:
                                            clean_r = str(cs.get('repetitions', 10)).strip().replace(',', '.')
                                            reps_val = Decimal(clean_r)
                                        except (decimal.DecimalException, ValueError, TypeError):
                                            reps_val = Decimal('10')
                                        try:
                                            clean_w = str(cs.get('weight', 0)).strip().replace(',', '.')
                                            wt_val = Decimal(clean_w)
                                        except (decimal.DecimalException, ValueError, TypeError):
                                            wt_val = Decimal('0')

                                        log_datetime = datetime.datetime.combine(session.date, timezone.localtime(timezone.now()).time())
                                        if timezone.is_naive(log_datetime):
                                            log_datetime = timezone.make_aware(log_datetime)

                                        if log_uuid and WorkoutLog.objects.filter(id=log_uuid).exists():
                                            log_obj = WorkoutLog.objects.get(id=log_uuid)
                                            log_obj.repetitions = reps_val
                                            log_obj.weight = wt_val
                                            log_obj.session = session
                                            log_obj.save()
                                        else:
                                            defaults = {
                                                'user': request.user,
                                                'routine_id': session.routine_id,
                                                'repetitions': reps_val,
                                                'weight': wt_val,
                                                'date': log_datetime,
                                            }
                                            if log_uuid:
                                                defaults['id'] = log_uuid
                                            WorkoutLog.objects.update_or_create(
                                                session=session,
                                                slot_entry=s_entry,
                                                exercise_id=ex_id,
                                                defaults=defaults,
                                            )
                                    except Exception as e:
                                        logger.error(f"Error syncing set in finish_workout: {e}")
                        except Exception as e:
                            logger.error(f"Error processing finish_workout payload: {e}")

                session.status = 'finished'
                if not session.time_end:
                    session.time_end = timezone.localtime(timezone.now()).time()
                session.save()
                WorkoutSession.objects.filter(user=request.user, day=day, status='active').update(status='finished')

                if request.POST.get('save_as_routine_day') == 'true':
                    target_routine_id = request.POST.get('target_routine_id')
                    new_routine_name = request.POST.get('new_routine_name')
                    routine_day_name = request.POST.get('routine_day_name')
                    create_day_from_session(
                        user=request.user,
                        session=session,
                        target_routine_id=target_routine_id,
                        new_routine_name=new_routine_name,
                        day_name=routine_day_name,
                    )
                    messages.success(request, _("Workout salvato come giorno di routine con successo!"))

                if session_key in request.session:
                    del request.session[session_key]
                return make_overview_redirect(request)

            elif action == 'interrupt_workout':
                session.status = 'interrupted'
                session.time_end = timezone.localtime(timezone.now()).time()
                session.save()
                WorkoutSession.objects.filter(user=request.user, day=day, status='active').update(status='interrupted')
                if session_key in request.session:
                    del request.session[session_key]
                return make_overview_redirect(request)

            elif action == 'discard_workout':
                session.logs.all().delete()
                session.status = 'interrupted'
                session.time_end = timezone.localtime(timezone.now()).time()
                session.save()
                WorkoutSession.objects.filter(user=request.user, day=day, status='active').update(status='interrupted')
                if session_key in request.session:
                    del request.session[session_key]
                return make_overview_redirect(request)

            elif action == 'complete_exercise':
                if slot:
                    if exercise_id:
                        target_entries = slot.entries.filter(exercise_id=exercise_id)
                    else:
                        target_entries = slot.entries.all()

                    target_set_ids = [entry.id for entry in target_entries]
                    logged_set_ids = list(
                        session.logs.filter(slot_entry_id__in=target_set_ids).values_list('slot_entry_id', flat=True)
                    )
                    all_completed = target_set_ids and all(sid in logged_set_ids for sid in target_set_ids)

                    if all_completed:
                        session.logs.filter(slot_entry_id__in=target_set_ids).delete()
                    else:
                        for slot_entry in target_entries:
                            if slot_entry.id not in logged_set_ids:
                                reps = None
                                weight = None

                                # 1. Read POST value specifically submitted for this slot_entry
                                post_reps = request.POST.get(f'reps_{slot_entry.id}') or request.POST.get(f'repetitions_{slot_entry.id}')
                                post_weight = request.POST.get(f'weight_{slot_entry.id}')

                                if post_reps is not None and str(post_reps).strip() != '':
                                    try:
                                        clean_r = str(post_reps).strip().replace(',', '.')
                                        reps = int(Decimal(clean_r))
                                    except (decimal.DecimalException, TypeError, ValueError):
                                        reps = None

                                if post_weight is not None and str(post_weight).strip() != '':
                                    try:
                                        clean_w = str(post_weight).strip().replace(',', '.')
                                        weight = Decimal(clean_w)
                                    except (decimal.DecimalException, ValueError, TypeError):
                                        weight = None

                                # 2. Fallback to reps_config / weight_config on slot_entry
                                if reps is None and hasattr(slot_entry, 'reps_config') and slot_entry.reps_config:
                                    if slot_entry.reps_config.reps is not None:
                                        reps = int(slot_entry.reps_config.reps)

                                if weight is None and hasattr(slot_entry, 'weight_config') and slot_entry.weight_config:
                                    if slot_entry.weight_config.weight is not None:
                                        try:
                                            clean_w = str(slot_entry.weight_config.weight).strip().replace(',', '.')
                                            weight = Decimal(clean_w)
                                        except (decimal.DecimalException, ValueError, TypeError):
                                            weight = Decimal('0')

                                # 3. Fallback to sibling set configs if reps is still None
                                if reps is None:
                                    for sibling in target_entries:
                                        if hasattr(sibling, 'reps_config') and sibling.reps_config and sibling.reps_config.reps is not None:
                                            reps = int(sibling.reps_config.reps)
                                            break

                                # 4. Final safety defaults
                                if reps is None or reps <= 0:
                                    reps = 10

                                if weight is None:
                                    weight = Decimal('0')

                                log_datetime = datetime.datetime.combine(session.date, timezone.localtime(timezone.now()).time())
                                if timezone.is_naive(log_datetime):
                                    log_datetime = timezone.make_aware(log_datetime)

                                WorkoutLog.objects.create(
                                    user=request.user,
                                    session=session,
                                    exercise_id=slot_entry.exercise_id,
                                    routine_id=routine_pk,
                                    slot_entry_id=slot_entry.id,
                                    repetitions=reps,
                                    weight=weight,
                                    date=log_datetime,
                                )

            elif action == 'delete_set':
                session.logs.filter(slot_entry_id=slot_entry_id).delete()
                if not slot and slot_entry_id:
                    slot_entry = SlotEntry.objects.filter(id=slot_entry_id, slot__day=day).first()
                    if slot_entry:
                        slot = slot_entry.slot

            elif action == 'add_set':
                if slot:
                    from wger.exercises.models import Exercise
                    if exercise_id:
                        exercise = get_object_or_404(Exercise, id=exercise_id)
                    elif slot.obj:
                        exercise = slot.obj
                    else:
                        exercise = None

                    if exercise:
                        max_order = slot.entries.aggregate(django_models.Max('order'))['order__max']
                        slot_entry = SlotEntry.objects.create(
                            slot=slot,
                            exercise=exercise,
                            order=(max_order or 0) + 1,
                        )

                        req_reps = request.POST.get('repetitions') or request.POST.get('reps')
                        req_weight = request.POST.get('weight')

                        if req_reps is not None and str(req_reps).strip() != '':
                            try:
                                clean_r = str(req_reps).strip().replace(',', '.')
                                reps_val = int(Decimal(clean_r))
                            except (decimal.DecimalException, ValueError, TypeError):
                                reps_val = 10
                        else:
                            last_entry = slot.entries.exclude(id=slot_entry.id).order_by('-order').first()
                            if (
                                last_entry
                                and hasattr(last_entry, 'reps_config')
                                and last_entry.reps_config
                                and last_entry.reps_config.reps is not None
                            ):
                                reps_val = int(last_entry.reps_config.reps)
                            else:
                                reps_val = 10

                        if req_weight is not None and str(req_weight).strip() != '':
                            try:
                                clean_w = str(req_weight).strip().replace(',', '.')
                                weight_val = Decimal(clean_w)
                            except (decimal.DecimalException, ValueError, TypeError):
                                weight_val = Decimal('0')
                        else:
                            weight_val = Decimal('0')

                        SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
                        RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=reps_val)
                        WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=weight_val)
                        reset_routine_cache(day.routine)

            elif action == 'add_exercise_on_the_fly':
                from wger.exercises.models import Exercise
                exercise = get_object_or_404(Exercise, id=exercise_id)
                max_slot_order = day.slots.aggregate(django_models.Max('order'))['order__max']
                slot = Slot.objects.create(
                    day=day,
                    order=(max_slot_order or 0) + 1,
                )
                try:
                    num_sets = int(request.POST.get('sets', 3))
                except (TypeError, ValueError):
                    num_sets = 3

                req_reps = request.POST.get('repetitions') or request.POST.get('reps')
                try:
                    clean_r = str(req_reps).strip().replace(',', '.') if req_reps else ''
                    reps_val = int(Decimal(clean_r)) if clean_r else 10
                except (decimal.DecimalException, TypeError, ValueError):
                    reps_val = 10

                req_weight = request.POST.get('weight')
                if req_weight is not None and str(req_weight).strip() not in ('', '0'):
                    try:
                        clean_w = str(req_weight).strip().replace(',', '.')
                        weight_val = Decimal(clean_w)
                    except (decimal.DecimalException, ValueError, TypeError):
                        weight_val = Decimal('0')
                else:
                    weight_val = Decimal('0')

                for i in range(num_sets):
                    slot_entry = SlotEntry.objects.create(
                        slot=slot,
                        exercise=exercise,
                        order=i + 1,
                    )
                    SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
                    RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=reps_val)
                    WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=weight_val)
                reset_routine_cache(day.routine)

            elif action == 'delete_set_config':
                slot_entry = get_object_or_404(SlotEntry, id=slot_entry_id, slot__day=day)
                slot = slot_entry.slot

                if slot.entries.count() <= 1:
                    slot.delete()
                    reset_routine_cache(day.routine)
                    if request.headers.get('HX-Request'):
                        return HttpResponse("")
                    return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)
                else:
                    slot_entry.delete()
                    reset_routine_cache(day.routine)

            else:
                # Default set logging
                repetitions = request.POST.get('repetitions')
                weight = request.POST.get('weight')
                rir = request.POST.get('rir') or None
                client_id_val = request.POST.get('client_id')
                log_uuid = None
                if client_id_val:
                    try:
                        log_uuid = uuid.UUID(str(client_id_val))
                    except (ValueError, TypeError):
                        log_uuid = None

                try:
                    clean_r = str(repetitions).strip().replace(',', '.') if repetitions is not None else ''
                    repetitions = int(Decimal(clean_r)) if clean_r != '' else 0
                except (decimal.DecimalException, TypeError, ValueError):
                    repetitions = 0

                if weight is None or str(weight).strip() in ('', '0'):
                    weight = Decimal('0')
                else:
                    try:
                        clean_w = str(weight).strip().replace(',', '.')
                        weight = Decimal(clean_w)
                    except (decimal.DecimalException, ValueError, TypeError):
                        weight = Decimal('0')

                if rir is not None and str(rir).strip() != '':
                    try:
                        clean_rir = str(rir).strip().replace(',', '.')
                        rir = Decimal(clean_rir)
                    except (decimal.DecimalException, ValueError, TypeError):
                        rir = None
                else:
                    rir = None

                log_datetime = datetime.datetime.combine(session.date, timezone.localtime(timezone.now()).time())
                if timezone.is_naive(log_datetime):
                    log_datetime = timezone.make_aware(log_datetime)

                if log_uuid and WorkoutLog.objects.filter(id=log_uuid).exists():
                    log_entry = WorkoutLog.objects.get(id=log_uuid)
                    log_entry.repetitions = repetitions
                    log_entry.weight = weight
                    log_entry.rir = rir
                    log_entry.session = session
                    log_entry.save()
                else:
                    create_kwargs = {
                        'user': request.user,
                        'session': session,
                        'exercise_id': exercise_id,
                        'routine_id': routine_pk,
                        'slot_entry_id': slot_entry_id,
                        'repetitions': repetitions,
                        'weight': weight,
                        'rir': rir,
                        'date': log_datetime,
                    }
                    if log_uuid:
                        create_kwargs['id'] = log_uuid
                    log_entry = WorkoutLog.objects.create(**create_kwargs)

                if not slot and slot_entry_id:
                    slot_entry = SlotEntry.objects.filter(id=slot_entry_id, slot__day=day).first()
                    if slot_entry:
                        slot = slot_entry.slot

        # Common rendering response for HTMX request
        if request.headers.get('HX-Request'):
            session_logs = list(session.logs.all())
            session_logged_set_ids = [log.slot_entry_id for log in session_logs if log.slot_entry_id is not None]
            logged_set_ids_set = set(session_logged_set_ids)
            completed_exercise_ids = []
            completed_slot_ids = []
            day_slots = day.slots.prefetch_related('entries__exercise', 'entries__repetitionsconfig_set', 'entries__weightconfig_set').all()
            for s in day_slots:
                all_set_ids = [entry.id for entry in s.entries.all()]
                if all_set_ids and all(sid in logged_set_ids_set for sid in all_set_ids):
                    completed_slot_ids.append(s.id)
                    if s.obj:
                        completed_exercise_ids.append(s.obj.id)

            session_logs_map = {log.slot_entry_id: log for log in session.logs.filter(slot_entry_id__isnull=False)}

            return render(request, 'workout/includes/exercise_card.html', {
                'slot': slot,
                'logged_set_ids': session_logged_set_ids,
                'completed_exercise_ids': completed_exercise_ids,
                'completed_slot_ids': completed_slot_ids,
                'day': day,
                'session_logs_map': session_logs_map,
            })

        return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

    # Calculate initial progress percentage
    day_slots = day.slots.prefetch_related(
        'entries__exercise',
        'entries__repetitionsconfig_set',
        'entries__weightconfig_set',
        'entries__rirconfig_set',
        'entries__restconfig_set',
        'entries__setsconfig_set',
    ).all()
    session_logs = list(session.logs.all())
    logged_set_ids = [log.slot_entry_id for log in session_logs if log.slot_entry_id is not None]
    total_sets = sum(slot.entries.count() for slot in day_slots)
    completed_sets = len(logged_set_ids)
    progress_percentage = int((completed_sets / total_sets) * 100) if total_sets > 0 else 0

    elapsed_seconds = 0
    if session.time_start:
        now = timezone.localtime(timezone.now())
        start_datetime = datetime.datetime.combine(session.date, session.time_start)
        if timezone.is_naive(start_datetime):
            start_datetime = timezone.make_aware(start_datetime)
        elapsed = (now - start_datetime).total_seconds()
        elapsed_seconds = max(0, int(elapsed))

    logged_set_ids_set = set(logged_set_ids)
    completed_exercise_ids = []
    completed_slot_ids = []
    for s in day_slots:
        all_set_ids = [entry.id for entry in s.entries.all()]
        if all_set_ids and all(sid in logged_set_ids_set for sid in all_set_ids):
            completed_slot_ids.append(s.id)
            if s.obj:
                completed_exercise_ids.append(s.obj.id)

    session_logs_map = {log.slot_entry_id: log for log in session_logs if log.slot_entry_id is not None}
    session_photos_count = 1 if session.condition_photo else 0
    user_routines = Routine.objects.filter(user=request.user)

    return render(request, 'workout/log_tailwind.html', {
        'day': day,
        'session': session,
        'logged_set_ids': logged_set_ids,
        'completed_exercise_ids': completed_exercise_ids,
        'completed_slot_ids': completed_slot_ids,
        'progress_percentage': progress_percentage,
        'elapsed_seconds': elapsed_seconds,
        'session_logs_map': session_logs_map,
        'today_photos_count': session_photos_count,
        'user_routines': user_routines,
    })



