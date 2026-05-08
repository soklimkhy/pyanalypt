import re

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.core.data_engine import get_cached_dataframe
from apps.core.ollama_client import generate_questions, stream_suggest_questions
from apps.datasets.models import Dataset
from apps.reports.models import Report

from .models import AnalysisGoal, AnalysisQuestion
from .serializers import (
    AnalysisGoalListSerializer,
    AnalysisGoalSerializer,
    AnalysisQuestionSerializer,
)

_MAX_QUESTIONS = 20


class AnalysisGoalViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return AnalysisGoal.objects.filter(dataset__user=self.request.user)

    def get_serializer_class(self):
        if self.action == "list":
            return AnalysisGoalListSerializer
        return AnalysisGoalSerializer

    @action(detail=True, methods=["post"])
    def suggest(self, request, pk=None):
        """
        POST /api/v1/goals/{id}/suggest/
        Streams Q1, Q2... questions from Ollama based on dataset columns
        and problem_statement. Saves generated questions with source="ai"
        on completion.
        """
        goal = self.get_object()
        dataset = goal.dataset
        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format)
        columns = list(df.columns)

        def _stream_and_save():
            raw_chunks = []
            try:
                for chunk in stream_suggest_questions(columns, goal.problem_statement):
                    raw_chunks.append(chunk)
                    yield chunk

                # Reconstruct full text from SSE chunks
                full_text = "".join(
                    line[6:].replace("\\n", "\n")
                    for line in "".join(raw_chunks).splitlines()
                    if line.startswith("data: ")
                    and "[DONE]" not in line
                    and "[ERROR]" not in line
                )

                # Parse Qn: lines into individual questions
                parsed = []
                for line in full_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    cleaned = re.sub(r"^Q\d+[\.:]\s*", "", line)
                    if cleaned:
                        parsed.append(cleaned)

                # Replace previous AI suggestions; manual questions are preserved.
                goal.questions.filter(source="ai").delete()
                manual_count = goal.questions.count()
                AnalysisQuestion.objects.bulk_create([
                    AnalysisQuestion(
                        goal=goal,
                        order=manual_count + i,
                        question=q,
                        source="ai",
                    )
                    for i, q in enumerate(parsed)
                ])
            except Exception as e:
                yield f"data: [ERROR] {str(e)}\n\n"

        response = StreamingHttpResponse(_stream_and_save(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    # ── Framing workflow ───────────────────────────────────────────────────────

    @staticmethod
    def _build_sample_stats(df):
        """Return a compact {col: {mean, std}} dict for numeric columns (max 8 cols)."""
        try:
            num_df = df.select_dtypes(include="number")
            if num_df.empty:
                return None
            return {
                col: {
                    "mean": round(float(num_df[col].mean()), 3),
                    "std": round(float(num_df[col].std()), 3),
                }
                for col in list(num_df.columns)[:8]
            }
        except Exception:
            return None

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """
        POST /api/v1/goals/generate/
        Body: { "dataset_id": <int> }
        Creates a new AnalysisGoal for the dataset and generates 10 analytical
        questions via Ollama. Returns the goal id and the 10 questions as JSON.
        """
        dataset_id = request.data.get("dataset_id")
        if not dataset_id:
            return Response({"detail": "dataset_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dataset = Dataset.objects.get(pk=dataset_id, user=request.user)
        except Dataset.DoesNotExist:
            return Response({"detail": "Dataset not found."}, status=status.HTTP_404_NOT_FOUND)

        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format)
        columns = list(df.columns)
        sample_stats = self._build_sample_stats(df)

        try:
            question_texts = generate_questions(columns, n=10, sample_stats=sample_stats)
        except Exception as exc:
            return Response({"detail": f"AI generation failed: {exc}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        goal = AnalysisGoal.objects.create(dataset=dataset, problem_statement="")
        AnalysisQuestion.objects.bulk_create([
            AnalysisQuestion(goal=goal, order=i, question=q, source="ai")
            for i, q in enumerate(question_texts)
        ])

        return Response(
            {
                "goal_id": goal.id,
                "questions": AnalysisQuestionSerializer(goal.questions.all(), many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def regenerate(self, request, pk=None):
        """
        POST /api/v1/goals/{id}/regenerate/
        Deletes all existing questions for this goal and generates 10 fresh ones.
        Returns the goal id and the new question list.
        """
        goal = self.get_object()
        dataset = goal.dataset

        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format)
        columns = list(df.columns)
        sample_stats = self._build_sample_stats(df)

        try:
            question_texts = generate_questions(columns, n=10, sample_stats=sample_stats)
        except Exception as exc:
            return Response({"detail": f"AI generation failed: {exc}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        goal.questions.all().delete()
        AnalysisQuestion.objects.bulk_create([
            AnalysisQuestion(goal=goal, order=i, question=q, source="ai")
            for i, q in enumerate(question_texts)
        ])

        return Response({
            "goal_id": goal.id,
            "questions": AnalysisQuestionSerializer(goal.questions.all(), many=True).data,
        })

    @action(detail=True, methods=["post"])
    def save(self, request, pk=None):
        """
        POST /api/v1/goals/{id}/save/
        Body: { "selected_ids": [<int>, ...] }
        Keeps only the selected questions, deletes the rest, re-numbers order,
        and auto-creates a Report linked to this goal and dataset.
        Returns the kept questions and the new report metadata.
        """
        goal = self.get_object()

        selected_ids_raw = request.data.get("selected_ids", [])
        if not isinstance(selected_ids_raw, list) or not selected_ids_raw:
            return Response({"detail": "selected_ids must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            selected_ids = [int(i) for i in selected_ids_raw]
        except (ValueError, TypeError):
            return Response({"detail": "selected_ids must be a list of integers."}, status=status.HTTP_400_BAD_REQUEST)

        valid_ids = set(goal.questions.filter(pk__in=selected_ids).values_list("id", flat=True))
        if len(valid_ids) != len(set(selected_ids)):
            return Response({"detail": "One or more question IDs are invalid."}, status=status.HTTP_400_BAD_REQUEST)

        # Remove questions the user did not select
        goal.questions.exclude(pk__in=valid_ids).delete()

        # Re-number remaining questions to keep order contiguous
        for i, q in enumerate(goal.questions.order_by("order", "created_at")):
            if q.order != i:
                q.order = i
                q.save(update_fields=["order"])

        # Auto-create the report
        dataset = goal.dataset
        report = Report.objects.create(
            user=request.user,
            dataset=dataset,
            goal=goal,
            title=f"Analysis of {dataset.file_name}",
            description="",
        )

        return Response(
            {
                "saved_questions": AnalysisQuestionSerializer(goal.questions.all(), many=True).data,
                "report": {
                    "id": report.id,
                    "title": report.title,
                    "created_at": report.created_at.isoformat(),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AnalysisQuestionViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_goal(self, request, goal_pk):
        try:
            return AnalysisGoal.objects.get(pk=goal_pk, dataset__user=request.user)
        except AnalysisGoal.DoesNotExist:
            raise NotFound("Goal not found.")

    def create(self, request, goal_pk=None):
        """POST /api/v1/goals/{goal_pk}/questions/"""
        goal = self._get_goal(request, goal_pk)
        if goal.questions.count() >= _MAX_QUESTIONS:
            return Response(
                {"detail": f"A goal may have at most {_MAX_QUESTIONS} questions."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        s = AnalysisQuestionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(goal=goal, source="manual")
        return Response(s.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, goal_pk=None, pk=None):
        """PATCH /api/v1/goals/{goal_pk}/questions/{pk}/"""
        goal = self._get_goal(request, goal_pk)
        try:
            question = AnalysisQuestion.objects.get(pk=pk, goal=goal)
        except AnalysisQuestion.DoesNotExist:
            raise NotFound("Question not found.")
        s = AnalysisQuestionSerializer(question, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    def destroy(self, request, goal_pk=None, pk=None):
        """DELETE /api/v1/goals/{goal_pk}/questions/{pk}/"""
        goal = self._get_goal(request, goal_pk)
        try:
            question = AnalysisQuestion.objects.get(pk=pk, goal=goal)
        except AnalysisQuestion.DoesNotExist:
            raise NotFound("Question not found.")
        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def bulk_destroy(self, request, goal_pk=None):
        """DELETE /api/v1/goals/{goal_pk}/questions/bulk-delete/"""
        goal = self._get_goal(request, goal_pk)

        ids_raw = request.data.get("ids", [])
        if not isinstance(ids_raw, list) or not ids_raw:
            return Response({"detail": "ids must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ids = [int(i) for i in ids_raw]
        except (ValueError, TypeError):
            return Response({"detail": "ids must be a list of integers."}, status=status.HTTP_400_BAD_REQUEST)

        valid_qs = AnalysisQuestion.objects.filter(pk__in=ids, goal=goal)
        if valid_qs.count() != len(set(ids)):
            return Response({"detail": "One or more question IDs are invalid."}, status=status.HTTP_400_BAD_REQUEST)

        deleted_count, _ = valid_qs.delete()
        return Response({"deleted": deleted_count}, status=status.HTTP_200_OK)
