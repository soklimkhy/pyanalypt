from django.conf import settings
from django.db import models

from apps.datasets.models import Dataset


class ChatSession(models.Model):
    """A named conversation about a specific dataset."""

    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions")
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="chat_sessions")
    title   = models.CharField(max_length=200, default="New conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_session"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} ({self.dataset.file_name})"


class ChatMessage(models.Model):
    ROLE_USER      = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES   = [(ROLE_USER, "User"), (ROLE_ASSISTANT, "Assistant")]

    session    = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role       = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional: pin EDA context that was injected for this turn
    context_snapshot = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "chat_message"
        ordering = ["created_at"]

    def __str__(self):
        preview = self.content[:60]
        return f"[{self.role}] {preview}"
