import logging

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.chart_engine import fmt_bar, fmt_histogram, fmt_line, fmt_scatter
from apps.core.data_engine import (
    apply_stored_casts,
    eda_distribution,
    get_cached_dataframe,
)
from apps.datasets.models import Dataset
from apps.reports.models import Report

from .models import Dashboard, DashboardWidget
from .serializers import (
    AddWidgetSerializer,
    CreateDashboardSerializer,
    DashboardSerializer,
    DashboardWidgetSerializer,
    UpdateWidgetSerializer,
)

logger = logging.getLogger(__name__)

_LOAD_FAILED = "Could not load dataset file."


def _load_df(dataset):
    df = get_cached_dataframe(
        dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date
    )
    if df is None:
        return None
    if dataset.column_casts:
        df = apply_stored_casts(df, dataset.column_casts)
    return df


def _render_widget(widget: DashboardWidget, df) -> dict | None:
    """
    Call the appropriate chart engine function based on widget.chart_type
    and widget.chart_params. Returns an ECharts config dict or None on failure.
    """
    p = widget.chart_params or {}
    try:
        if widget.chart_type == DashboardWidget.CHART_BAR:
            return fmt_bar(
                df,
                x_col=p["x_col"],
                y_col=p["y_col"],
                agg=p.get("agg", "sum"),
                group_by=p.get("group_by"),
                limit=int(p.get("limit", 20)),
            )
        if widget.chart_type == DashboardWidget.CHART_LINE:
            y_cols = p.get("y_cols") or [p["y_col"]]
            if isinstance(y_cols, str):
                y_cols = [y_cols]
            return fmt_line(
                df,
                x_col=p["x_col"],
                y_cols=y_cols,
                sort=p.get("sort", True),
            )
        if widget.chart_type == DashboardWidget.CHART_SCATTER:
            return fmt_scatter(
                df,
                col_x=p["col_x"],
                col_y=p["col_y"],
                color_by=p.get("color_by"),
                sample=int(p.get("sample", 500)),
            )
        if widget.chart_type == DashboardWidget.CHART_HISTOGRAM:
            col = p["col"]
            dist = eda_distribution(df, [col], bins=int(p.get("bins", 20)))
            charts = fmt_histogram(dist)
            return charts.get(col)
        if widget.chart_type == DashboardWidget.CHART_TEXT:
            return None  # text widgets have no chart config
        if widget.chart_type == DashboardWidget.CHART_REPORT:
            return None  # report widgets contain an entire report (rendered on frontend)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Widget %s render failed: %s", widget.pk, exc)
        return None
    return None


# ── Dashboard CRUD ─────────────────────────────────────────────────────────────

class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == 'public_view':
            return [permissions.AllowAny()]
        return super().get_permissions()

    def list(self, request):
        """GET /dashboards/"""
        qs = Dashboard.objects.filter(user=request.user).prefetch_related("widgets")
        dataset_id = request.query_params.get("dataset_id")
        if dataset_id:
            qs = qs.filter(dataset_id=dataset_id)
        return Response(DashboardSerializer(qs, many=True).data)

    def create(self, request):
        """POST /dashboards/"""
        s = CreateDashboardSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        dataset = get_object_or_404(Dataset, pk=s.validated_data["dataset_id"], user=request.user)
        dashboard = Dashboard.objects.create(
            user=request.user,
            dataset=dataset,
            title=s.validated_data["title"],
            description=s.validated_data.get("description", ""),
        )
        return Response(DashboardSerializer(dashboard).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        """GET /dashboards/{id}/  — full dashboard with all widgets."""
        dashboard = get_object_or_404(Dashboard, pk=pk, user=request.user)
        return Response(DashboardSerializer(dashboard).data)

    def partial_update(self, request, pk=None):
        """PATCH /dashboards/{id}/  — rename or update description."""
        dashboard = get_object_or_404(Dashboard, pk=pk, user=request.user)
        fields = []
        if "title" in request.data:
            dashboard.title = str(request.data["title"]).strip() or dashboard.title
            fields.append("title")
        if "description" in request.data:
            dashboard.description = str(request.data["description"])
            fields.append("description")
        if "is_public" in request.data:
            dashboard.is_public = bool(request.data["is_public"])
            fields.append("is_public")
            
        if fields:
            dashboard.save(update_fields=fields)
        return Response(DashboardSerializer(dashboard).data)

    def destroy(self, request, pk=None):
        """DELETE /dashboards/{id}/"""
        dashboard = get_object_or_404(Dashboard, pk=pk, user=request.user)
        dashboard.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request, pk=None):
        """
        POST /dashboards/{id}/share/
        Toggle public access and return the share token.
        """
        dashboard = get_object_or_404(Dashboard, pk=pk, user=request.user)
        dashboard.is_public = request.data.get("is_public", not dashboard.is_public)
        dashboard.save(update_fields=["is_public", "updated_at"])
        return Response({
            "is_public": dashboard.is_public,
            "share_token": dashboard.share_token,
            "title": dashboard.title
        })

    @action(detail=False, methods=["get"], url_path="public/(?P<share_token>[^/.]+)")
    def public_view(self, request, share_token=None):
        """
        GET /dashboards/public/{share_token}/
        Retrieve a dashboard by its public token. No auth required if is_public=True.
        """
        dashboard = get_object_or_404(Dashboard.objects.prefetch_related("widgets"), share_token=share_token, is_public=True)
        return Response(DashboardSerializer(dashboard).data)

    @action(detail=True, methods=["post"], url_path="refresh")
    def refresh(self, request, pk=None):
        """
        POST /dashboards/{id}/refresh/
        Re-renders all non-text/non-report widgets and saves the updated chart_config.
        """
        dashboard = get_object_or_404(Dashboard, pk=pk, user=request.user)
        df = _load_df(dashboard.dataset)
        if df is None:
            return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        refreshed, errors = 0, []
        for widget in dashboard.widgets.all():
            if widget.chart_type in (DashboardWidget.CHART_TEXT, DashboardWidget.CHART_REPORT):
                continue
            config = _render_widget(widget, df)
            if config is not None:
                widget.chart_config = config
                widget.save(update_fields=["chart_config", "updated_at"])
                refreshed += 1
            else:
                errors.append({"widget_id": widget.pk, "title": widget.title})

        return Response({
            **DashboardSerializer(dashboard).data,
            "refreshed": refreshed,
            "errors": errors,
        })


