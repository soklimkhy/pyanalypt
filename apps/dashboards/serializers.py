from rest_framework import serializers

from .models import Dashboard, DashboardWidget


class DashboardWidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DashboardWidget
        fields = [
            "id", "title", "report", "chart_type", "chart_params",
            "chart_config", "text_content",
            "grid_col", "grid_row", "grid_width", "grid_height",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "chart_config", "created_at", "updated_at"]


class DashboardSerializer(serializers.ModelSerializer):
    dataset_name = serializers.CharField(source="dataset.file_name", read_only=True)
    widget_count = serializers.SerializerMethodField()
    widgets      = DashboardWidgetSerializer(many=True, read_only=True)

    class Meta:
        model  = Dashboard
        fields = [
            "id", "title", "description", "dataset", "dataset_name", 
            "is_public", "share_token", "widget_count", "widgets", 
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "dataset_name", "share_token", "widget_count", "created_at", "updated_at"]

    def get_widget_count(self, obj):
        return obj.widgets.count()


class CreateDashboardSerializer(serializers.Serializer):
    dataset_id  = serializers.IntegerField()
    title       = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class AddWidgetSerializer(serializers.Serializer):
    title       = serializers.CharField(max_length=200)
    report_id   = serializers.IntegerField(required=False, allow_null=True)
    chart_type  = serializers.ChoiceField(choices=DashboardWidget.CHART_CHOICES)
    chart_params = serializers.DictField(required=False, default=dict)
    text_content = serializers.CharField(required=False, allow_blank=True, default="")
    grid_col    = serializers.IntegerField(min_value=0, max_value=11, default=0)
    grid_row    = serializers.IntegerField(min_value=0, default=0)
    grid_width  = serializers.IntegerField(min_value=1, max_value=12, default=6)
    grid_height = serializers.IntegerField(min_value=1, default=4)


class UpdateWidgetSerializer(serializers.Serializer):
    title        = serializers.CharField(max_length=200,  required=False)
    report_id    = serializers.IntegerField(required=False, allow_null=True)
    chart_params = serializers.DictField(required=False)
    text_content = serializers.CharField(required=False, allow_blank=True)
    grid_col     = serializers.IntegerField(min_value=0, max_value=11, required=False)
    grid_row     = serializers.IntegerField(min_value=0, required=False)
    grid_width   = serializers.IntegerField(min_value=1, max_value=12, required=False)
    grid_height  = serializers.IntegerField(min_value=1, required=False)
