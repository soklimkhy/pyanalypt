from django.contrib import admin

from .models import ChatMessage, ChatSession


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("role", "content", "created_at")
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display  = ("title", "user", "dataset", "created_at", "updated_at")
    list_filter   = ("created_at",)
    search_fields = ("title", "user__username", "dataset__file_name")
    inlines       = [ChatMessageInline]
    readonly_fields = ("created_at", "updated_at")
