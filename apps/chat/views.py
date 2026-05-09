import logging

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.data_engine import apply_stored_casts, get_cached_dataframe
from apps.core.ollama_client import (
    OllamaError,
    build_dataset_context,
    chat_about_data,
    stream_chat_about_data,
)
from apps.datasets.models import Dataset

from .models import ChatMessage, ChatSession
from .serializers import (
    ChatMessageSerializer,
    ChatSessionSerializer,
    CreateSessionSerializer,
    SendMessageSerializer,
)

logger = logging.getLogger(__name__)


def _load_df(dataset):
    df = get_cached_dataframe(
        dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date
    )
    if df is None:
        return None
    if dataset.column_casts:
        df = apply_stored_casts(df, dataset.column_casts)
    return df


def _history(session) -> list[dict]:
    return list(
        session.messages.values("role", "content").order_by("created_at")
    )


class ChatSessionViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """GET /chat/  — list all sessions for the current user."""
        qs = ChatSession.objects.filter(user=request.user).prefetch_related("messages")
        dataset_id = request.query_params.get("dataset_id")
        if dataset_id:
            qs = qs.filter(dataset_id=dataset_id)
        return Response(ChatSessionSerializer(qs, many=True).data)

    def create(self, request):
        """POST /chat/  — start a new chat session."""
        s = CreateSessionSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        dataset = get_object_or_404(Dataset, pk=s.validated_data["dataset_id"], user=request.user)
        session = ChatSession.objects.create(
            user=request.user,
            dataset=dataset,
            title=s.validated_data.get("title", "New conversation"),
        )
        return Response(ChatSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        """GET /chat/{id}/  — session detail + full message history."""
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)
        messages = session.messages.all()
        return Response({
            **ChatSessionSerializer(session).data,
            "messages": ChatMessageSerializer(messages, many=True).data,
        })

    def partial_update(self, request, pk=None):
        """PATCH /chat/{id}/  — rename session title."""
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)
        title = request.data.get("title", "").strip()
        if not title:
            return Response({"detail": "'title' is required."}, status=status.HTTP_400_BAD_REQUEST)
        session.title = title
        session.save(update_fields=["title"])
        return Response(ChatSessionSerializer(session).data)

    def destroy(self, request, pk=None):
        """DELETE /chat/{id}/"""
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="message")
    def message(self, request, pk=None):
        """
        POST /chat/{id}/message/
        Body: { "message": "..." }
        Returns the full assistant reply synchronously.
        """
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)

        s = SendMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user_text = s.validated_data["message"]

        df = _load_df(session.dataset)
        if df is None:
            return Response(
                {"detail": "Could not load dataset file."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        context = build_dataset_context(df, dataset_name=session.dataset.file_name)
        history  = _history(session)

        # Save user message first
        ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=user_text)

        try:
            reply = chat_about_data(context, history, user_text)
        except OllamaError as exc:
            logger.error("Ollama error in chat session %s: %s", session.pk, exc)
            return Response(
                {"detail": f"AI service unavailable: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        assistant_msg = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content=reply,
        )
        session.save(update_fields=["updated_at"])

        return Response({
            "session_id": session.pk,
            "message": ChatMessageSerializer(assistant_msg).data,
        })

    @action(detail=True, methods=["post"], url_path="stream")
    def stream(self, request, pk=None):
        """
        POST /chat/{id}/stream/
        Body: { "message": "..." }
        Returns a Server-Sent Events stream. The full reply is also saved to DB
        by accumulating tokens server-side before closing the stream.
        """
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)

        s = SendMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user_text = s.validated_data["message"]

        df = _load_df(session.dataset)
        if df is None:
            return Response(
                {"detail": "Could not load dataset file."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        context = build_dataset_context(df, dataset_name=session.dataset.file_name)
        history  = _history(session)

        ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=user_text)

        accumulated: list[str] = []

        def _event_stream():
            for chunk in stream_chat_about_data(context, history, user_text):
                # Extract token text from SSE chunk to accumulate reply
                if chunk.startswith("data: ") and not chunk.startswith("data: ["):
                    token_text = chunk[6:].rstrip("\n").replace("\\n", "\n")
                    accumulated.append(token_text)
                yield chunk

            # Persist complete reply after stream ends
            full_reply = "".join(accumulated)
            if full_reply:
                ChatMessage.objects.create(
                    session=session,
                    role=ChatMessage.ROLE_ASSISTANT,
                    content=full_reply,
                )
                ChatSession.objects.filter(pk=session.pk).update(updated_at=timezone.now())

        return StreamingHttpResponse(
            _event_stream(),
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @action(detail=True, methods=["delete"], url_path="clear")
    def clear(self, request, pk=None):
        """DELETE /chat/{id}/clear/  — wipe all messages in a session."""
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)
        count, _ = session.messages.all().delete()
        return Response({"detail": f"Cleared {count} message(s)."})
