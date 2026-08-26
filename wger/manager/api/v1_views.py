# -*- coding: utf-8 -*-
"""
V1 API Views for Decoupled Frontend and Fast Catalog Access.
"""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from wger.exercises.models import Exercise, Muscle
from wger.manager.models import Routine, Day, Slot, SlotEntry, WeightConfig
from wger.manager.services.exercise_catalog import get_cached_exercise_catalog


@api_view(['GET'])
@permission_classes([AllowAny])
def api_v1_exercises_list(request):
    """
    GET /api/v1/exercises/
    Returns compact, versioned exercise catalog DTO.
    Served 100% from high-performance in-memory cache on hits.
    """
    lang = getattr(request, 'LANGUAGE_CODE', 'it')
    catalog = get_cached_exercise_catalog(language_code=lang)
    return JsonResponse(catalog, safe=False)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_v1_exercise_detail(request, pk):
    """
    GET /api/v1/exercises/<id>/
    Returns single exercise details.
    """
    exercise = get_object_or_404(Exercise, pk=pk)
    translation = exercise.get_translation()
    name = translation.name if translation and translation.name else f"Exercise #{exercise.id}"
    
    data = {
        'id': exercise.id,
        'uuid': str(exercise.uuid),
        'name': name,
        'category': exercise.category.name if exercise.category else '',
        'muscles': [m.name for m in exercise.muscles.all()],
        'equipment': [eq.name for eq in exercise.equipment.all()],
        'description': translation.description if translation else '',
        'image': exercise.demo_media_url or '',
    }
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_v1_muscles_list(request):
    """
    GET /api/v1/muscles/
    """
    muscles = list(Muscle.objects.values('id', 'name'))
    return Response({'items': muscles})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_v1_routines_list(request):
    """
    GET /api/v1/routines/
    User-specific routines list.
    """
    routines = Routine.objects.filter(user=request.user)
    items = []
    for r in routines:
        items.append({
            'id': r.id,
            'name': r.name or f"Routine #{r.id}",
            'created': r.created.isoformat() if hasattr(r, 'created') and r.created else None,
            'is_active': getattr(r, 'is_active', True),
        })
    return Response({'items': items})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_v1_routine_detail(request, pk):
    """
    GET /api/v1/routines/<id>/
    """
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    days_data = []
    for day in routine.days.all():
        slots_data = []
        for slot in day.slots.all():
            entries_data = []
            for entry in slot.entries.all():
                entries_data.append({
                    'id': entry.id,
                    'exercise_id': entry.exercise.id,
                    'exercise_name': entry.exercise.get_translation().name if entry.exercise.get_translation() else f"Exercise #{entry.exercise.id}",
                    'sets': entry.sets_config.sets if hasattr(entry, 'sets_config') and entry.sets_config else 3,
                })
            slots_data.append({
                'id': slot.id,
                'entries': entries_data,
            })
        days_data.append({
            'id': day.id,
            'name': day.name,
            'slots': slots_data,
        })
        
    return Response({
        'id': routine.id,
        'name': routine.name,
        'days': days_data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_v1_routine_add_exercise(request, routine_id, day_id):
    """
    POST /api/v1/routines/<id>/exercises/
    Add exercise to a routine day.
    """
    routine = get_object_or_404(Routine, pk=routine_id, user=request.user)
    day = get_object_or_404(Day, pk=day_id, routine=routine)
    
    exercise_id = request.data.get('exercise_id')
    if not exercise_id:
        return Response({'error': 'exercise_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    
    slot = Slot.objects.create(day=day)
    slot_entry = SlotEntry.objects.create(slot=slot, exercise=exercise)
    WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=0)
    
    return Response({
        'status': 'success',
        'slot_id': slot.id,
        'entry_id': slot_entry.id,
        'exercise_id': exercise.id
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_v1_routine_delete_exercise(request, routine_id, exercise_id):
    """
    DELETE /api/v1/routines/<id>/exercises/<exercise_id>/
    Delete slot/exercise entry from routine.
    """
    routine = get_object_or_404(Routine, pk=routine_id, user=request.user)
    entries = SlotEntry.objects.filter(slot__day__routine=routine, pk=exercise_id)
    if not entries.exists():
        return Response({'error': 'Exercise entry not found'}, status=status.HTTP_404_NOT_FOUND)
        
    for entry in entries:
        slot = entry.slot
        entry.delete()
        if slot and not slot.slotentry_set.exists():
            slot.delete()
            
    return Response({'status': 'deleted'})
