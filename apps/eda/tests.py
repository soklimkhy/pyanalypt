import io
from unittest.mock import patch

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.datasets.models import Dataset

User = get_user_model()

_VIEWS = "apps.eda.views"


def _make_df():
    return pd.DataFrame({
        "age":    [25.0, 30.0, 35.0, 40.0, 45.0, 200.0],
        "salary": [50000.0, 60000.0, 70000.0, 80000.0, 90000.0, 100000.0],
        "city":   ["A", "B", "A", "C", "B", "A"],
        "score":  [1.1, 2.2, None, 4.4, 5.5, 6.6],
    })


def _csv_upload(df, filename="test.csv"):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read().encode(), content_type="text/csv")


class EDATestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pw")
        self.client.force_authenticate(user=self.user)
        self.df = _make_df()
        self.dataset = Dataset.objects.create(
            user=self.user,
            file=_csv_upload(self.df),
            file_name="test.csv",
            file_format="csv",
        )

    def url(self, endpoint, dataset_id=None):
        pk = dataset_id if dataset_id is not None else self.dataset.id
        return f"/api/v1/eda/{endpoint}/{pk}/"

    def get(self, endpoint, params=None, dataset_id=None, df=None):
        df = self.df if df is None else df
        with patch(f"{_VIEWS}.get_cached_dataframe", return_value=df):
            return self.client.get(self.url(endpoint, dataset_id), params or {})

    def get_404(self, endpoint, params=None):
        return self.client.get(self.url(endpoint, dataset_id=99999), params or {})

    def get_no_df(self, endpoint, params=None):
        with patch(f"{_VIEWS}.get_cached_dataframe", return_value=None):
            return self.client.get(self.url(endpoint), params or {})


# ---------------------------------------------------------------------------
# /correlation/
# ---------------------------------------------------------------------------

