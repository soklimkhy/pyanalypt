"""
Main URL Configuration
API documentation: API_DOCS.md
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/v1/",
        include(
            [
                path("", include("apps.users.urls")),
                path("datasets/", include("apps.datasets.urls")),
                path("datalab/", include("apps.datalab.urls")),
                path("goals/", include("apps.goals.urls")),
                path("eda/", include("apps.eda.urls")),
                path("viz/", include("apps.visualization.urls")),
                path("reports/", include("apps.reports.urls")),
                path("mlstudio/", include("apps.mlstudio.urls")),
                path("chat/", include("apps.chat.urls")),
                path("dashboards/", include("apps.dashboards.urls")),
            ]
        ),
    ),
    path("accounts/", include("allauth.urls")),  # Google OAuth
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
