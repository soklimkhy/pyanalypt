import io
from unittest.mock import patch

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.datasets.models import Dataset

User = get_user_model()

_VIEWS = "apps.visualization.views"


def _make_df():
    return pd.DataFrame({
        "age":      [25.0, 30.0, 35.0, 40.0, 45.0, 50.0],
        "salary":   [50000.0, 60000.0, 70000.0, 80000.0, 90000.0, 100000.0],
        "city":     ["A", "B", "A", "C", "B", "A"],
        "category": ["X", "Y", "X", "Y", "X", "Y"],
        "score":    [1.1, 2.2, 3.3, 4.4, 5.5, 6.6],
    })


def _csv_upload(df, filename="test.csv"):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read().encode(), content_type="text/csv")


class VizTestBase(APITestCase):
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
        return f"/api/v1/viz/{endpoint}/{pk}/"

    def get(self, endpoint, params=None, df=None, dataset_id=None):
        df = self.df if df is None else df
        with patch(f"{_VIEWS}.get_cached_dataframe", return_value=df):
            return self.client.get(self.url(endpoint, dataset_id), params or {})

    def get_no_df(self, endpoint, params=None):
        with patch(f"{_VIEWS}.get_cached_dataframe", return_value=None):
            return self.client.get(self.url(endpoint), params or {})


# ---------------------------------------------------------------------------
# /viz/bar/
# ---------------------------------------------------------------------------

