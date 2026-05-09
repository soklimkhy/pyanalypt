import base64
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.datasets.models import Dataset
from .models import Report, ReportItem

User = get_user_model()

# Minimal 1x1 white PNG as base64 for image tests
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
)


def _make_dataset(user):
    buf = io.BytesIO(b"a,b\n1,2\n3,4")
    return Dataset.objects.create(
        user=user,
        file=SimpleUploadedFile("t.csv", buf.read(), content_type="text/csv"),
        file_name="t.csv",
        file_format="csv",
    )


class ReportTestBase(APITestCase):
    def setUp(self):
        self.user  = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.client.force_authenticate(user=self.user)
        self.dataset = _make_dataset(self.user)

    def _create_report(self, title="My Report", description=""):
        return self.client.post("/api/v1/reports/", {
            "title": title,
            "description": description,
            "dataset": self.dataset.id,
        })

    def _create_item(self, report_id, **kwargs):
        payload = {
            "order": 0,
            "chart_type": "bar",
            "annotation": "Insight here.",
            "chart_image": _PNG_B64,
            "chart_params": {"x_col": "city", "y_col": "salary"},
        }
        payload.update(kwargs)
        return self.client.post(f"/api/v1/reports/{report_id}/items/", payload, format="json")


# ---------------------------------------------------------------------------
# Report CRUD
# ---------------------------------------------------------------------------

