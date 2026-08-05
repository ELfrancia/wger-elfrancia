# -*- coding: utf-8 -*-
"""
Exercise catalog caching service.
Builds, caches, and invalidates versioned catalog DTOs for high performance.
"""

import time
import hashlib
from django.core.cache import cache
from wger.exercises.models import Exercise, CalisthenicsExercise
from wger.manager.forms import AddExerciseForm


CATALOG_VERSION_KEY = 'catalog:version'
CATALOG_DATA_KEY_PREFIX = 'catalog:'
CATALOG_TTL = 86400  # 24 hours


def get_catalog_version():
    """
    Get the current active catalog version hash/string.
    If none exists, create a new timestamped version tag.
    """
    version = cache.get(CATALOG_VERSION_KEY)
    if not version:
        version = f"v-{int(time.time())}"
        cache.set(CATALOG_VERSION_KEY, version, CATALOG_TTL)
    return version


def bump_catalog_version():
    """
    Invalidate current catalog cache by generating a new version hash.
    Should be called after successful Baserow sync or exercise modifications.
    """
    new_version = f"v-{int(time.time())}"
    cache.set(CATALOG_VERSION_KEY, new_version, CATALOG_TTL)
    return new_version


def get_cached_exercise_catalog(language_code='it'):
    """
    Retrieve or build the compact exercise catalog DTO.
    Returns: dict containing { 'version': str, 'items': list, 'muscles': list, 'categories': list }
    """
    version = get_catalog_version()
    cache_key = f"{CATALOG_DATA_KEY_PREFIX}{version}:{language_code}"
    
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    # Build catalog with optimized DB query
    form = AddExerciseForm()
    exercise_qs = form.fields['exercise'].queryset.prefetch_related(
        'muscles', 'translations', 'equipment', 'category'
    )
    
    calisthenics_map = {
        str(cal.id): cal for cal in CalisthenicsExercise.objects.all()
    }
    
    items = []
    muscles_set = set()
    categories_set = set()
    equipment_set = set()
    
    DUMMY_NAMES = {
        'needed for demo user',
        'pending exercise',
        'an exercise',
        'very cool exercise',
        'boring exercise',
        'test pushup',
        'i will be deleted'
    }

    for ex in exercise_qs:
        translation = ex.get_translation()
        cal = calisthenics_map.get(str(ex.uuid))
        is_calisthenics = bool(cal and cal.discipline == 'calisthenics')
        
        if translation and translation.name:
            name = translation.name
        elif cal and cal.name:
            name = cal.name
        else:
            name = f"Exercise #{ex.id}"
            
        if name.strip().lower() in DUMMY_NAMES or 'needed for demo user' in name.lower():
            continue
            
        if name and name.islower():
            name = name.title()
            
        preview_url = cal.demo_media_url if (cal and cal.demo_media_url) else ex.demo_media_url
        skill_family = (cal.skill_family.replace('_', ' ').title() if (cal and cal.skill_family) else 'Other')
        
        muscles = [m.name for m in ex.muscles.all()]
        if not muscles and cal and cal.target_muscle:
            muscles = [cal.target_muscle.title()]

        for m in muscles:
            muscles_set.add(m)
            
        equipment = [eq.name for eq in ex.equipment.all()]
        if not equipment and cal:
            equipment = [cal.equipment or 'Body weight']
        for eq in equipment:
            equipment_set.add(eq)
            
        cat_name = ex.category.name if ex.category else ('Calisthenics' if is_calisthenics else 'General')
        if cat_name not in ['Another category', 'Yet another category', 'I will be deleted', 'Category']:
            categories_set.add(cat_name)
        else:
            cat_name = 'Gym' if not is_calisthenics else 'Calisthenics'
            categories_set.add(cat_name)

        search_blob = f"{name} {skill_family} {' '.join(muscles)} {' '.join(equipment)} {cat_name}".lower()

        items.append({
            'id': ex.id,
            'name': name,
            'category': cat_name,
            'muscles': muscles,
            'equipment': equipment,
            'skill_family': skill_family,
            'is_calisthenics': is_calisthenics,
            'image': preview_url or '',
            'search_blob': search_blob,
        })

    items = sorted(items, key=lambda x: x['name'].lower())
    
    catalog_dto = {
        'version': version,
        'items': items,
        'muscles': sorted(list(muscles_set)),
        'categories': sorted(list(categories_set)),
        'equipment': sorted(list(equipment_set)),
        'total_count': len(items)
    }

    cache.set(cache_key, catalog_dto, CATALOG_TTL)
    return catalog_dto
