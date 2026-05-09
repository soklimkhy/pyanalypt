import logging

import pandas as pd
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from apps.core.chart_engine import AGGREGATIONS, fmt_bar, fmt_histogram, fmt_line, fmt_scatter
from apps.core.data_engine import apply_stored_casts, eda_distribution, get_cached_dataframe
from apps.datasets.models import Dataset

logger = logging.getLogger(__name__)

_DEFAULT_SAMPLE = 500
_MAX_SAMPLE = 5_000
_DEFAULT_BINS = 20
_MAX_BINS = 100
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


def _load_df(dataset_id, request):
    try:
        dataset = Dataset.objects.get(pk=dataset_id, user=request.user)
    except Dataset.DoesNotExist:
        return Response({"detail": "Dataset not found."}, status=status.HTTP_404_NOT_FOUND), None

    df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
    if df is None:
        return Response({"detail": "Could not load dataset file."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR), None

    if dataset.column_casts:
        df = apply_stored_casts(df, dataset.column_casts)

    return None, df


class VisualizationViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def bar(self, request, dataset_id=None):
        err, df = _load_df(dataset_id, request)
        if err:
            return err

        x_col = request.query_params.get("x_col")
        y_col = request.query_params.get("y_col")
        if not x_col or not y_col:
            return Response({"detail": "'x_col' and 'y_col' are required."}, status=status.HTTP_400_BAD_REQUEST)

        for col in (x_col, y_col):
            if col not in df.columns:
                return Response({"detail": f"Column '{col}' not found in dataset."}, status=status.HTTP_400_BAD_REQUEST)

        if not pd.api.types.is_numeric_dtype(df[y_col]):
            return Response(
                {"detail": f"'y_col' ('{y_col}') must be numeric."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agg = request.query_params.get("agg", "sum")
        if agg not in AGGREGATIONS:
            return Response(
                {"detail": f"'agg' must be one of: {sorted(AGGREGATIONS)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        group_by = request.query_params.get("group_by")
        if group_by and group_by not in df.columns:
            return Response(
                {"detail": f"'group_by' column '{group_by}' not found in dataset."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit", _DEFAULT_LIMIT))
        except (ValueError, TypeError):
            return Response({"detail": "'limit' must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        if not (1 <= limit <= _MAX_LIMIT):
            return Response(
                {"detail": f"'limit' must be between 1 and {_MAX_LIMIT}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = fmt_bar(df, x_col, y_col, agg=agg, group_by=group_by, limit=limit)
        except Exception:
            logger.exception("fmt_bar failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error building bar chart."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def line(self, request, dataset_id=None):
        err, df = _load_df(dataset_id, request)
        if err:
            return err

        x_col = request.query_params.get("x_col")
        y_cols_raw = request.query_params.getlist("y_cols")

        if not x_col:
            return Response({"detail": "'x_col' is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not y_cols_raw:
            return Response({"detail": "'y_cols' is required (pass one or more)."}, status=status.HTTP_400_BAD_REQUEST)

        all_cols = [x_col] + y_cols_raw
        missing = [c for c in all_cols if c not in df.columns]
        if missing:
            return Response({"detail": f"Columns not found in dataset: {missing}"}, status=status.HTTP_400_BAD_REQUEST)

        non_numeric = [c for c in y_cols_raw if not pd.api.types.is_numeric_dtype(df[c])]
        if non_numeric:
            return Response(
                {"detail": f"'y_cols' must be numeric: {non_numeric}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sort = request.query_params.get("sort", "true").lower() != "false"

        try:
            data = fmt_line(df, x_col, y_cols_raw, sort=sort)
        except Exception:
            logger.exception("fmt_line failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error building line chart."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def scatter(self, request, dataset_id=None):
        err, df = _load_df(dataset_id, request)
        if err:
            return err

        col_x = request.query_params.get("col_x")
        col_y = request.query_params.get("col_y")
        if not col_x or not col_y:
            return Response({"detail": "'col_x' and 'col_y' are required."}, status=status.HTTP_400_BAD_REQUEST)

        for col in (col_x, col_y):
            if col not in df.columns:
                return Response({"detail": f"Column '{col}' not found in dataset."}, status=status.HTTP_400_BAD_REQUEST)

        non_numeric = [c for c in (col_x, col_y) if not pd.api.types.is_numeric_dtype(df[c])]
        if non_numeric:
            return Response(
                {"detail": f"Columns must be numeric: {non_numeric}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        color_by = request.query_params.get("color_by")
        if color_by and color_by not in df.columns:
            return Response(
                {"detail": f"'color_by' column '{color_by}' not found in dataset."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sample = int(request.query_params.get("sample", _DEFAULT_SAMPLE))
        except (ValueError, TypeError):
            return Response({"detail": "'sample' must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        if not (1 <= sample <= _MAX_SAMPLE):
            return Response(
                {"detail": f"'sample' must be between 1 and {_MAX_SAMPLE}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = fmt_scatter(df, col_x, col_y, color_by=color_by, sample=sample)
        except Exception:
            logger.exception("fmt_scatter failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error building scatter chart."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def histogram(self, request, dataset_id=None):
        err, df = _load_df(dataset_id, request)
        if err:
            return err

        columns_raw = request.query_params.getlist("columns")
        try:
            bins = int(request.query_params.get("bins", _DEFAULT_BINS))
        except (ValueError, TypeError):
            return Response({"detail": "'bins' must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        if not (1 <= bins <= _MAX_BINS):
            return Response(
                {"detail": f"'bins' must be between 1 and {_MAX_BINS}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if columns_raw:
            missing = [c for c in columns_raw if c not in df.columns]
            if missing:
                return Response({"detail": f"Columns not found in dataset: {missing}"}, status=status.HTTP_400_BAD_REQUEST)
            non_numeric = [c for c in columns_raw if not pd.api.types.is_numeric_dtype(df[c])]
            if non_numeric:
                return Response(
                    {"detail": f"Columns must be numeric: {non_numeric}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            columns = columns_raw
        else:
            columns = df.select_dtypes(include="number").columns.tolist()
            if not columns:
                return Response({"detail": "No numeric columns found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            distribution = eda_distribution(df, columns, bins=bins)
            data = fmt_histogram(distribution)
        except Exception:
            logger.exception("fmt_histogram failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error building histogram."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)
