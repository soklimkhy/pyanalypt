import io
import os
import logging

from rest_framework import mixins, viewsets, permissions, generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.decorators import action
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404

from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta

from apps.core.data_engine import get_cached_dataframe
from .models import Dataset, DatasetActivityLog
from .serializers import DatasetSerializer, DatasetActivityLogSerializer

logger = logging.getLogger(__name__)

ERR_UNSUPPORTED_FORMAT = "Unsupported format."


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class DatasetActivityMixin:
    """
    Mixin to provide activity logging for datasets.
    """

    def _log_activity(self, dataset, action, details=None):
        if dataset:
            dataset_name_snap = dataset.file_name
        else:
            dataset_name_snap = "N/A"

        DatasetActivityLog.objects.create(
            user=self.request.user,
            dataset=dataset,
            dataset_name_snap=dataset_name_snap,
            action=action,
            details=details or {},
        )


class CreateDatasetView(DatasetActivityMixin, generics.CreateAPIView):
    """
    POST /datasets/upload/
    Handle file uploads (Drag and Drop / File Input).
    """

    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save(user=self.request.user)
        self._log_activity(instance, "UPLOAD", {"format": instance.file_format, "size": instance.file_size})


class DatasetViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    DatasetActivityMixin,
    viewsets.GenericViewSet,
):
    """
    Endpoints:
      GET    /datasets/             — list all datasets
      GET    /datasets/{id}/         — retrieve dataset
      DELETE /datasets/{id}/         — delete dataset
      PATCH  /datasets/{id}/rename/  — rename file_name
      GET    /datasets/{id}/export/  — export (?format=csv|json|xlsx|parquet)
      POST   /datasets/{id}/duplicate/ — duplicate (?format=...)
      GET    /datasets/activity_logs/ — list activities (?dataset_id=<id>)
    """

    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        return Dataset.objects.filter(user=self.request.user).select_related("user")

    @action(detail=True, methods=["patch"])
    def rename(self, request, pk=None):
        dataset = self.get_object()
        new_name = request.data.get("file_name")
        if not new_name or not new_name.strip():
            return Response({"detail": "file_name is required."}, status=status.HTTP_400_BAD_REQUEST)

        dataset.file_name = new_name.strip()
        dataset.save(update_fields=["file_name", "updated_date"])
        self._log_activity(dataset, "RENAME", {"new_name": dataset.file_name})
        return Response(self.get_serializer(dataset).data)

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        dataset = self.get_object()
        file_path = dataset.file.path
        export_format = request.query_params.get("format", dataset.file_format).lower()
        base_name = os.path.splitext(dataset.file_name)[0]

        try:
            df = get_cached_dataframe(dataset.id, file_path, dataset.file_format)
            if df is None:
                return Response({"detail": ERR_UNSUPPORTED_FORMAT}, status=status.HTTP_400_BAD_REQUEST)

            if export_format == "csv":
                buf = io.StringIO()
                df.to_csv(buf, index=False)
                response = HttpResponse(buf.getvalue(), content_type="text/csv")
                response["Content-Disposition"] = f'attachment; filename="{base_name}.csv"'
            elif export_format in ["xlsx", "excel"]:
                buf = io.BytesIO()
                df.to_excel(buf, index=False)
                buf.seek(0)
                response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                response["Content-Disposition"] = f'attachment; filename="{base_name}.xlsx"'
            elif export_format == "json":
                response = HttpResponse(df.to_json(orient="records"), content_type="application/json")
                response["Content-Disposition"] = f'attachment; filename="{base_name}.json"'
            elif export_format == "parquet":
                buf = io.BytesIO()
                df.to_parquet(buf, index=False)
                buf.seek(0)
                response = HttpResponse(buf.getvalue(), content_type="application/octet-stream")
                response["Content-Disposition"] = f'attachment; filename="{base_name}.parquet"'
            else:
                return Response({"detail": f"Unsupported format: {export_format}"}, status=status.HTTP_400_BAD_REQUEST)

            self._log_activity(dataset, "EXPORT", {"format": export_format})
            return response
        except OSError:
            logger.exception("File not accessible during export for dataset %s", pk)
            return Response({"detail": "Dataset file not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            logger.exception("Unexpected error during export for dataset %s", pk)
            return Response({"detail": "Export failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        source = self.get_object()
        new_name = request.data.get("new_file_name") or f"{source.file_name}_copy"
        new_format = request.data.get("format", source.file_format).lower()

        try:
            df = get_cached_dataframe(source.id, source.file.path, source.file_format)
            if df is None:
                return Response({"detail": "Failed to load source."}, status=status.HTTP_400_BAD_REQUEST)

            if new_format == "csv":
                buf = io.StringIO()
                df.to_csv(buf, index=False)
                content = ContentFile(buf.getvalue().encode("utf-8"))
            elif new_format == "json":
                buf = io.StringIO()
                df.to_json(buf, orient="records")
                content = ContentFile(buf.getvalue().encode("utf-8"))
            elif new_format == "xlsx":
                buf = io.BytesIO()
                df.to_excel(buf, index=False)
                content = ContentFile(buf.getvalue())
            elif new_format == "parquet":
                buf = io.BytesIO()
                df.to_parquet(buf, index=False)
                content = ContentFile(buf.getvalue())
            else:
                return Response({"detail": "Unsupported format."}, status=status.HTTP_400_BAD_REQUEST)

            new_ds = Dataset(user=self.request.user, file_name=new_name, file_format=new_format, parent=source)
            new_ds.file.save(f"{new_name}.{new_format}", content, save=True)
            self._log_activity(source, "DUPLICATE", {"new_name": new_name, "format": new_format})
            return Response(self.get_serializer(new_ds).data, status=status.HTTP_201_CREATED)
        except OSError:
            logger.exception("File not accessible during duplicate for dataset %s", pk)
            return Response({"detail": "Source file not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            logger.exception("Unexpected error during duplicate for dataset %s", pk)
            return Response({"detail": "Duplicate failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_destroy(self, instance):
        self._log_activity(instance, "DELETE", {"file_name": instance.file_name})
        instance.delete()

    @action(detail=False, methods=["get"])
    def activity_logs(self, request):
        logs = DatasetActivityLog.objects.filter(user=request.user).select_related("user", "dataset")
        dataset_id = request.query_params.get("dataset_id")
        if dataset_id is not None:
            try:
                dataset_id = int(dataset_id)
            except (TypeError, ValueError):
                return Response({"detail": "dataset_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
            get_object_or_404(Dataset, id=dataset_id, user=request.user)
            logs = logs.filter(dataset_id=dataset_id)
        page = self.paginate_queryset(logs)
        if page is not None:
            return self.get_paginated_response(DatasetActivityLogSerializer(page, many=True).data)
        return Response(DatasetActivityLogSerializer(logs, many=True).data)

    @action(detail=False, methods=["get"])
    def workspace_summary(self, request):
        """
        GET /datasets/workspace_summary/
        Returns aggregate stats and recent activity for the main dashboard.
        """
        user = request.user
        
        # 1. Basic Stats
        total_datasets = Dataset.objects.filter(user=user).count()
        total_analyses = DatasetActivityLog.objects.filter(
            user=user, 
            action__in=["DIAGNOSE", "AI_ANALYSIS", "CAST", "RENAME_COLUMN", "DROP_DUPLICATES", "REPLACE_VALUES", "DROP_NULLS", "FILL_NULLS", "FILL_DERIVED", "TRANSFORM_COLUMN", "SCALE_COLUMNS", "EXTRACT_DATETIME", "ENCODE_COLUMNS"]
        ).count()
        
        total_size_bytes = Dataset.objects.filter(user=user).aggregate(total=Sum("file_size"))["total"] or 0
        
        # Trends (last 7 days)
        last_week = timezone.now() - timedelta(days=7)
        datasets_this_week = Dataset.objects.filter(user=user, uploaded_date__gte=last_week).count()
        analyses_today = DatasetActivityLog.objects.filter(user=user, timestamp__gte=timezone.now().replace(hour=0, minute=0, second=0)).count()

        # 2. Recent Datasets (Last 5)
        recent_datasets = Dataset.objects.filter(user=user).order_by("-updated_date")[:5]
        
        # 3. Recent Activity (Last 5)
        recent_activity = DatasetActivityLog.objects.filter(user=user).order_by("-timestamp")[:5]

        # 4. Storage Info (Plan limit is currently mocked as 120GB)
        plan_limit_bytes = 120 * 1024 * 1024 * 1024
        
        # 5. Activity Chart Data (Last 7 days)
        chart_days = []
        analyses_trend = []
        datasets_trend = []
        
        for i in range(6, -1, -1):
            day = timezone.now().date() - timedelta(days=i)
            chart_days.append(day.strftime("%a"))
            
            # Count analyses for this day
            a_count = DatasetActivityLog.objects.filter(
                user=user,
                timestamp__date=day,
                action__in=["DIAGNOSE", "AI_ANALYSIS", "CAST", "RENAME_COLUMN", "DROP_DUPLICATES", "REPLACE_VALUES", "DROP_NULLS", "FILL_NULLS", "FILL_DERIVED", "TRANSFORM_COLUMN", "SCALE_COLUMNS", "EXTRACT_DATETIME", "ENCODE_COLUMNS"]
            ).count()
            analyses_trend.append(a_count)
            
            # Count datasets uploaded for this day
            d_count = Dataset.objects.filter(user=user, uploaded_date__date=day).count()
            datasets_trend.append(d_count)

        return Response({
            "stats": {
                "total_datasets": {
                    "value": str(total_datasets),
                    "trend": f"+{datasets_this_week} this week" if datasets_this_week > 0 else "No new files",
                    "trend_up": datasets_this_week > 0
                },
                "total_analyses": {
                    "value": str(total_analyses),
                    "trend": f"+{analyses_today} today" if analyses_today > 0 else "Start analysis",
                    "trend_up": analyses_today > 0
                },
                "total_insights": {
                    "value": str(DatasetActivityLog.objects.filter(user=user, action="AI_ANALYSIS").count()),
                    "trend": "Auto-detections",
                    "trend_up": True
                },
                "storage_used": {
                    "value": self._format_size(total_size_bytes),
                    "label": "of 120 GB plan",
                    "pct": round((total_size_bytes / plan_limit_bytes) * 100, 1) if plan_limit_bytes > 0 else 0,
                    "trend_up": False
                }
            },
            "recent_datasets": [
                {
                    "id": ds.id,
                    "name": ds.file_name,
                    "status": "ready", # Mocked for now
                    "updated": self._format_time_ago(ds.updated_date)
                } for ds in recent_datasets
            ],
            "activity_feed": [
                {
                    "action": log.action,
                    "label": log.get_action_display(),
                    "sub": f"{log.dataset_name_snap} · {log.timestamp.strftime('%H:%M')}",
                    "time": self._format_time_ago(log.timestamp)
                } for log in recent_activity
            ],
            "chart_data": {
                "days": chart_days,
                "analyses": analyses_trend,
                "datasets": datasets_trend
            }
        })

    def _format_size(self, size_bytes):
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def _format_time_ago(self, dt):
        now = timezone.now()
        diff = now - dt
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        return "Just now"
