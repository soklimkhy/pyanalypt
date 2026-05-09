from rest_framework import serializers

from .models import ChatMessage, ChatSession


class ChatSessionSerializer(serializers.ModelSerializer):
    dataset_name    = serializers.CharField(source="dataset.file_name", read_only=True)
    message_count   = serializers.SerializerMethodField()

    class Meta:
        model  = ChatSession
        fields = ["id", "title", "dataset", "dataset_name", "message_count", "created_at", "updated_at"]
        read_only_fields = ["id", "dataset_name", "message_count", "created_at", "updated_at"]

    def get_message_count(self, obj):
        return obj.messages.count()


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ChatMessage
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = ["id", "role", "created_at"]


class CreateSessionSerializer(serializers.Serializer):
    dataset_id = serializers.IntegerField()
    title      = serializers.CharField(max_length=200, default="New conversation", required=False)


class SendMessageSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1, max_length=4000)
