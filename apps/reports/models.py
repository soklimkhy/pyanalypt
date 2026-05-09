from django.conf import settings
from django.db import models

CHART_TYPE_CHOICES = [
    ("bar",       "Bar"),
    ("line",      "Line"),
    ("scatter",   "Scatter"),
    ("histogram", "Histogram"),
    ("text",      "Text Only"),
]


class Report(models.Model):
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    dataset = models.ForeignKey("datasets.Dataset", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    goal    = models.ForeignKey("goals.AnalysisGoal", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class ReportItem(models.Model):
    report      = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="items")
    order       = models.PositiveIntegerField(default=0)
    chart_type  = models.CharField(max_length=20, choices=CHART_TYPE_CHOICES, blank=True)
    chart_params = models.JSONField(blank=True, null=True)
    chart_image  = models.TextField(blank=True)   # base64-encoded PNG from frontend
    annotation   = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"{self.report.title} — item {self.order}"