class ReportCreateTests(ReportTestBase):
    def test_create_report_returns_201(self):
        r = self._create_report()
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["title"], "My Report")
        self.assertEqual(r.data["item_count"], 0)
        self.assertEqual(r.data["items"], [])

    def test_create_report_without_dataset(self):
        r = self.client.post("/api/v1/reports/", {"title": "No Dataset"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(r.data["dataset"])

    def test_create_report_missing_title_returns_400(self):
        r = self.client.post("/api/v1/reports/", {"description": "No title"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self._create_report()
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


class ReportListTests(ReportTestBase):
    def test_list_returns_only_own_reports(self):
        self._create_report("Mine 1")
        self._create_report("Mine 2")
        # other user's report — should not appear
        self.client.force_authenticate(user=self.other)
        self.client.post("/api/v1/reports/", {"title": "Theirs"})
        self.client.force_authenticate(user=self.user)

        r = self.client.get("/api/v1/reports/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 2)
        titles = {rep["title"] for rep in r.data}
        self.assertSetEqual(titles, {"Mine 1", "Mine 2"})

    def test_list_includes_item_count(self):
        report_r = self._create_report()
        rid = report_r.data["id"]
        self._create_item(rid)
        self._create_item(rid)

        r = self.client.get("/api/v1/reports/")
        self.assertEqual(r.data[0]["item_count"], 2)
        self.assertNotIn("items", r.data[0])  # list serializer omits items


class ReportRetrieveTests(ReportTestBase):
    def test_retrieve_includes_nested_items(self):
        rid = self._create_report().data["id"]
        self._create_item(rid, annotation="First insight")
        self._create_item(rid, annotation="Second insight")

        r = self.client.get(f"/api/v1/reports/{rid}/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["items"]), 2)

    def test_retrieve_other_user_report_returns_404(self):
        self.client.force_authenticate(user=self.other)
        other_rid = self.client.post("/api/v1/reports/", {"title": "Other"}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self.client.get(f"/api/v1/reports/{other_rid}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_nonexistent_returns_404(self):
        r = self.client.get("/api/v1/reports/99999/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class ReportUpdateTests(ReportTestBase):
    def test_partial_update_title(self):
        rid = self._create_report("Old Title").data["id"]
        r = self.client.patch(f"/api/v1/reports/{rid}/", {"title": "New Title"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["title"], "New Title")

    def test_partial_update_description_only(self):
        rid = self._create_report().data["id"]
        r = self.client.patch(f"/api/v1/reports/{rid}/", {"description": "Updated desc"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["description"], "Updated desc")

    def test_update_other_user_report_returns_404(self):
        self.client.force_authenticate(user=self.other)
        other_rid = self.client.post("/api/v1/reports/", {"title": "Other"}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self.client.patch(f"/api/v1/reports/{other_rid}/", {"title": "Hijacked"})
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class ReportDeleteTests(ReportTestBase):
    def test_delete_report_returns_204(self):
        rid = self._create_report().data["id"]
        r = self.client.delete(f"/api/v1/reports/{rid}/")
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Report.objects.filter(pk=rid).exists())

    def test_delete_cascades_to_items(self):
        rid = self._create_report().data["id"]
        self._create_item(rid)
        self.client.delete(f"/api/v1/reports/{rid}/")
        self.assertFalse(ReportItem.objects.filter(report_id=rid).exists())

    def test_delete_other_user_report_returns_404(self):
        self.client.force_authenticate(user=self.other)
        other_rid = self.client.post("/api/v1/reports/", {"title": "Other"}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self.client.delete(f"/api/v1/reports/{other_rid}/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Report Items
# ---------------------------------------------------------------------------

class ReportItemCreateTests(ReportTestBase):
    def test_add_item_returns_201(self):
        rid = self._create_report().data["id"]
        r = self._create_item(rid)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["annotation"], "Insight here.")
        self.assertEqual(r.data["chart_type"], "bar")

    def test_add_text_only_item(self):
        rid = self._create_report().data["id"]
        r = self._create_item(rid, chart_type="text", chart_image="", chart_params=None)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["chart_type"], "text")

    def test_item_order_field_persisted(self):
        rid = self._create_report().data["id"]
        r = self._create_item(rid, order=5)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["order"], 5)

    def test_add_item_to_other_user_report_returns_404(self):
        self.client.force_authenticate(user=self.other)
        other_rid = self.client.post("/api/v1/reports/", {"title": "Other"}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self._create_item(other_rid)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_item_limit_returns_400(self):
        rid = self._create_report().data["id"]
        report = Report.objects.get(pk=rid)
        ReportItem.objects.bulk_create([
            ReportItem(report=report, order=i, annotation=f"item {i}")
            for i in range(50)
        ])
        r = self._create_item(rid)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("50", r.data["detail"])


class ReportItemUpdateTests(ReportTestBase):
    def test_patch_annotation(self):
        rid = self._create_report().data["id"]
        iid = self._create_item(rid).data["id"]

        r = self.client.patch(
            f"/api/v1/reports/{rid}/items/{iid}/",
            {"annotation": "Updated insight"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["annotation"], "Updated insight")

    def test_patch_order(self):
        rid = self._create_report().data["id"]
        iid = self._create_item(rid, order=0).data["id"]

        r = self.client.patch(f"/api/v1/reports/{rid}/items/{iid}/", {"order": 3}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["order"], 3)

    def test_patch_item_wrong_report_returns_404(self):
        rid1 = self._create_report("R1").data["id"]
        rid2 = self._create_report("R2").data["id"]
        iid = self._create_item(rid1).data["id"]

        r = self.client.patch(f"/api/v1/reports/{rid2}/items/{iid}/", {"annotation": "x"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class ReportItemDeleteTests(ReportTestBase):
    def test_delete_item_returns_204(self):
        rid = self._create_report().data["id"]
        iid = self._create_item(rid).data["id"]

        r = self.client.delete(f"/api/v1/reports/{rid}/items/{iid}/")
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ReportItem.objects.filter(pk=iid).exists())

    def test_delete_item_does_not_delete_report(self):
        rid = self._create_report().data["id"]
        iid = self._create_item(rid).data["id"]
        self.client.delete(f"/api/v1/reports/{rid}/items/{iid}/")
        self.assertTrue(Report.objects.filter(pk=rid).exists())


# ---------------------------------------------------------------------------
# PDF Export
# ---------------------------------------------------------------------------

class ReportExportTests(ReportTestBase):
    def test_export_returns_pdf_content_type(self):
        rid = self._create_report("Sales Report").data["id"]
        self._create_item(rid, annotation="Revenue is up 20%.")

        r = self.client.get(f"/api/v1/reports/{rid}/export/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("Sales_Report.pdf", r["Content-Disposition"])

    def test_export_pdf_has_content(self):
        rid = self._create_report().data["id"]
        self._create_item(rid)

        r = self.client.get(f"/api/v1/reports/{rid}/export/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(len(r.content), 100)
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_export_empty_report_returns_pdf(self):
        rid = self._create_report("Empty").data["id"]
        r = self.client.get(f"/api/v1/reports/{rid}/export/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_export_other_user_report_returns_404(self):
        self.client.force_authenticate(user=self.other)
        other_rid = self.client.post("/api/v1/reports/", {"title": "Other"}).data["id"]
        self.client.force_authenticate(user=self.user)

        r = self.client.get(f"/api/v1/reports/{other_rid}/export/")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_export_with_chart_image_returns_pdf(self):
        rid = self._create_report().data["id"]
        self._create_item(rid, chart_image=_PNG_B64, annotation="Chart with image.")

        r = self.client.get(f"/api/v1/reports/{rid}/export/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.content.startswith(b"%PDF"))
