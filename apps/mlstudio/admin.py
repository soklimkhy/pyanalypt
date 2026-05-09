from django.contrib import admin

from .models import MLModel


@admin.register(MLModel)
class MLModelAdmin(admin.ModelAdmin):
    list_display  = ("name", "user", "dataset", "task_type", "algorithm", "status", "created_at")
    list_filter   = ("task_type", "algorithm", "status")
    search_fields = ("name", "user__username", "dataset__file_name")
    readonly_fields = (
        "metrics", "feature_importances", "label_classes",
        "train_samples", "test_samples", "training_time_seconds",
        "created_at", "updated_at",
    )