class CorrelationTests(EDATestBase):
    def test_default_selects_all_numeric(self):
        r = self.get("correlation")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("matrix", r.data)
        self.assertIn("columns", r.data)
        self.assertEqual(r.data["method"], "pearson")
        # only numeric cols: age, salary, score
        self.assertEqual(set(r.data["columns"]), {"age", "salary", "score"})

    def test_explicit_columns(self):
        r = self.get("correlation", {"columns": ["age", "salary"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["columns"], ["age", "salary"])

    def test_spearman_method(self):
        r = self.get("correlation", {"method": "spearman"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["method"], "spearman")

    def test_invalid_method_returns_400(self):
        r = self.get("correlation", {"method": "bad"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_column_returns_400(self):
        r = self.get("correlation", {"columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("numeric", r.data["detail"])

    def test_unknown_column_returns_400(self):
        r = self.get("correlation", {"columns": ["does_not_exist"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_numeric_columns_returns_400(self):
        df_str = pd.DataFrame({"city": ["A", "B"], "country": ["X", "Y"]})
        r = self.get("correlation", df=df_str)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dataset_not_found_returns_404(self):
        r = self.get_404("correlation")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_df_load_failure_returns_500(self):
        r = self.get_no_df("correlation")
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("correlation"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# /distribution/
# ---------------------------------------------------------------------------

class DistributionTests(EDATestBase):
    def test_default(self):
        r = self.get("distribution")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("age", r.data)
        self.assertIn("bins", r.data["age"])

    def test_explicit_columns(self):
        r = self.get("distribution", {"columns": ["age"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("age", r.data)
        self.assertNotIn("salary", r.data)

    def test_custom_bins(self):
        r = self.get("distribution", {"bins": "10"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["age"]["bins"]), 10)

    def test_invalid_bins_type_returns_400(self):
        r = self.get("distribution", {"bins": "not_a_number"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bins_zero_returns_400(self):
        r = self.get("distribution", {"bins": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bins_over_max_returns_400(self):
        r = self.get("distribution", {"bins": "101"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_column_returns_400(self):
        r = self.get("distribution", {"columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.get("distribution", {"columns": ["nope"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_numeric_columns_returns_400(self):
        df_str = pd.DataFrame({"city": ["A", "B"]})
        r = self.get("distribution", df=df_str)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dataset_not_found_returns_404(self):
        r = self.get_404("distribution")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# /value-counts/
# ---------------------------------------------------------------------------

class ValueCountsTests(EDATestBase):
    def test_default_returns_all_columns(self):
        r = self.get("value-counts")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        for col in ["age", "salary", "city", "score"]:
            self.assertIn(col, r.data)

    def test_explicit_columns(self):
        r = self.get("value-counts", {"columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("city", r.data)
        self.assertNotIn("age", r.data)

    def test_custom_top_n(self):
        r = self.get("value-counts", {"columns": ["city"], "top_n": "2"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(r.data["city"]["top_values"]), 2)

    def test_invalid_top_n_returns_400(self):
        r = self.get("value-counts", {"top_n": "abc"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_top_n_zero_returns_400(self):
        r = self.get("value-counts", {"top_n": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_top_n_over_max_returns_400(self):
        r = self.get("value-counts", {"top_n": "101"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.get("value-counts", {"columns": ["missing"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wide_df_is_capped_at_50_columns(self):
        wide_df = pd.DataFrame({f"col_{i}": range(3) for i in range(60)})
        r = self.get("value-counts", df=wide_df)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 50)

    def test_dataset_not_found_returns_404(self):
        r = self.get_404("value-counts")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# /crosstab/
# ---------------------------------------------------------------------------

class CrosstabTests(EDATestBase):
    def test_happy_path(self):
        r = self.get("crosstab", {"col_a": "city", "col_b": "city"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("table", r.data)
        self.assertIn("normalize", r.data)

    def test_normalize_true(self):
        r = self.get("crosstab", {"col_a": "city", "col_b": "city", "normalize": "true"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data["normalize"])

    def test_normalize_false_by_default(self):
        r = self.get("crosstab", {"col_a": "city", "col_b": "city"})
        self.assertFalse(r.data["normalize"])

    def test_normalize_yes_is_not_accepted(self):
        r = self.get("crosstab", {"col_a": "city", "col_b": "city", "normalize": "yes"})
        self.assertFalse(r.data["normalize"])

    def test_missing_col_a_returns_400(self):
        r = self.get("crosstab", {"col_b": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_col_b_returns_400(self):
        r = self.get("crosstab", {"col_a": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.get("crosstab", {"col_a": "city", "col_b": "nonexistent"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_high_cardinality_returns_400(self):
        high_card_df = pd.DataFrame({
            "a": list(range(60)),
            "b": ["x"] * 60,
        })
        r = self.get("crosstab", {"col_a": "a", "col_b": "b"}, df=high_card_df)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unique values", r.data["detail"])

    def test_dataset_not_found_returns_404(self):
        r = self.get_404("crosstab")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# /outlier-summary/
# ---------------------------------------------------------------------------

class OutlierSummaryTests(EDATestBase):
    def test_default_iqr(self):
        r = self.get("outlier-summary")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["method"], "iqr")
        self.assertIn("per_column", r.data)

    def test_zscore_method(self):
        r = self.get("outlier-summary", {"method": "zscore"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["method"], "zscore")

    def test_invalid_method_returns_400(self):
        r = self.get("outlier-summary", {"method": "mad"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_threshold_type_returns_400(self):
        r = self.get("outlier-summary", {"threshold": "abc"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_zero_returns_400(self):
        r = self.get("outlier-summary", {"threshold": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_negative_returns_400(self):
        r = self.get("outlier-summary", {"threshold": "-1"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_over_max_returns_400(self):
        r = self.get("outlier-summary", {"threshold": "11"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_at_max_is_accepted(self):
        r = self.get("outlier-summary", {"threshold": "10"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_custom_threshold(self):
        r = self.get("outlier-summary", {"threshold": "3"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["threshold"], 3.0)

    def test_dataset_not_found_returns_404(self):
        r = self.get_404("outlier-summary")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# /missing-heatmap/
# ---------------------------------------------------------------------------

class MissingHeatmapTests(EDATestBase):
    def test_happy_path(self):
        r = self.get("missing-heatmap")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("per_column", r.data)
        self.assertIn("total_rows", r.data)
        self.assertIn("worst_rows", r.data)

    def test_large_df_is_sampled(self):
        large_df = pd.DataFrame({
            "a": range(60_000),
            "b": [None] * 60_000,
        })
        r = self.get("missing-heatmap", df=large_df)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["total_rows"], 50_000)

    def test_dataset_not_found_returns_404(self):
        r = self.get_404("missing-heatmap")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_df_load_failure_returns_500(self):
        r = self.get_no_df("missing-heatmap")
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# /pairwise/
# ---------------------------------------------------------------------------

class PairwiseTests(EDATestBase):
    def test_happy_path(self):
        r = self.get("pairwise", {"col_x": "age", "col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("points", r.data)
        self.assertIn("pearson_r", r.data)
        self.assertEqual(r.data["col_x"], "age")
        self.assertEqual(r.data["col_y"], "salary")

    def test_missing_col_x_returns_400(self):
        r = self.get("pairwise", {"col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_col_y_returns_400(self):
        r = self.get("pairwise", {"col_x": "age"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.get("pairwise", {"col_x": "age", "col_y": "nonexistent"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_column_returns_400(self):
        r = self.get("pairwise", {"col_x": "age", "col_y": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("numeric", r.data["detail"])

    def test_both_non_numeric_returns_400(self):
        r = self.get("pairwise", {"col_x": "city", "col_y": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_sample_type_returns_400(self):
        r = self.get("pairwise", {"col_x": "age", "col_y": "salary", "sample": "abc"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sample_zero_returns_400(self):
        r = self.get("pairwise", {"col_x": "age", "col_y": "salary", "sample": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sample_over_max_returns_400(self):
        r = self.get("pairwise", {"col_x": "age", "col_y": "salary", "sample": "5001"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_custom_sample_limits_points(self):
        large_df = pd.DataFrame({
            "x": range(1000),
            "y": range(1000),
        })
        r = self.get("pairwise", {"col_x": "x", "col_y": "y", "sample": "10"}, df=large_df)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["sampled"], 10)
        self.assertEqual(len(r.data["points"]), 10)

    def test_dataset_not_found_returns_404(self):
        r = self.get_404("pairwise")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("pairwise"), {"col_x": "age", "col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
