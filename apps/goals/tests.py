import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.datasets.models import Dataset
from .models import AnalysisGoal, AnalysisQuestion

User = get_user_model()


def _make_dataset(user):
    buf = io.BytesIO(b"region,revenue,returns\nNorth,1000,5\nSouth,800,10")
    return Dataset.objects.create(
        user=user,
        file=SimpleUploadedFile("sales.csv", buf.read(), content_type="text/csv"),
        file_name="sales.csv",
        file_format="csv",
    )


class GoalTestBase(APITestCase):
    def setUp(self):
        self.user  = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.client.force_authenticate(user=self.user)
        self.dataset = _make_dataset(self.user)

    def _create_goal(self, problem_statement="Why did revenue drop?", dataset_id=None):
        return self.client.post("/api/v1/goals/", {
            "dataset": dataset_id or self.dataset.id,
            "problem_statement": problem_statement,
        })


# ---------------------------------------------------------------------------
# AnalysisGoal CRUD
# ---------------------------------------------------------------------------

class GoalCreateTests(GoalTestBase):
    def test_create_goal_returns_201(self):
        r = self._create_goal()
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["problem_statement"], "Why did revenue drop?")
        self.assertEqual(r.data["question_count"], 0)
        self.assertEqual(r.data["questions"], [])

    def test_create_goal_without_problem_statement(self):
        r = self.client.post("/api/v1/goals/", {"dataset": self.dataset.id})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["problem_statement"], "")

    def test_create_goal_other_user_dataset_returns_400(self):
        other_ds = _make_dataset(self.other)
        r = self.client.post("/api/v1/goals/", {"dataset": other_ds.id})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self._create_goal()
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_multiple_goals_per_dataset_allowed(self):
        self._create_goal("Problem 1")
        r = self._create_goal("Problem 2")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AnalysisGoal.objects.filter(dataset=self.dataset).count(), 2)


