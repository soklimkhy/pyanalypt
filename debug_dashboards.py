import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.dashboards.models import Dashboard
from apps.dashboards.serializers import DashboardSerializer

try:
    dashboards = Dashboard.objects.all()
    print(f"Found {dashboards.count()} dashboards")
    for d in dashboards:
        print(f"Dashboard: {d.title}")
        data = DashboardSerializer(d).data
        print(f"Serialized OK: {d.title}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
