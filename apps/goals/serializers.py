from rest_framework import serializers

from .models import AnalysisGoal, AnalysisQuestion


class AnalysisQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisQuestion
        fields = ["id", "order", "question", "source", "created_at"]
        read_only_fields = ["id", "source", "created_at"]


class AnalysisGoalSerializer(serializers.ModelSerializer):
    questions = AnalysisQuestionSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(source="questions.count", read_only=True)

    class Meta:
        model = AnalysisGoal
        fields = ["id", "dataset", "problem_statement", "question_count", "questions", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_dataset(self, value):
        request = self.context["request"]
        if value.user != request.user:
            raise serializers.ValidationError("Dataset not found.")
        return value


class AnalysisGoalListSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source="questions.count", read_only=True)

    class Meta:
        model = AnalysisGoal
        fields = ["id", "dataset", "problem_statement", "question_count", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
