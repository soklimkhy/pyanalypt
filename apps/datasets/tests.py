import io

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Dataset, DatasetActivityLog

User = get_user_model()

TEST_PASSWORD = "test-pw-123"  # noqa: S105


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_file(filename="test.csv"):
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read().encode(), content_type="text/csv")


def _xlsx_file(filename="test.xlsx"):
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return SimpleUploadedFile(
        filename,
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _make_dataset(user, filename="data.csv"):
    ds = Dataset.objects.create(
        user=user,
        file=_csv_file(filename),
        file_name=filename,
        file_format="csv",
    )
    return ds


class DatasetTestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password=TEST_PASSWORD)
        self.other = User.objects.create_user(username="other", password=TEST_PASSWORD)
        self.client.force_authenticate(user=self.user)
        self.dataset = _make_dataset(self.user)

    def url(self, name, pk=None):
        if pk is not None:
            return reverse(name, args=[pk])
        return reverse(name)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class UploadTests(DatasetTestBase):
    def test_upload_csv(self):
        r = self.client.post(
            self.url("dataset-upload"),
            {"file": _csv_file()},
            format="multipart",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["file_format"], "csv")
        self.assertIsNotNone(r.data["file_size"])

    def test_upload_xlsx(self):
        r = self.client.post(
            self.url("dataset-upload"),
            {"file": _xlsx_file()},
            format="multipart",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["file_format"], "xlsx")

    def test_upload_logs_activity(self):
        before = DatasetActivityLog.objects.filter(user=self.user, action="UPLOAD").count()
        self.client.post(
            self.url("dataset-upload"),
            {"file": _csv_file()},
            format="multipart",
        )
        after = DatasetActivityLog.objects.filter(user=self.user, action="UPLOAD").count()
        self.assertEqual(after, before + 1)

    def test_upload_requires_auth(self):
        self.client.force_authenticate(user=None)
        r = self.client.post(
            self.url("dataset-upload"),
            {"file": _csv_file()},
            format="multipart",
        )
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_invalid_extension(self):
        bad_file = SimpleUploadedFile("bad.txt", b"hello", content_type="text/plain")
        r = self.client.post(
            self.url("dataset-upload"),
            {"file": bad_file},
            format="multipart",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_missing_file(self):
        r = self.client.post(self.url("dataset-upload"), {}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class ListTests(DatasetTestBase):
    def test_list_returns_own_datasets(self):
        r = self.client.get(self.url("dataset-list"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        self.assertTrue(any(d["id"] == self.dataset.id for d in results))

    def test_list_excludes_other_users_datasets(self):
        other_ds = _make_dataset(self.other, "other.csv")
        r = self.client.get(self.url("dataset-list"))
        results = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        self.assertFalse(any(d["id"] == other_ds.id for d in results))

    def test_list_requires_auth(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("dataset-list"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------

class RetrieveTests(DatasetTestBase):
    def test_retrieve_own_dataset(self):
        r = self.client.get(self.url("dataset-detail", self.dataset.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["id"], self.dataset.id)
        self.assertEqual(r.data["file_name"], self.dataset.file_name)

    def test_retrieve_other_users_dataset_returns_404(self):
        other_ds = _make_dataset(self.other)
        r = self.client.get(self.url("dataset-detail", other_ds.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_nonexistent_returns_404(self):
        r = self.client.get(self.url("dataset-detail", 99999))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_requires_auth(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("dataset-detail", self.dataset.id))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class DeleteTests(DatasetTestBase):
    def test_delete_own_dataset(self):
        r = self.client.delete(self.url("dataset-detail", self.dataset.id))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Dataset.objects.filter(id=self.dataset.id).exists())

    def test_delete_logs_activity(self):
        self.client.delete(self.url("dataset-detail", self.dataset.id))
        self.assertTrue(
            DatasetActivityLog.objects.filter(
                user=self.user,
                action="DELETE",
                dataset_name_snap=self.dataset.file_name,
            ).exists()
        )

    def test_delete_other_users_dataset_returns_404(self):
        other_ds = _make_dataset(self.other)
        r = self.client.delete(self.url("dataset-detail", other_ds.id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Dataset.objects.filter(id=other_ds.id).exists())

    def test_delete_requires_auth(self):
        self.client.force_authenticate(user=None)
        r = self.client.delete(self.url("dataset-detail", self.dataset.id))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------

class RenameTests(DatasetTestBase):
    def test_rename_success(self):
        r = self.client.patch(
            self.url("dataset-rename", self.dataset.id),
            {"file_name": "renamed.csv"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["file_name"], "renamed.csv")
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.file_name, "renamed.csv")

    def test_rename_logs_activity(self):
        self.client.patch(
            self.url("dataset-rename", self.dataset.id),
            {"file_name": "renamed.csv"},
            format="json",
        )
        self.assertTrue(
            DatasetActivityLog.objects.filter(user=self.user, action="RENAME").exists()
        )

    def test_rename_missing_file_name(self):
        r = self.client.patch(
            self.url("dataset-rename", self.dataset.id),
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rename_blank_file_name(self):
        r = self.client.patch(
            self.url("dataset-rename", self.dataset.id),
            {"file_name": "   "},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rename_other_users_dataset_returns_404(self):
        other_ds = _make_dataset(self.other)
        r = self.client.patch(
            self.url("dataset-rename", other_ds.id),
            {"file_name": "hacked.csv"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportTests(DatasetTestBase):
    def test_export_csv(self):
        r = self.client.get(self.url("dataset-export", self.dataset.id), {"format": "csv"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", r["Content-Type"])

    def test_export_json(self):
        r = self.client.get(self.url("dataset-export", self.dataset.id), {"format": "json"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("application/json", r["Content-Type"])

    def test_export_xlsx(self):
        r = self.client.get(self.url("dataset-export", self.dataset.id), {"format": "xlsx"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("spreadsheetml", r["Content-Type"])

    def test_export_default_format(self):
        r = self.client.get(self.url("dataset-export", self.dataset.id))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_export_unsupported_format(self):
        r = self.client.get(self.url("dataset-export", self.dataset.id), {"format": "pdf"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_logs_activity(self):
        self.client.get(self.url("dataset-export", self.dataset.id), {"format": "csv"})
        self.assertTrue(
            DatasetActivityLog.objects.filter(user=self.user, action="EXPORT").exists()
        )

    def test_export_other_users_dataset_returns_404(self):
        other_ds = _make_dataset(self.other)
        r = self.client.get(self.url("dataset-export", other_ds.id), {"format": "csv"})
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------

class DuplicateTests(DatasetTestBase):
    def test_duplicate_same_format(self):
        r = self.client.post(
            self.url("dataset-duplicate", self.dataset.id),
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["file_format"], "csv")
        self.assertIn("_copy", r.data["file_name"])

    def test_duplicate_with_custom_name(self):
        r = self.client.post(
            self.url("dataset-duplicate", self.dataset.id),
            {"new_file_name": "my_copy"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["file_name"], "my_copy")

    def test_duplicate_format_conversion(self):
        r = self.client.post(
            self.url("dataset-duplicate", self.dataset.id),
            {"format": "json"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["file_format"], "json")

    def test_duplicate_unsupported_format(self):
        r = self.client.post(
            self.url("dataset-duplicate", self.dataset.id),
            {"format": "pdf"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_logs_activity(self):
        self.client.post(
            self.url("dataset-duplicate", self.dataset.id),
            {},
            format="json",
        )
        self.assertTrue(
            DatasetActivityLog.objects.filter(user=self.user, action="DUPLICATE").exists()
        )

    def test_duplicate_other_users_dataset_returns_404(self):
        other_ds = _make_dataset(self.other)
        r = self.client.post(
            self.url("dataset-duplicate", other_ds.id),
            {},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Activity Logs
# ---------------------------------------------------------------------------

class ActivityLogTests(DatasetTestBase):
    def setUp(self):
        super().setUp()
        DatasetActivityLog.objects.create(
            user=self.user,
            dataset=self.dataset,
            dataset_name_snap=self.dataset.file_name,
            action="UPLOAD",
            details={},
        )

    def test_activity_logs_returns_own_logs(self):
        r = self.client.get(self.url("dataset-activity-logs"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        self.assertGreaterEqual(len(results), 1)

    def test_activity_logs_filter_by_dataset(self):
        other_ds = _make_dataset(self.user, "other.csv")
        DatasetActivityLog.objects.create(
            user=self.user,
            dataset=other_ds,
            dataset_name_snap="other.csv",
            action="RENAME",
            details={},
        )
        r = self.client.get(
            self.url("dataset-activity-logs"),
            {"dataset_id": self.dataset.id},
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.data.get("results", r.data) if isinstance(r.data, dict) else r.data
        for log in results:
            self.assertEqual(log["dataset"], self.dataset.id)

    def test_activity_logs_invalid_dataset_id(self):
        r = self.client.get(
            self.url("dataset-activity-logs"),
            {"dataset_id": "abc"},
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_activity_logs_other_users_dataset_returns_404(self):
        other_ds = _make_dataset(self.other)
        r = self.client.get(
            self.url("dataset-activity-logs"),
            {"dataset_id": other_ds.id},
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_activity_logs_requires_auth(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("dataset-activity-logs"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Workspace Summary
# ---------------------------------------------------------------------------

class WorkspaceSummaryTests(DatasetTestBase):
    def test_summary_returns_expected_keys(self):
        r = self.client.get(self.url("dataset-workspace-summary"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("stats", r.data)
        self.assertIn("recent_datasets", r.data)
        self.assertIn("activity_feed", r.data)
        self.assertIn("chart_data", r.data)

    def test_summary_stats_keys(self):
        r = self.client.get(self.url("dataset-workspace-summary"))
        stats = r.data["stats"]
        for key in ("total_datasets", "total_analyses", "total_insights", "storage_used"):
            self.assertIn(key, stats)

    def test_summary_requires_auth(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("dataset-workspace-summary"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_summary_counts_own_datasets_only(self):
        _make_dataset(self.other, "other.csv")
        r = self.client.get(self.url("dataset-workspace-summary"))
        total = int(r.data["stats"]["total_datasets"]["value"])
        user_count = Dataset.objects.filter(user=self.user).count()
        self.assertEqual(total, user_count)
