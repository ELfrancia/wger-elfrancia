import os
import django
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.main")
django.setup()

from django.template.loader import get_template
from django.template import Context
from wger.manager.models import WorkoutSession

try:
    print("Loading session_details_modal.html...")
    template = get_template('user/session_details_modal.html')
    print("Template loaded successfully!")
    
    # Try to render it with dummy context or actual database objects
    session = WorkoutSession.objects.first()
    if session:
        print(f"Rendering template with WorkoutSession ID: {session.id}")
        # Mimic view context
        from wger.core.views.user import session_details_tailwind
        from django.test import RequestFactory
        
        request = RequestFactory().get('/')
        request.user = session.user
        
        # Add session support to RequestFactory request
        from django.contrib.sessions.middleware import SessionMiddleware
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        
        # Call the view to see if it raises a 500 error!
        response = session_details_tailwind(request, session.id)
        print("Template rendered successfully! Status code:", response.status_code)
    else:
        print("No WorkoutSession objects found in database to test rendering.")
except Exception as e:
    import traceback
    print("ERROR DURING RENDER:")
    traceback.print_exc()