# ── Widget CRUD ────────────────────────────────────────────────────────────────

class DashboardWidgetViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_dashboard(self, dashboard_id, user):
        return get_object_or_404(Dashboard, pk=dashboard_id, user=user)

    def list(self, request, dashboard_id=None):
        """GET /dashboards/{dashboard_id}/widgets/"""
        dashboard = self._get_dashboard(dashboard_id, request.user)
        return Response(DashboardWidgetSerializer(dashboard.widgets.all(), many=True).data)

    def create(self, request, dashboard_id=None):
        """POST /dashboards/{dashboard_id}/widgets/  — add a widget."""
        dashboard = self._get_dashboard(dashboard_id, request.user)

        s = AddWidgetSerializer(data=request.data)
        if not s.is_valid():
            logger.error("AddWidget validation failed — data=%s errors=%s", request.data, s.errors)
            from rest_framework.exceptions import ValidationError
            raise ValidationError(s.errors)
        d = s.validated_data

        if d.get("report_id"):
            get_object_or_404(Report, pk=d["report_id"], user=request.user)

        widget = DashboardWidget(
            dashboard=dashboard,
            title=d["title"],
            report_id=d.get("report_id"),
            chart_type=d["chart_type"],
            chart_params=d.get("chart_params", {}),
            text_content=d.get("text_content", ""),
            grid_col=d.get("grid_col", 0),
            grid_row=d.get("grid_row", 0),
            grid_width=d.get("grid_width", 6),
            grid_height=d.get("grid_height", 4),
        )

        # Render chart if it's a standard chart type
        static_types = (DashboardWidget.CHART_TEXT, DashboardWidget.CHART_REPORT)
        if widget.chart_type not in static_types:
            df = _load_df(dashboard.dataset)
            if df is not None:
                widget.chart_config = _render_widget(widget, df)

        widget.save()
        return Response(DashboardWidgetSerializer(widget).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, dashboard_id=None, pk=None):
        """PATCH /dashboards/{dashboard_id}/widgets/{id}/"""
        dashboard = self._get_dashboard(dashboard_id, request.user)
        widget = get_object_or_404(DashboardWidget, pk=pk, dashboard=dashboard)

        s = UpdateWidgetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        if "report_id" in d and d["report_id"]:
            get_object_or_404(Report, pk=d["report_id"], user=request.user)

        changed = []
        fields = ("title", "report_id", "chart_params", "text_content", "grid_col", "grid_row", "grid_width", "grid_height")
        for field in fields:
            if field in d:
                setattr(widget, field, d[field])
                changed.append(field)

        # Re-render if chart params changed and it's a renderable type
        static_types = (DashboardWidget.CHART_TEXT, DashboardWidget.CHART_REPORT)
        if "chart_params" in d and widget.chart_type not in static_types:
            df = _load_df(dashboard.dataset)
            if df is not None:
                widget.chart_config = _render_widget(widget, df)
                changed.append("chart_config")

        if changed:
            widget.save(update_fields=[*changed, "updated_at"])

        return Response(DashboardWidgetSerializer(widget).data)

    def destroy(self, request, dashboard_id=None, pk=None):
        """DELETE /dashboards/{dashboard_id}/widgets/{id}/"""
        dashboard = self._get_dashboard(dashboard_id, request.user)
        widget = get_object_or_404(DashboardWidget, pk=pk, dashboard=dashboard)
        widget.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="refresh")
    def refresh(self, request, dashboard_id=None, pk=None):
        """POST /dashboards/{dashboard_id}/widgets/{id}/refresh/"""
        dashboard = self._get_dashboard(dashboard_id, request.user)
        widget = get_object_or_404(DashboardWidget, pk=pk, dashboard=dashboard)

        static_types = (DashboardWidget.CHART_TEXT, DashboardWidget.CHART_REPORT)
        if widget.chart_type in static_types:
            return Response({"detail": "Static widgets have no chart config to refresh."})

        df = _load_df(dashboard.dataset)
        if df is None:
            return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        config = _render_widget(widget, df)
        if config is None:
            return Response(
                {"detail": "Chart rendering failed."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        widget.chart_config = config
        widget.save(update_fields=["chart_config", "updated_at"])
        return Response(DashboardWidgetSerializer(widget).data)
