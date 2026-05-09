from rest_framework import serializers

from .models import Report, ReportItem


class ReportItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportItem
        fields = ["id", "order", "chart_type", "chart_params", "chart_image", "annotation", "created_at"]
        read_only_fields = ["id", "created_at"]


class ReportSerializer(serializers.ModelSerializer):
    dataset_name = serializers.CharField(source="dataset.file_name", read_only=True)
    items      = ReportItemSerializer(many=True, read_only=True)
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Report
        fields = ["id", "dataset", "dataset_name", "goal", "title", "description", "created_at", "updated_at", "item_count", "items"]
        read_only_fields = ["id", "dataset_name", "created_at", "updated_at", "item_count"]


class ReportListSerializer(serializers.ModelSerializer):
    dataset_name = serializers.CharField(source="dataset.file_name", read_only=True)
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Report
        fields = ["id", "dataset", "dataset_name", "goal", "title", "description", "created_at", "updated_at", "item_count"]
        read_only_fields = ["id", "dataset_name", "created_at", "updated_at", "item_count"]
