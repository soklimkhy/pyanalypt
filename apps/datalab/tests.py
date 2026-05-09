import io

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.datasets.models import Dataset

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_upload(df, filename="test.csv"):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read().encode(), content_type="text/csv")


def _base_df():
    """Shared DataFrame for most tests. c = a + b for formula tests."""
    return pd.DataFrame({
        "id":    [1, 2, 3, 4, 5, 6],
        "name":  ["Alice", "Bob", "Charlie", "Dave", "Eve", None],
        "age":   [25.0, 30.0, 35.0, None, 45.0, 50.0],
        "score": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        "city":  ["NYC", "LA", "NYC", "Chicago", "LA", "NYC"],
        "a":     [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "b":     [2.0, 4.0, 6.0, 8.0, 10.0, 12.0],
        "c":     [3.0, 6.0, 9.0, 12.0, 15.0, 18.0],
    })


class DatalabTestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pw")
        self.client.force_authenticate(user=self.user)
        self.dataset = Dataset.objects.create(
            user=self.user,
            file=_csv_upload(_base_df()),
            file_name="test.csv",
            file_format="csv",
        )

    def url(self, name, dataset_id=None):
        return reverse(f"datalab-{name}", args=[dataset_id or self.dataset.id])

    def post(self, name, data, dataset_id=None):
        return self.client.post(self.url(name, dataset_id), data, format="json")

    def patch(self, name, data, dataset_id=None):
        return self.client.patch(self.url(name, dataset_id), data, format="json")

    def get(self, name, params=None, dataset_id=None):
        return self.client.get(self.url(name, dataset_id), params or {})


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

class PreviewTests(DatalabTestBase):
    def test_default_preview(self):
        r = self.get("preview")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["total_rows"], 6)
        self.assertEqual(r.data["total_columns"], 8)
        self.assertIn("rows", r.data)
        self.assertFalse(r.data["truncated"])

    def test_preview_with_limit(self):
        r = self.get("preview", {"limit": "2"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["rows"]), 2)
        self.assertTrue(r.data["truncated"])

    def test_limit_zero_returns_all_rows(self):
        r = self.get("preview", {"limit": "0"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["rows"]), 6)

    def test_invalid_limit_returns_400(self):
        r = self.get("preview", {"limit": "bad"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_limit_returns_400(self):
        r = self.get("preview", {"limit": "-1"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_limit_exceeds_max_returns_400(self):
        r = self.get("preview", {"limit": "99999"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dataset_not_found_returns_404(self):
        r = self.get("preview", dataset_id=99999)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(self.url("preview"))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_other_users_dataset_returns_404(self):
        other = User.objects.create_user(username="other", password="pw")
        ds = Dataset.objects.create(
            user=other, file=_csv_upload(_base_df()), file_name="o.csv", file_format="csv"
        )
        r = self.get("preview", dataset_id=ds.id)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Inspect & Describe
# ---------------------------------------------------------------------------

class InspectDescribeTests(DatalabTestBase):
    def test_inspect_returns_column_stats(self):
        r = self.get("inspect")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("info", r.data)
        cols = {c["column"] for c in r.data["info"]["columns"]}
        self.assertIn("age", cols)
        self.assertIn("null_count", r.data["info"]["columns"][0])

    def test_describe_returns_stats(self):
        r = self.get("describe")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("columns", r.data)

    def test_inspect_dataset_not_found_returns_404(self):
        r = self.get("inspect", dataset_id=99999)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# detect_outliers
# ---------------------------------------------------------------------------

class DetectOutliersTests(DatalabTestBase):
    def test_iqr_default(self):
        r = self.get("detect-outliers", {"columns": "score"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("columns", r.data)
        self.assertEqual(r.data["method"], "iqr")

    def test_zscore_method(self):
        r = self.get("detect-outliers", {"columns": "score", "method": "zscore"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["method"], "zscore")

    def test_invalid_method_returns_400(self):
        r = self.get("detect-outliers", {"columns": "score", "method": "mad"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_zero_returns_400(self):
        r = self.get("detect-outliers", {"columns": "score", "threshold": "0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_over_max_returns_400(self):
        r = self.get("detect-outliers", {"columns": "score", "threshold": "11"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_column_returns_400(self):
        r = self.get("detect-outliers", {"columns": "name"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# cast_columns
# ---------------------------------------------------------------------------

class CastColumnsTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("cast", {"casts": {"id": "integer"}, "force": True})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.dataset.refresh_from_db()
        self.assertIn("id", self.dataset.column_casts)

    def test_missing_casts_returns_400(self):
        r = self.post("cast", {})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_casts_not_dict_returns_400(self):
        r = self.post("cast", {"casts": ["age", "integer"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_cast_type_returns_400(self):
        r = self.post("cast", {"casts": {"age": "foobar"}})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("foobar", r.data["detail"])

    def test_unknown_column_returns_400(self):
        r = self.post("cast", {"casts": {"nonexistent": "integer"}})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_failure_flag_present(self):
        # id (float-like ints) → integer should succeed; name (strings) → integer should fail
        r = self.post("cast", {"casts": {"id": "integer", "name": "integer"}, "force": True})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("partial_failure", r.data)
        self.assertIn("updated_columns", r.data)

    def test_all_success_partial_failure_is_false(self):
        r = self.post("cast", {"casts": {"id": "float"}, "force": True})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertFalse(r.data["partial_failure"])

    def test_all_casts_fail_returns_422(self):
        # name → integer is impossible; nothing succeeds
        r = self.post("cast", {"casts": {"name": "integer"}})
        self.assertEqual(r.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("detail", r.data)
        self.assertIn("updated_columns", r.data)


# ---------------------------------------------------------------------------
# update_cell
# ---------------------------------------------------------------------------

class UpdateCellTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.patch("update-cell", {"row_index": 0, "column": "score", "value": 99.0})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["column"], "score")
        self.assertEqual(r.data["row_index"], 0)

    def test_missing_column_returns_400(self):
        r = self.patch("update-cell", {"row_index": 0, "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_row_index_returns_400(self):
        r = self.patch("update-cell", {"column": "score", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_row_index_returns_400(self):
        r = self.patch("update-cell", {"row_index": -1, "column": "score", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_row_index_not_int_returns_400(self):
        r = self.patch("update-cell", {"row_index": "bad", "column": "score", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_column_not_found_returns_400(self):
        r = self.patch("update-cell", {"row_index": 0, "column": "nonexistent", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_row_out_of_range_returns_400(self):
        r = self.patch("update-cell", {"row_index": 9999, "column": "score", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# rename_column
# ---------------------------------------------------------------------------

class RenameColumnTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("rename-column", {"old_name": "city", "new_name": "location"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("location", r.data["columns"])
        self.assertNotIn("city", r.data["columns"])

    def test_missing_old_name_returns_400(self):
        r = self.post("rename-column", {"new_name": "location"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_new_name_returns_400(self):
        r = self.post("rename-column", {"old_name": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_name_returns_400(self):
        r = self.post("rename-column", {"old_name": "city", "new_name": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_old_name_not_found_returns_400(self):
        r = self.post("rename-column", {"old_name": "nonexistent", "new_name": "foo"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_name_already_exists_returns_400(self):
        r = self.post("rename-column", {"old_name": "city", "new_name": "name"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# drop_duplicates
# ---------------------------------------------------------------------------

class DropDuplicatesTests(DatalabTestBase):
    def test_no_duplicates_returns_zero_dropped(self):
        r = self.post("drop-duplicates", {"mode": "all_first"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["rows_dropped"], 0)

    def test_invalid_mode_returns_400(self):
        r = self.post("drop-duplicates", {"mode": "bad_mode"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_subset_keep_without_subset_returns_400(self):
        r = self.post("drop-duplicates", {"mode": "subset_keep"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_subset_keep_invalid_keep_returns_400(self):
        r = self.post("drop-duplicates", {"mode": "subset_keep", "subset": ["city"], "keep": "invalid"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_subset_column_returns_400(self):
        r = self.post("drop-duplicates", {"mode": "subset_keep", "subset": ["nonexistent"], "keep": "first"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_actual_duplicates_are_dropped(self):
        df = pd.concat([_base_df(), _base_df().iloc[[0]]], ignore_index=True)
        ds = Dataset.objects.create(
            user=self.user, file=_csv_upload(df), file_name="dups.csv", file_format="csv"
        )
        r = self.client.post(
            reverse("datalab-drop-duplicates", args=[ds.id]),
            {"mode": "all_first"}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(r.data["rows_dropped"], 0)


# ---------------------------------------------------------------------------
# replace_values
# ---------------------------------------------------------------------------

class ReplaceValuesTests(DatalabTestBase):
    def test_with_explicit_columns(self):
        r = self.post("replace-values", {"replacements": {"NYC": "New York"}, "columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(r.data["cells_replaced"], 0)

    def test_global_without_confirm_returns_400(self):
        r = self.post("replace-values", {"replacements": {"NYC": "New York"}})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("confirm_global", r.data["detail"])

    def test_global_with_confirm_global_true_succeeds(self):
        r = self.post("replace-values", {"replacements": {"NYC": "New York"}, "confirm_global": True})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_missing_replacements_returns_400(self):
        r = self.post("replace-values", {"columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_replacements_not_dict_returns_400(self):
        r = self.post("replace-values", {"replacements": ["NYC", "New York"], "columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("replace-values", {"replacements": {"NYC": "NY"}, "columns": ["nonexistent"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# drop_nulls
# ---------------------------------------------------------------------------

class DropNullsTests(DatalabTestBase):
    def test_drop_rows_any(self):
        r = self.post("drop-nulls", {"axis": "rows", "how": "any"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("rows_dropped", r.data)
        self.assertGreater(r.data["rows_dropped"], 0)

    def test_drop_columns_with_thresh(self):
        r = self.post("drop-nulls", {"axis": "columns", "thresh_pct": 50})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_invalid_axis_returns_400(self):
        r = self.post("drop-nulls", {"axis": "diagonal"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_how_returns_400(self):
        r = self.post("drop-nulls", {"axis": "rows", "how": "some"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_columns_axis_without_thresh_pct_returns_400(self):
        r = self.post("drop-nulls", {"axis": "columns"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_thresh_pct_out_of_range_returns_400(self):
        r = self.post("drop-nulls", {"axis": "columns", "thresh_pct": 150})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# fill_nulls
# ---------------------------------------------------------------------------

class FillNullsTests(DatalabTestBase):
    def test_constant_fill(self):
        r = self.post("fill-nulls", {"strategy": "constant", "columns": ["name"], "value": "Unknown"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["cells_filled"], 1)

    def test_mean_fill_numeric(self):
        r = self.post("fill-nulls", {"strategy": "mean", "columns": ["age"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(r.data["cells_filled"], 0)

    def test_invalid_strategy_returns_400(self):
        r = self.post("fill-nulls", {"strategy": "interpolate"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_constant_without_value_returns_400(self):
        r = self.post("fill-nulls", {"strategy": "constant"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("fill-nulls", {"strategy": "constant", "columns": ["nonexistent"], "value": "x"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_file_reflects_fill(self):
        self.post("fill-nulls", {"strategy": "constant", "columns": ["name"], "value": "Unknown"})
        r = self.get("preview")
        names = [row["name"] for row in r.data["rows"]]
        self.assertNotIn(None, names)
        self.assertIn("Unknown", names)


# ---------------------------------------------------------------------------
# trim_outliers
# ---------------------------------------------------------------------------

class TrimOutliersTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("trim-outliers", {"columns": ["score"], "method": "zscore", "threshold": 2.0})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("rows_before", r.data)
        self.assertIn("rows_dropped", r.data)

    def test_invalid_method_returns_400(self):
        r = self.post("trim-outliers", {"columns": ["score"], "method": "bad"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_zero_returns_400(self):
        r = self.post("trim-outliers", {"columns": ["score"], "threshold": 0})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_threshold_over_max_returns_400(self):
        r = self.post("trim-outliers", {"columns": ["score"], "threshold": 11})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_column_returns_400(self):
        r = self.post("trim-outliers", {"columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("trim-outliers", {"columns": ["nonexistent"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# impute_outliers
# ---------------------------------------------------------------------------

class ImputeOutliersTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("impute-outliers", {"columns": ["score"], "strategy": "median"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("cells_imputed", r.data)

    def test_invalid_strategy_returns_400(self):
        r = self.post("impute-outliers", {"columns": ["score"], "strategy": "winsorize"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_method_returns_400(self):
        r = self.post("impute-outliers", {"columns": ["score"], "method": "mad"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("impute-outliers", {"columns": ["nonexistent"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# cap_outliers
# ---------------------------------------------------------------------------

class CapOutliersTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("cap-outliers", {"columns": ["score"], "lower_pct": 10, "upper_pct": 90})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("cells_capped", r.data)

    def test_inverted_percentiles_returns_400(self):
        r = self.post("cap-outliers", {"columns": ["score"], "lower_pct": 90, "upper_pct": 10})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upper_over_100_returns_400(self):
        r = self.post("cap-outliers", {"columns": ["score"], "lower_pct": 5, "upper_pct": 110})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_equal_percentiles_returns_400(self):
        r = self.post("cap-outliers", {"columns": ["score"], "lower_pct": 50, "upper_pct": 50})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# transform_column
# ---------------------------------------------------------------------------

class TransformColumnTests(DatalabTestBase):
    def test_log_transform(self):
        r = self.post("transform-column", {"columns": ["score"], "function": "log"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("transformed_columns", r.data)

    def test_sqrt_transform(self):
        r = self.post("transform-column", {"columns": ["score"], "function": "sqrt"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_invalid_function_returns_400(self):
        r = self.post("transform-column", {"columns": ["score"], "function": "sigmoid"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_returns_400(self):
        r = self.post("transform-column", {"columns": ["name"], "function": "log"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# drop_columns
# ---------------------------------------------------------------------------

class DropColumnsTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("drop-columns", {"columns": ["city"]})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("city", r.data["columns_dropped"])

    def test_invalid_columns_type_returns_400(self):
        r = self.post("drop-columns", {"columns": "city"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_columns_list_returns_400(self):
        r = self.post("drop-columns", {"columns": []})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("drop-columns", {"columns": ["nonexistent"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_reflects_drop(self):
        self.post("drop-columns", {"columns": ["city"]})
        r = self.get("preview")
        self.assertNotIn("city", r.data["columns"])


# ---------------------------------------------------------------------------
# add_column
# ---------------------------------------------------------------------------

class AddColumnTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("add-column", {
            "new_name": "sum_ab", "formula": "add",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["new_column"], "sum_ab")

    def test_missing_params_returns_400(self):
        r = self.post("add-column", {"new_name": "x", "formula": "add"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_formula_returns_400(self):
        r = self.post("add-column", {
            "new_name": "x", "formula": "exponentiate",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_column_already_exists_returns_400(self):
        r = self.post("add-column", {
            "new_name": "c", "formula": "add",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_operand_returns_400(self):
        r = self.post("add-column", {
            "new_name": "x", "formula": "add",
            "operand_a": "name", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_operand_returns_400(self):
        r = self.post("add-column", {
            "new_name": "x", "formula": "add",
            "operand_a": "nonexistent", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# filter_rows
# ---------------------------------------------------------------------------

class FilterRowsTests(DatalabTestBase):
    def test_gt_filter_keeps_matching_rows(self):
        # age > 26: keeps 30.0, 35.0, 45.0, 50.0 → rows_after=4, removes 25.0 + null
        r = self.post("filter-rows", {"column": "age", "operator": "gt", "value": 26})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["rows_after"], 4)
        self.assertEqual(r.data["rows_removed"], 2)

    def test_notnull_operator_no_value_needed(self):
        r = self.post("filter-rows", {"column": "age", "operator": "notnull"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["rows_after"], 5)

    def test_eq_filter(self):
        r = self.post("filter-rows", {"column": "city", "operator": "eq", "value": "NYC"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["rows_after"], 3)

    def test_missing_column_returns_400(self):
        r = self.post("filter-rows", {"operator": "eq", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_operator_returns_400(self):
        r = self.post("filter-rows", {"column": "age", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_operator_returns_400(self):
        r = self.post("filter-rows", {"column": "age", "operator": "between", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_value_for_gt_returns_400(self):
        r = self.post("filter-rows", {"column": "age", "operator": "gt"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("filter-rows", {"column": "nonexistent", "operator": "eq", "value": 1})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# clean_string
# ---------------------------------------------------------------------------

class CleanStringTests(DatalabTestBase):
    def test_lower_operation(self):
        r = self.post("clean-string", {"columns": ["name"], "operation": "lower"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(r.data["cells_changed"], 0)

    def test_upper_operation(self):
        r = self.post("clean-string", {"columns": ["city"], "operation": "upper"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_invalid_operation_returns_400(self):
        r = self.post("clean-string", {"columns": ["name"], "operation": "reverse"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_string_column_returns_400(self):
        r = self.post("clean-string", {"columns": ["age"], "operation": "lower"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_columns_type_returns_400(self):
        r = self.post("clean-string", {"columns": "name", "operation": "lower"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# scale_columns
# ---------------------------------------------------------------------------

class ScaleColumnsTests(DatalabTestBase):
    def test_minmax_scale(self):
        r = self.post("scale-columns", {"columns": ["score", "a"], "method": "minmax"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("scaled_columns", r.data)

    def test_zscore_scale(self):
        r = self.post("scale-columns", {"columns": ["score"], "method": "zscore"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_invalid_method_returns_400(self):
        r = self.post("scale-columns", {"columns": ["score"], "method": "l2_norm"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_returns_400(self):
        r = self.post("scale-columns", {"columns": ["name"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# extract_datetime
# ---------------------------------------------------------------------------

class ExtractDatetimeTests(DatalabTestBase):
    def test_missing_column_returns_400(self):
        r = self.post("extract-datetime", {"features": ["year", "month"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_features_returns_400(self):
        r = self.post("extract-datetime", {"column": "name"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_features_returns_400(self):
        r = self.post("extract-datetime", {"column": "name", "features": []})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_feature_returns_400(self):
        r = self.post("extract-datetime", {"column": "name", "features": ["quarter"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("extract-datetime", {"column": "nonexistent", "features": ["year"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_happy_path_extracts_features(self):
        df = pd.DataFrame({
            "date": ["2021-01-15", "2022-06-30", "2023-12-01"],
            "value": [1, 2, 3],
        })
        ds = Dataset.objects.create(
            user=self.user, file=_csv_upload(df), file_name="dt.csv", file_format="csv"
        )
        r = self.client.post(
            reverse("datalab-extract-datetime", args=[ds.id]),
            {"column": "date", "features": ["year", "month"]},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("date_year", r.data["added_columns"])
        self.assertIn("date_month", r.data["added_columns"])


# ---------------------------------------------------------------------------
# encode_columns
# ---------------------------------------------------------------------------

class EncodeColumnsTests(DatalabTestBase):
    def test_label_encode(self):
        r = self.post("encode-columns", {"columns": ["city"], "strategy": "label"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["strategy"], "label")

    def test_onehot_low_cardinality_succeeds(self):
        # city has 4 unique values — well under the 50-value limit
        r = self.post("encode-columns", {"columns": ["city"], "strategy": "onehot"})
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_onehot_high_cardinality_returns_400(self):
        df = pd.DataFrame({
            "id": range(60),
            "high_card": [f"val_{i}" for i in range(60)],
        })
        ds = Dataset.objects.create(
            user=self.user, file=_csv_upload(df), file_name="hc.csv", file_format="csv"
        )
        r = self.client.post(
            reverse("datalab-encode-columns", args=[ds.id]),
            {"columns": ["high_card"], "strategy": "onehot"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unique values", r.data["detail"])

    def test_invalid_strategy_returns_400(self):
        r = self.post("encode-columns", {"columns": ["city"], "strategy": "binary"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_numeric_column_returns_400(self):
        r = self.post("encode-columns", {"columns": ["score"], "strategy": "label"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_column_returns_400(self):
        r = self.post("encode-columns", {"columns": ["nonexistent"], "strategy": "label"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_columns_list_returns_400(self):
        r = self.post("encode-columns", {"columns": [], "strategy": "label"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# normalize_column_names
# ---------------------------------------------------------------------------

class NormalizeColumnNamesTests(DatalabTestBase):
    def test_already_normalized_is_noop(self):
        # base_df columns are all clean lowercase — should report already normalized
        r = self.post("normalize-column-names", {})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("detail", r.data)

    def test_uppercase_columns_are_renamed(self):
        df = pd.DataFrame({"First Name": [1, 2], "Last Name": [3, 4]})
        ds = Dataset.objects.create(
            user=self.user, file=_csv_upload(df), file_name="caps.csv", file_format="csv"
        )
        r = self.client.post(
            reverse("datalab-normalize-column-names", args=[ds.id]),
            {}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("renamed", r.data)
        self.assertGreater(len(r.data["renamed"]), 0)

    def test_column_casts_keys_migrate_after_normalize(self):
        df = pd.DataFrame({"First Name": ["Alice", "Bob"], "Age": [30, 40]})
        ds = Dataset.objects.create(
            user=self.user, file=_csv_upload(df), file_name="cn.csv", file_format="csv"
        )
        ds.column_casts = {"First Name": "string"}
        ds.save(update_fields=["column_casts"])

        r = self.client.post(
            reverse("datalab-normalize-column-names", args=[ds.id]),
            {}, format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ds.refresh_from_db()
        self.assertNotIn("First Name", ds.column_casts)
        self.assertIn("first_name", ds.column_casts)


# ---------------------------------------------------------------------------
# validate_formula
# ---------------------------------------------------------------------------

class ValidateFormulaTests(DatalabTestBase):
    def test_happy_path(self):
        r = self.post("validate-formula", {
            "result_column": "c", "formula": "add",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("result_column", r.data)

    def test_missing_params_returns_400(self):
        r = self.post("validate-formula", {"result_column": "c", "formula": "add"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_formula_returns_400(self):
        r = self.post("validate-formula", {
            "result_column": "c", "formula": "power",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_column_returns_400(self):
        r = self.post("validate-formula", {
            "result_column": "c", "formula": "add",
            "operand_a": "name", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tolerance_zero_returns_400(self):
        r = self.post("validate-formula", {
            "result_column": "c", "formula": "add",
            "operand_a": "a", "operand_b": "b",
            "tolerance": 0,
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_tolerance_returns_400(self):
        r = self.post("validate-formula", {
            "result_column": "c", "formula": "add",
            "operand_a": "a", "operand_b": "b",
            "tolerance": -1,
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# fill_derived
# ---------------------------------------------------------------------------

class FillDerivedTests(DatalabTestBase):
    def test_no_nulls_returns_zero_filled(self):
        # c has no nulls in base_df
        r = self.post("fill-derived", {
            "target": "c", "formula": "add",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["cells_filled"], 0)

    def test_fills_null_values(self):
        df = pd.DataFrame({
            "a": [1.0, 2.0, 3.0],
            "b": [2.0, 4.0, 6.0],
            "c": [None, 6.0, None],
        })
        ds = Dataset.objects.create(
            user=self.user, file=_csv_upload(df), file_name="derived.csv", file_format="csv"
        )
        r = self.client.post(
            reverse("datalab-fill-derived", args=[ds.id]),
            {"target": "c", "formula": "add", "operand_a": "a", "operand_b": "b"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreater(r.data["cells_filled"], 0)

    def test_missing_params_returns_400(self):
        r = self.post("fill-derived", {"target": "c", "formula": "add"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_column_returns_400(self):
        r = self.post("fill-derived", {
            "target": "name", "formula": "add",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# fix_formula
# ---------------------------------------------------------------------------

class FixFormulaTests(DatalabTestBase):
    def test_no_violations_returns_zero_fixed(self):
        # c = a + b exactly → no violations within tolerance
        r = self.post("fix-formula", {
            "target": "c", "formula": "add",
            "operand_a": "a", "operand_b": "b",
            "tolerance": 0.01,
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["cells_fixed"], 0)

    def test_tolerance_zero_returns_400(self):
        r = self.post("fix-formula", {
            "target": "c", "formula": "add",
            "operand_a": "a", "operand_b": "b",
            "tolerance": 0,
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_formula_returns_400(self):
        r = self.post("fix-formula", {
            "target": "c", "formula": "power",
            "operand_a": "a", "operand_b": "b",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_params_returns_400(self):
        r = self.post("fix-formula", {"target": "c"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