class BarTests(VizTestBase):
    def test_basic_bar_returns_echarts_structure(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["chart_type"], "bar")
        self.assertIn("xAxis", r.data)
        self.assertIn("yAxis", r.data)
        self.assertIn("series", r.data)
        self.assertEqual(r.data["xAxis"]["type"], "category")
        self.assertEqual(len(r.data["series"]), 1)
        self.assertEqual(r.data["series"][0]["type"], "bar")

    def test_agg_mean(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary", "agg": "mean"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("mean(salary)", r.data["yAxis"]["name"])

    def test_agg_count(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary", "agg": "count"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_with_group_by_returns_multiple_series(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary", "group_by": "category"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(len(r.data["series"]), 1)
        for s in r.data["series"]:
            self.assertEqual(s["type"], "bar")

    def test_missing_x_col_returns_400(self):
        r = self.get("bar", {"y_col": "salary"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("x_col", r.data["detail"])

    def test_missing_y_col_returns_400(self):
        r = self.get("bar", {"x_col": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("y_col", r.data["detail"])

    def test_unknown_column_returns_400(self):
        r = self.get("bar", {"x_col": "nope", "y_col": "salary"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nope", r.data["detail"])

    def test_non_numeric_y_col_returns_400(self):
        r = self.get("bar", {"x_col": "city", "y_col": "category"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("numeric", r.data["detail"])

    def test_invalid_agg_returns_400(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary", "agg": "bad"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("agg", r.data["detail"])

    def test_group_by_not_found_returns_400(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary", "group_by": "nope"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nope", r.data["detail"])

    def test_limit_applied(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary", "limit": "2"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(r.data["xAxis"]["data"]), 2)

    def test_invalid_limit_returns_400(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary", "limit": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_404_for_missing_dataset(self):
        r = self.get("bar", {"x_col": "city", "y_col": "salary"}, dataset_id=99999)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_500_when_df_load_fails(self):
        r = self.get_no_df("bar", {"x_col": "city", "y_col": "salary"})
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("bar"), {"x_col": "city", "y_col": "salary"})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# /viz/line/
# ---------------------------------------------------------------------------

class LineTests(VizTestBase):
    def test_basic_line_returns_echarts_structure(self):
        r = self.get("line", {"x_col": "age", "y_cols": ["salary"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["chart_type"], "line")
        self.assertIn("xAxis", r.data)
        self.assertIn("series", r.data)
        self.assertEqual(r.data["series"][0]["type"], "line")
        self.assertEqual(r.data["series"][0]["name"], "salary")

    def test_multi_y_cols_returns_multiple_series(self):
        r = self.get("line", {"x_col": "age", "y_cols": ["salary", "score"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["series"]), 2)

    def test_sort_false_param(self):
        r = self.get("line", {"x_col": "age", "y_cols": ["salary"], "sort": "false"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_missing_x_col_returns_400(self):
        r = self.get("line", {"y_cols": ["salary"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("x_col", r.data["detail"])

    def test_missing_y_cols_returns_400(self):
        r = self.get("line", {"x_col": "age"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("y_cols", r.data["detail"])

    def test_unknown_column_returns_400(self):
        r = self.get("line", {"x_col": "age", "y_cols": ["nope"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_y_col_returns_400(self):
        r = self.get("line", {"x_col": "age", "y_cols": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("numeric", r.data["detail"])

    def test_404_for_missing_dataset(self):
        r = self.get("line", {"x_col": "age", "y_cols": ["salary"]}, dataset_id=99999)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_500_when_df_load_fails(self):
        r = self.get_no_df("line", {"x_col": "age", "y_cols": ["salary"]})
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# /viz/scatter/
# ---------------------------------------------------------------------------

class ScatterTests(VizTestBase):
    def test_basic_scatter_returns_echarts_structure(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["chart_type"], "scatter")
        self.assertIn("pearson_r", r.data)
        self.assertIn("series", r.data)
        self.assertEqual(r.data["series"][0]["type"], "scatter")
        self.assertIsInstance(r.data["series"][0]["data"][0], list)

    def test_pearson_r_is_float(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsInstance(r.data["pearson_r"], float)

    def test_with_color_by_returns_multiple_series(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary", "color_by": "city"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(len(r.data["series"]), 1)

    def test_sample_param_limits_points(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary", "sample": "3"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(r.data["series"][0]["data"]), 3)

    def test_missing_col_x_returns_400(self):
        r = self.get("scatter", {"col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("col_x", r.data["detail"])

    def test_missing_col_y_returns_400(self):
        r = self.get("scatter", {"col_x": "age"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("col_y", r.data["detail"])

    def test_non_numeric_column_returns_400(self):
        r = self.get("scatter", {"col_x": "city", "col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("numeric", r.data["detail"])

    def test_color_by_not_found_returns_400(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary", "color_by": "nope"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nope", r.data["detail"])

    def test_invalid_sample_returns_400(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary", "sample": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sample_non_integer_returns_400(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary", "sample": "abc"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_404_for_missing_dataset(self):
        r = self.get("scatter", {"col_x": "age", "col_y": "salary"}, dataset_id=99999)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_500_when_df_load_fails(self):
        r = self.get_no_df("scatter", {"col_x": "age", "col_y": "salary"})
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# /viz/histogram/
# ---------------------------------------------------------------------------

class HistogramTests(VizTestBase):
    def test_default_all_numeric_columns(self):
        r = self.get("histogram")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # numeric cols: age, salary, score
        for col in ("age", "salary", "score"):
            self.assertIn(col, r.data)
            self.assertEqual(r.data[col]["chart_type"], "histogram")
            self.assertIn("series", r.data[col])
            self.assertIn("stats", r.data[col])

    def test_explicit_column(self):
        r = self.get("histogram", {"columns": ["age"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("age", r.data)
        self.assertNotIn("salary", r.data)

    def test_custom_bins(self):
        r = self.get("histogram", {"columns": ["age"], "bins": "10"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["age"]["series"][0]["data"]), 10)

    def test_series_type_is_bar(self):
        r = self.get("histogram", {"columns": ["age"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["age"]["series"][0]["type"], "bar")

    def test_stats_fields_present(self):
        r = self.get("histogram", {"columns": ["age"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        for field in ("count", "mean", "std", "min", "max", "skewness", "kurtosis"):
            self.assertIn(field, r.data["age"]["stats"])

    def test_bins_out_of_range_returns_400(self):
        r = self.get("histogram", {"bins": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bins_non_integer_returns_400(self):
        r = self.get("histogram", {"bins": "abc"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.get("histogram", {"columns": ["nope"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nope", r.data["detail"])

    def test_non_numeric_column_returns_400(self):
        r = self.get("histogram", {"columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("numeric", r.data["detail"])

    def test_no_numeric_columns_returns_400(self):
        df_str = pd.DataFrame({"city": ["A", "B"], "country": ["X", "Y"]})
        r = self.get("histogram", df=df_str)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("numeric", r.data["detail"])

    def test_404_for_missing_dataset(self):
        r = self.get("histogram", dataset_id=99999)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_500_when_df_load_fails(self):
        r = self.get_no_df("histogram")
        self.assertEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
