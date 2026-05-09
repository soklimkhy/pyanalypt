from django.urls import path
from .views import DatasetViewSet, CreateDatasetView

urlpatterns = [
    path("upload/", CreateDatasetView.as_view(), name="dataset-upload"),
    path("", DatasetViewSet.as_view({"get": "list"}), name="dataset-list"),
    path("activity_logs/", DatasetViewSet.as_view({"get": "activity_logs"}), name="dataset-activity-logs"),
    path("workspace_summary/", DatasetViewSet.as_view({"get": "workspace_summary"}), name="dataset-workspace-summary"),
    path("<int:pk>/", DatasetViewSet.as_view({"get": "retrieve", "delete": "destroy"}), name="dataset-detail"),
    path("<int:pk>/rename/", DatasetViewSet.as_view({"patch": "rename"}), name="dataset-rename"),
    path("<int:pk>/export/", DatasetViewSet.as_view({"get": "export"}), name="dataset-export"),
    path("<int:pk>/duplicate/", DatasetViewSet.as_view({"post": "duplicate"}), name="dataset-duplicate"),
]
