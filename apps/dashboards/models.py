import uuid
from django.conf import settings
from django.db import models

from apps.datasets.models import Dataset


class Dashboard(models.Model):
    """A named collection of chart widgets for a dataset."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboards"
    )
    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="dashboards"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    # Public sharing fields
    is_public = models.BooleanField(default=False)
    share_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dashboard"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} ({self.dataset.file_name})"


class DashboardWidget(models.Model):
    """A single chart pinned to a dashboard at a specific grid position."""

    CHART_BAR = "bar"
    CHART_LINE = "line"
    CHART_SCATTER = "scatter"
    CHART_HISTOGRAM = "histogram"
    CHART_TEXT = "text"
    CHART_REPORT = "report"

    CHART_CHOICES = [
        (CHART_BAR, "Bar"),
        (CHART_LINE, "Line"),
        (CHART_SCATTER, "Scatter"),
        (CHART_HISTOGRAM, "Histogram"),
        (CHART_TEXT, "Text / Annotation"),
        (CHART_REPORT, "Embedded Report"),
    ]

    dashboard = models.ForeignKey(
        Dashboard, on_delete=models.CASCADE, related_name="widgets"
    )
    report = models.ForeignKey(
        "reports.Report",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dashboard_widgets",
    )

    title = models.CharField(max_length=200)
    chart_type = models.CharField(max_length=20, choices=CHART_CHOICES)

    # Chart parameters — matches the existing visualization API
    chart_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Column names and options forwarded to the chart engine.",
    )

    # Cached rendered config — refreshed on-demand
    chart_config = models.JSONField(
        null=True,
        blank=True,
        help_text="Last rendered ECharts config returned by the chart engine.",
    )

    # Freeform text content (for text/annotation widgets)
    text_content = models.TextField(blank=True, default="")

    # Layout: column-based grid (0-indexed, 12-column grid)
    grid_col = models.PositiveSmallIntegerField(default=0)
    grid_row = models.PositiveSmallIntegerField(default=0)
    grid_width = models.PositiveSmallIntegerField(default=6)  # out of 12
    grid_height = models.PositiveSmallIntegerField(default=4)  # arbitrary units

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dashboard_widget"
        ordering = ["grid_row", "grid_col"]

    def __str__(self):
        return f"{self.title} ({self.chart_type}) on {self.dashboard.title}"
