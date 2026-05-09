from django.contrib import admin
from .models import Dataset, DatasetActivityLog


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("file_name", "user", "file_format", "file_size", "uploaded_date", "updated_date")
    list_filter = ("file_format", "uploaded_date")
    search_fields = ("file_name", "user__username")
    readonly_fields = ("uploaded_date", "updated_date")


@admin.register(DatasetActivityLog)
class DatasetActivityLogAdmin(admin.ModelAdmin):
    list_display = ("dataset_name_snap", "user", "action", "timestamp")
    list_filter = ("action", "timestamp")
    search_fields = ("dataset_name_snap", "user__username")
    readonly_fields = ("user", "dataset", "dataset_name_snap", "action", "details", "timestamp")
