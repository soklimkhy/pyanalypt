from rest_framework import serializers

from apps.core.ml_engine import ALGORITHMS, TASK_TYPES, HYPERPARAMS_SCHEMA, validate_hyperparams

from .models import MLModel


class TrainModelSerializer(serializers.Serializer):
    """Input validation for POST /mlstudio/ (create + train)."""

    name            = serializers.CharField(max_length=200)
    description     = serializers.CharField(required=False, allow_blank=True, default="")
    dataset_id      = serializers.IntegerField()
    task_type       = serializers.ChoiceField(choices=list(TASK_TYPES))
    algorithm       = serializers.CharField()
    feature_columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    target_column   = serializers.CharField(required=False, allow_blank=True, default="")
    hyperparams     = serializers.DictField(required=False, default=dict)
    test_size       = serializers.FloatField(min_value=0.05, max_value=0.5, default=0.2)

    def validate(self, data):
        task_type = data["task_type"]
        algorithm = data["algorithm"]

        valid_algos = list(ALGORITHMS.get(task_type, {}).keys())
        if algorithm not in valid_algos:
            raise serializers.ValidationError(
                {"algorithm": f"For task '{task_type}', algorithm must be one of: {valid_algos}"}
            )

        if task_type != "clustering" and not data.get("target_column"):
            raise serializers.ValidationError(
                {"target_column": "Required for regression and classification tasks."}
            )

        ok, err, _ = validate_hyperparams(algorithm, data.get("hyperparams", {}))
        if not ok:
            raise serializers.ValidationError({"hyperparams": err})

        allowed = list(HYPERPARAMS_SCHEMA.get(algorithm, {}).keys())
        if allowed:
            data["_allowed_hyperparams"] = allowed

        return data


class PredictSerializer(serializers.Serializer):
    """Input for POST /mlstudio/{id}/predict/."""
    dataset_id = serializers.IntegerField(
        required=False,
        help_text="Dataset to run predictions on. Defaults to the training dataset.",
    )


class MLModelSerializer(serializers.ModelSerializer):
    dataset_name = serializers.CharField(source="dataset.file_name", read_only=True)
    allowed_hyperparams = serializers.SerializerMethodField()

    class Meta:
        model = MLModel
        fields = [
            "id", "name", "description",
            "dataset", "dataset_name",
            "task_type", "algorithm",
            "feature_columns", "target_column",
            "hyperparams", "test_size",
            "status", "progress", "error_message",
            "metrics", "feature_importances", "label_classes",
            "train_samples", "test_samples", "training_time_seconds",
            "allowed_hyperparams",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "progress", "error_message",
            "metrics", "feature_importances", "label_classes",
            "train_samples", "test_samples", "training_time_seconds",
            "created_at", "updated_at", "dataset_name",
        ]

    def get_allowed_hyperparams(self, obj):
        schema = HYPERPARAMS_SCHEMA.get(obj.algorithm, {})
        return {k: v.__name__ for k, v in schema.items()}
