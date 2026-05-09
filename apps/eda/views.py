import logging

import pandas as pd
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.data_engine import (
    CORRELATION_METHODS,
    OUTLIER_METHODS,
    apply_stored_casts,
    eda_correlation,
    eda_crosstab,
    eda_distribution,
    eda_missing_heatmap,
    eda_outlier_summary,
    eda_pairwise,
    eda_value_counts,
    eda_categorical_association,
    get_cached_dataframe,
)
from apps.datasets.models import Dataset
from apps.core.ollama_client import stream_interpret_eda
from django.http import StreamingHttpResponse

logger = logging.getLogger(__name__)

_DEFAULT_BINS = 20
_MAX_BINS = 100
_DEFAULT_SAMPLE = 500
_MAX_SAMPLE = 5000
_DEFAULT_TOP_N = 20
_MAX_TOP_N = 100
_MAX_CROSSTAB_CARDINALITY = 50
_MAX_OUTLIER_THRESHOLD = 10
_MAX_VALUE_COUNTS_COLS = 50
_MISSING_HEATMAP_ROW_LIMIT = 50_000


def _load_df(dataset_id, request):
    """
    Fetch Dataset, verify ownership, load and apply casts.
    Returns (error_response, None) on failure or (None, (df, dataset)).
    """
    try:
        dataset = Dataset.objects.get(pk=dataset_id, user=request.user)
    except Dataset.DoesNotExist:
        return Response({"detail": "Dataset not found."}, status=status.HTTP_404_NOT_FOUND), None

    df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
    if df is None:
        return Response({"detail": "Could not load dataset file."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR), None

    if dataset.column_casts:
        df = apply_stored_casts(df, dataset.column_casts)

    return None, (df, dataset)


def _parse_columns_param(raw, df, require_numeric=False):
    """
    Validate a list of column names against df.
    Returns (error_str, None) or (None, validated_list).
    """
    if not raw or not isinstance(raw, list):
        return "columns must be a non-empty list.", None

    missing = [c for c in raw if c not in df.columns]
    if missing:
        return f"Columns not found in dataset: {missing}", None

    if require_numeric:
        non_numeric = [c for c in raw if not pd.api.types.is_numeric_dtype(df[c])]
        if non_numeric:
            return f"Columns must be numeric: {non_numeric}", None

    return None, raw


class EDAViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def correlation(self, request, dataset_id=None):
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

        columns_raw = request.query_params.getlist("columns")
        method = request.query_params.get("method", "pearson")

        if method not in CORRELATION_METHODS:
            return Response(
                {"detail": f"'method' must be one of: {sorted(CORRELATION_METHODS)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if columns_raw:
            col_err, columns = _parse_columns_param(columns_raw, df, require_numeric=True)
            if col_err:
                return Response({"detail": col_err}, status=status.HTTP_400_BAD_REQUEST)
        else:
            columns = df.select_dtypes(include="number").columns.tolist()
            if not columns:
                return Response({"detail": "No numeric columns found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = eda_correlation(df, columns, method=method)
        except (ValueError, KeyError, TypeError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("eda_correlation failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing correlation."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def association(self, request, dataset_id=None):
        """
        GET /eda/association/{dataset_id}/
        Compute Cramér's V for categorical columns.
        """
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

        columns_raw = request.query_params.getlist("columns")

        if columns_raw:
            col_err, columns = _parse_columns_param(columns_raw, df)
            if col_err:
                return Response({"detail": col_err}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Default to all non-numeric columns
            columns = df.select_dtypes(exclude="number").columns.tolist()
            if not columns:
                return Response({"detail": "No categorical columns found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Limit to 50 columns for performance
            columns = columns[:50]
            data = eda_categorical_association(df, columns)
        except Exception:
            logger.exception("eda_categorical_association failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing association."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def distribution(self, request, dataset_id=None):
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

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
            col_err, columns = _parse_columns_param(columns_raw, df, require_numeric=True)
            if col_err:
                return Response({"detail": col_err}, status=status.HTTP_400_BAD_REQUEST)
        else:
            columns = df.select_dtypes(include="number").columns.tolist()
            if not columns:
                return Response({"detail": "No numeric columns found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = eda_distribution(df, columns, bins=bins)
        except (ValueError, KeyError, TypeError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("eda_distribution failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing distribution."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def value_counts(self, request, dataset_id=None):
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

        columns_raw = request.query_params.getlist("columns")
        try:
            top_n = int(request.query_params.get("top_n", _DEFAULT_TOP_N))
        except (ValueError, TypeError):
            return Response({"detail": "'top_n' must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        if not (1 <= top_n <= _MAX_TOP_N):
            return Response(
                {"detail": f"'top_n' must be between 1 and {_MAX_TOP_N}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if columns_raw:
            col_err, columns = _parse_columns_param(columns_raw, df)
            if col_err:
                return Response({"detail": col_err}, status=status.HTTP_400_BAD_REQUEST)
        else:
            columns = df.columns.tolist()[:_MAX_VALUE_COUNTS_COLS]

        try:
            data = eda_value_counts(df, columns, top_n=top_n)
        except (ValueError, KeyError, TypeError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("eda_value_counts failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing value counts."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def crosstab(self, request, dataset_id=None):
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

        col_a = request.query_params.get("col_a")
        col_b = request.query_params.get("col_b")

        if not col_a or not col_b:
            return Response(
                {"detail": "'col_a' and 'col_b' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        col_err, _ = _parse_columns_param([col_a, col_b], df)
        if col_err:
            return Response({"detail": col_err}, status=status.HTTP_400_BAD_REQUEST)

        for col_name, col in ((col_a, df[col_a]), (col_b, df[col_b])):
            cardinality = col.nunique()
            if cardinality > _MAX_CROSSTAB_CARDINALITY:
                return Response(
                    {
                        "detail": (
                            f"'{col_name}' has {cardinality} unique values — "
                            f"crosstab is limited to {_MAX_CROSSTAB_CARDINALITY}. "
                            f"Use value-counts to explore high-cardinality columns."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        normalize = request.query_params.get("normalize", "false").lower() == "true"

        try:
            data = eda_crosstab(df, col_a, col_b, normalize=normalize)
        except (ValueError, KeyError, TypeError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("eda_crosstab failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing crosstab."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def outlier_summary(self, request, dataset_id=None):
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

        method = request.query_params.get("method", "iqr")
        if method not in OUTLIER_METHODS:
            return Response(
                {"detail": f"'method' must be one of: {sorted(OUTLIER_METHODS)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            threshold = float(request.query_params.get("threshold", 1.5))
        except (ValueError, TypeError):
            return Response(
                {"detail": "'threshold' must be a number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if threshold <= 0:
            return Response(
                {"detail": "'threshold' must be > 0."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if threshold > _MAX_OUTLIER_THRESHOLD:
            return Response(
                {"detail": f"'threshold' must be ≤ {_MAX_OUTLIER_THRESHOLD}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = eda_outlier_summary(df, method=method, threshold=threshold)
        except (ValueError, KeyError, TypeError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("eda_outlier_summary failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing outlier summary."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def missing_heatmap(self, request, dataset_id=None):
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

        if len(df) > _MISSING_HEATMAP_ROW_LIMIT:
            df = df.sample(n=_MISSING_HEATMAP_ROW_LIMIT, random_state=42)

        try:
            data = eda_missing_heatmap(df)
        except (ValueError, KeyError, TypeError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("eda_missing_heatmap failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing missing heatmap."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    def pairwise(self, request, dataset_id=None):
        err, result = _load_df(dataset_id, request)
        if err:
            return err
        df, _ = result

        col_x = request.query_params.get("col_x")
        col_y = request.query_params.get("col_y")

        if not col_x or not col_y:
            return Response(
                {"detail": "'col_x' and 'col_y' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        col_err, _ = _parse_columns_param([col_x, col_y], df, require_numeric=True)
        if col_err:
            return Response({"detail": col_err}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sample = int(request.query_params.get("sample", _DEFAULT_SAMPLE))
        except (ValueError, TypeError):
            return Response(
                {"detail": "'sample' must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not (1 <= sample <= _MAX_SAMPLE):
            return Response(
                {"detail": f"'sample' must be between 1 and {_MAX_SAMPLE}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = eda_pairwise(df, col_x, col_y, sample=sample)
        except (ValueError, KeyError, TypeError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("eda_pairwise failed for dataset %s", dataset_id)
            return Response({"detail": "Internal error computing pairwise scatter."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)

    @action(detail=True, methods=["post"])
    def interpret(self, request, dataset_id=None):
        """
        POST /api/v1/eda/{dataset_id}/interpret/
        Body: { "eda_type": "correlation", "data": {...}, "columns": [...] }
        Streams AI interpretation of the provided EDA results.
        """
        eda_type = request.data.get("eda_type")
        data = request.data.get("data")
        columns = request.data.get("columns")

        if not eda_type or not data:
            return Response(
                {"detail": "'eda_type' and 'data' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = StreamingHttpResponse(
            stream_interpret_eda(eda_type, data, columns),
            content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
