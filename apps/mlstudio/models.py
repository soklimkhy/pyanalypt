from django.conf import settings
from django.db import models

from apps.datasets.models import Dataset


def _model_upload_path(instance, filename):
    return f"models/{instance.user_id}/{filename}"


class MLModel(models.Model):
    TASK_REGRESSION      = "regression"
    TASK_CLASSIFICATION  = "classification"
    TASK_CLUSTERING      = "clustering"
    TASK_CHOICES = [
        (TASK_REGRESSION,     "Regression"),
        (TASK_CLASSIFICATION, "Classification"),
        (TASK_CLUSTERING,     "Clustering"),
    ]

    STATUS_PENDING  = "pending"
    STATUS_TRAINING = "training"
    STATUS_READY    = "ready"
    STATUS_FAILED   = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING,  "Pending"),
        (STATUS_TRAINING, "Training"),
        (STATUS_READY,    "Ready"),
        (STATUS_FAILED,   "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ml_models",
    )
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name="ml_models",
    )
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    task_type   = models.CharField(max_length=20, choices=TASK_CHOICES)
    algorithm   = models.CharField(max_length=50)

    feature_columns = models.JSONField(help_text="List of column names used as features.")
    target_column   = models.CharField(max_length=200, blank=True, default="",
                                        help_text="Empty for clustering tasks.")
    hyperparams     = models.JSONField(default=dict, blank=True)
    test_size       = models.FloatField(default=0.2)
    progress        = models.IntegerField(default=0, help_text="Training progress (0-100).")

    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message   = models.TextField(blank=True, default="")

    # Result fields (populated after successful training)
    metrics              = models.JSONField(null=True, blank=True)
    feature_importances  = models.JSONField(null=True, blank=True)
    label_classes        = models.JSONField(default=list, blank=True)
    train_samples        = models.IntegerField(null=True, blank=True)
    test_samples         = models.IntegerField(null=True, blank=True)
    training_time_seconds = models.FloatField(null=True, blank=True)

    model_file = models.FileField(upload_to=_model_upload_path, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ml_model"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.algorithm}/{self.task_type}) [{self.status}]"

    @property
    def is_ready(self):
        return self.status == self.STATUS_READY
