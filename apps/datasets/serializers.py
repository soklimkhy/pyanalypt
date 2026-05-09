from rest_framework import serializers
from .models import Dataset, DatasetActivityLog


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = (
            "id",
            "user",
            "file",
            "file_name",
            "file_format",
            "file_size",
            "parent",
            "uploaded_date",
            "updated_date",
        )
        read_only_fields = (
            "id",
            "user",
            "file_format",
            "file_size",
            "parent",
            "uploaded_date",
            "updated_date",
        )


class DatasetActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetActivityLog
        fields = (
            "id",
            "user",
            "dataset",
            "dataset_name_snap",
            "action",
            "details",
            "timestamp",
        )
        read_only_fields = fields
