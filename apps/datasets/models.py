import os
from django.db import models
from django.conf import settings
from .validators import validate_file_size_and_type
from django.db.models.signals import pre_delete
from django.dispatch import receiver


class Dataset(models.Model):
    """
    Model representing a dataset file associated with a user.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="datasets",
    )
    file = models.FileField(
        upload_to="datasets/%Y/%m/%d/", validators=[validate_file_size_and_type]
    )
    file_name = models.CharField(max_length=255, blank=True)
    file_format = models.CharField(max_length=10, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    is_cleaned = models.BooleanField(default=False)
    column_casts = models.JSONField(
        default=dict,
        blank=True,
        help_text="User-defined dtype overrides: {column_name: target_type}. Re-applied on every load.",
    )

    uploaded_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # 1. Set basic metadata — guard all .name/.size accesses behind if self.file
        if self.file and not self.file_name:
            self.file_name = os.path.basename(self.file.name)
        if self.file and not self.file_format:
            self.file_format = os.path.splitext(self.file.name)[1][1:].lower()
        if self.file:
            self.file_size = self.file.size

        super().save(*args, **kwargs)

    def __str__(self):
        owner = self.user.username if self.user else "Unknown"
        return f"{self.file_name} ({owner})"

    class Meta:
        ordering = ["-uploaded_date"]
        verbose_name = "Dataset"
        verbose_name_plural = "Datasets"


@receiver(pre_delete, sender=Dataset)
def dataset_delete(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
    from apps.core.data_engine import invalidate_dataframe_cache
    invalidate_dataframe_cache(instance.id)


class DatasetActivityLog(models.Model):
    """
    Tracks every activity performed on a dataset.
    """

    ACTION_CHOICES = [
        ("UPLOAD", "Upload"),
        ("RENAME", "Rename"),
        ("DELETE", "Delete"),
        ("DUPLICATE", "Duplicate"),
        ("EXPORT", "Export"),
        ("UPDATE_CELL", "Update Cell"),
        ("PREVIEW", "Preview"),
        ("DIAGNOSE", "Diagnose"),
        ("AI_ANALYSIS", "AI Analysis"),
        ("CAST", "Cast Columns"),
        ("RENAME_COLUMN", "Rename Column"),
        ("DROP_DUPLICATES", "Drop Duplicates"),
        ("REPLACE_VALUES", "Replace Values"),
        ("DROP_NULLS", "Drop Nulls"),
        ("FILL_NULLS", "Fill Nulls"),
        ("FILL_DERIVED", "Fill Derived"),
        ("FIX_FORMULA", "Fix Formula"),
        ("TRIM_OUTLIERS", "Trim Outliers"),
        ("IMPUTE_OUTLIERS", "Impute Outliers"),
        ("CAP_OUTLIERS", "Cap Outliers"),
        ("TRANSFORM_COLUMN", "Transform Column"),
        ("DROP_COLUMNS", "Drop Columns"),
        ("ADD_COLUMN", "Add Column"),
        ("FILTER_ROWS", "Filter Rows"),
        ("CLEAN_STRING", "Clean String"),
        ("SCALE_COLUMNS", "Scale Columns"),
        ("EXTRACT_DATETIME", "Extract Datetime"),
        ("ENCODE_COLUMNS", "Encode Columns"),
        ("NORMALIZE_COLUMN_NAMES", "Normalize Column Names"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="activity_logs",
    )
    # We use SET_NULL so that if a dataset is deleted, we still have the logs
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.SET_NULL,
        null=True,
        related_name="activity_logs",
    )
    dataset_name_snap = models.CharField(
        max_length=255, help_text="Snapshot of the file name at the time of log."
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"{user_str} - {self.action} on {self.dataset_name_snap}"


class DatasetSnapshot(models.Model):
    """
    Model representing a point-in-time snapshot of a dataset.
    Used for Undo/Revert functionality.
    """

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    file = models.FileField(upload_to="snapshots/%Y/%m/%d/")
    activity_log = models.OneToOneField(
        DatasetActivityLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshot",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Dataset Snapshot"
        verbose_name_plural = "Dataset Snapshots"

    def __str__(self):
        return f"Snapshot of {self.dataset.file_name} at {self.timestamp}"


@receiver(pre_delete, sender=DatasetSnapshot)
def snapshot_delete(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