class GoalListTests(GoalTestBase):
    def test_list_returns_own_goals_only(self):
        self._create_goal("Goal 1")
        self._create_goal("Goal 2")
        other_ds = _make_dataset(self.other)
        self.client.force_authenticate(user=self.other)
        self.client.post("/api/v1/goals/", {"dataset": other_ds.id, "problem_statement": "Theirs"})
        self.client.force_authenticate(user=self.user)

        r = self.client.get("/api/v1/goals/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 2)

    def test_list_includes_question_count(self):
        goal_id = self._create_goal().data["id"]
        AnalysisQuestion.objects.bulk_create([
            AnalysisQuestion(goal_id=goal_id, order=i, question=f"Q{i}?")
            for i in range(3)
        ])
        r = self.client.get("/api/v1/goals/")
        self.assertEqual(r.data[0]["question_count"], 3)
        self.assertNotIn("questions", r.data[0])

    def test_list_does_not_include_questions_array(self):
        self._create_goal()
        r = self.client.get("/api/v1/goals/")
        self.assertNotIn("questions", r.data[0])


class GoalRetrieveTests(GoalTestBase):
    def test_retrieve_includes_nested_questions(self):
        goal_id = self._create_goal().data["id"]
        self.client.post(f"/api/v1/goals/{goal_id}/questions/", {"order": 0, "question": "Q1?"}, format="json")
        self.client.post(f"/api/v1/goals/{goal_id}/questions/", {"order": 1, "question": "Q2?"}, format="json")

        r = self.client.get(f"/api/v1/goals/{goal_id}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["questions"]), 2)

    def test_retrieve_other_user_goal_returns_404(self):
        other_ds = _make_dataset(self.other)
        self.client.force_authenticate(user=self.other)
        other_id = self.client.post("/api/v1/goals/", {"dataset": other_ds.id}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self.client.get(f"/api/v1/goals/{other_id}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class GoalUpdateTests(GoalTestBase):
    def test_patch_problem_statement(self):
        goal_id = self._create_goal("Old").data["id"]
        r = self.client.patch(f"/api/v1/goals/{goal_id}/", {"problem_statement": "New"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["problem_statement"], "New")

    def test_put_not_allowed(self):
        goal_id = self._create_goal().data["id"]
        r = self.client.put(f"/api/v1/goals/{goal_id}/", {"problem_statement": "x", "dataset": self.dataset.id})
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class GoalDeleteTests(GoalTestBase):
    def test_delete_goal_returns_204(self):
        goal_id = self._create_goal().data["id"]
        r = self.client.delete(f"/api/v1/goals/{goal_id}/")
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AnalysisGoal.objects.filter(pk=goal_id).exists())

    def test_delete_cascades_to_questions(self):
        goal_id = self._create_goal().data["id"]
        AnalysisQuestion.objects.create(goal_id=goal_id, order=0, question="Q?")
        self.client.delete(f"/api/v1/goals/{goal_id}/")
        self.assertFalse(AnalysisQuestion.objects.filter(goal_id=goal_id).exists())


# ---------------------------------------------------------------------------
# AnalysisQuestion CRUD
# ---------------------------------------------------------------------------

class QuestionCreateTests(GoalTestBase):
    def test_add_manual_question_returns_201(self):
        goal_id = self._create_goal().data["id"]
        r = self.client.post(
            f"/api/v1/goals/{goal_id}/questions/",
            {"order": 0, "question": "Which region had the highest drop?"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["source"], "manual")
        self.assertEqual(r.data["question"], "Which region had the highest drop?")

    def test_question_order_persisted(self):
        goal_id = self._create_goal().data["id"]
        r = self.client.post(
            f"/api/v1/goals/{goal_id}/questions/",
            {"order": 5, "question": "Test?"},
            format="json",
        )
        self.assertEqual(r.data["order"], 5)

    def test_add_question_to_other_user_goal_returns_404(self):
        other_ds = _make_dataset(self.other)
        self.client.force_authenticate(user=self.other)
        other_id = self.client.post("/api/v1/goals/", {"dataset": other_ds.id}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self.client.post(
            f"/api/v1/goals/{other_id}/questions/",
            {"order": 0, "question": "Hijack?"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_question_limit_returns_400(self):
        goal_id = self._create_goal().data["id"]
        goal = AnalysisGoal.objects.get(pk=goal_id)
        AnalysisQuestion.objects.bulk_create([
            AnalysisQuestion(goal=goal, order=i, question=f"Q{i}?")
            for i in range(20)
        ])
        r = self.client.post(
            f"/api/v1/goals/{goal_id}/questions/",
            {"order": 20, "question": "One too many?"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("20", r.data["detail"])


class QuestionUpdateTests(GoalTestBase):
    def _setup(self):
        goal_id = self._create_goal().data["id"]
        q = AnalysisQuestion.objects.create(goal_id=goal_id, order=0, question="Original?")
        return goal_id, q.id

    def test_patch_question_text(self):
        goal_id, qid = self._setup()
        r = self.client.patch(
            f"/api/v1/goals/{goal_id}/questions/{qid}/",
            {"question": "Updated?"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["question"], "Updated?")

    def test_patch_order(self):
        goal_id, qid = self._setup()
        r = self.client.patch(
            f"/api/v1/goals/{goal_id}/questions/{qid}/",
            {"order": 3},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["order"], 3)

    def test_patch_question_wrong_goal_returns_404(self):
        goal1_id = self._create_goal("G1").data["id"]
        goal2_id = self._create_goal("G2").data["id"]
        q = AnalysisQuestion.objects.create(goal_id=goal1_id, order=0, question="Q?")

        r = self.client.patch(
            f"/api/v1/goals/{goal2_id}/questions/{q.id}/",
            {"question": "x"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class QuestionDeleteTests(GoalTestBase):
    def test_delete_question_returns_204(self):
        goal_id = self._create_goal().data["id"]
        q = AnalysisQuestion.objects.create(goal_id=goal_id, order=0, question="Q?")
        r = self.client.delete(f"/api/v1/goals/{goal_id}/questions/{q.id}/")
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AnalysisQuestion.objects.filter(pk=q.id).exists())

    def test_delete_question_does_not_delete_goal(self):
        goal_id = self._create_goal().data["id"]
        q = AnalysisQuestion.objects.create(goal_id=goal_id, order=0, question="Q?")
        self.client.delete(f"/api/v1/goals/{goal_id}/questions/{q.id}/")
        self.assertTrue(AnalysisGoal.objects.filter(pk=goal_id).exists())


# ---------------------------------------------------------------------------
# Ollama Suggest
# ---------------------------------------------------------------------------

class GoalSuggestTests(GoalTestBase):
    def _sse(self, *tokens):
        return [f"data: {t}\n\n" for t in tokens] + ["data: [DONE]\n\n"]

    @patch("apps.goals.views.stream_suggest_questions")
    def test_suggest_streams_sse(self, mock_stream):
        mock_stream.return_value = iter(self._sse("Q1", ":", " Which region?", "\\n", "Q2", ":", " Revenue trend?"))
        goal_id = self._create_goal().data["id"]
        r = self.client.post(f"/api/v1/goals/{goal_id}/suggest/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r["Content-Type"], "text/event-stream")

    @patch("apps.goals.views.stream_suggest_questions")
    def test_suggest_saves_ai_questions(self, mock_stream):
        mock_stream.return_value = iter(
            self._sse("Q1: Which region dropped?\\nQ2: What is the monthly trend?")
        )
        goal_id = self._create_goal().data["id"]
        self.client.post(f"/api/v1/goals/{goal_id}/suggest/")
        qs = AnalysisQuestion.objects.filter(goal_id=goal_id, source="ai")
        self.assertGreater(qs.count(), 0)

    @patch("apps.goals.views.stream_suggest_questions")
    def test_suggest_other_user_goal_returns_404(self, mock_stream):
        other_ds = _make_dataset(self.other)
        self.client.force_authenticate(user=self.other)
        other_id = self.client.post("/api/v1/goals/", {"dataset": other_ds.id}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self.client.post(f"/api/v1/goals/{other_id}/suggest/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
