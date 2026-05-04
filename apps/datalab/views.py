import io
import logging
import os

import pandas as pd

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.files.base import ContentFile
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import StreamingHttpResponse

from apps.datasets.models import Dataset, DatasetActivityLog, DatasetSnapshot
from apps.core.ollama_client import stream_suggest_cleaning
from .serializers import (
    CastColumnsSerializer,
    UpdateCellSerializer,
    RenameColumnSerializer,
    DropDuplicatesSerializer,
    ReplaceValuesSerializer,
    DropNullsSerializer,
    FillNullsSerializer,
    AddColumnSerializer,
    OutlierParamsSerializer,
    ImputeOutliersSerializer,
    CapOutliersSerializer,
    TransformColumnSerializer,
    DropColumnsSerializer,
    FilterRowsSerializer,
    CleanStringSerializer,
    ScaleColumnsSerializer,
    ExtractDatetimeSerializer,
    EncodeColumnsSerializer,
)
from apps.core.data_engine import (
    _df_cache_key,
    get_cached_dataframe,
    save_dataframe,
    apply_cast,
    validate_cast,
    apply_stored_casts,
    update_cell as df_update_cell,
    rename_column as df_rename_column,
    replace_values as df_replace_values,
    drop_nulls as df_drop_nulls,
    fill_nulls as df_fill_nulls,
    describe_dataframe,
    fill_derived as df_fill_derived,
    validate_formula as df_validate_formula,
    fix_formula_errors as df_fix_formula_errors,
    detect_outliers as df_detect_outliers,
    trim_outliers as df_trim_outliers,
    impute_outliers as df_impute_outliers,
    cap_outliers as df_cap_outliers,
    transform_column as df_transform_column,
    drop_columns as df_drop_columns,
    add_column as df_add_column,
    filter_rows as df_filter_rows,
    clean_string_column as df_clean_string_column,
    scale_columns as df_scale_columns,
    extract_datetime_features as df_extract_datetime_features,
    encode_columns as df_encode_columns,
    normalize_column_names as df_normalize_column_names,
    OUTLIER_METHODS,
    SUPPORTED_FORMULAS,
)

logger = logging.getLogger(__name__)

_LOAD_FAILED = "Could not load dataset file."
_SAVE_FAILED = "Failed to save updated dataset."
_INVALID_THRESHOLD = "'threshold' must be a positive number."
_MAX_PREVIEW_LIMIT = 10_000
_MAX_OUTLIER_THRESHOLD = 10


def _commit_mutation(df, dataset, user, action, details, extra_save_fields=None, create_snapshot=True):
    """
    Persist df → disk, update dataset metadata, pre-warm versioned cache, write activity log.
    Optionally creates a snapshot of the state PRIOR to this mutation.
    Must be called inside transaction.atomic().
    """
    log = DatasetActivityLog.objects.create(
        user=user,
        dataset=dataset,
        dataset_name_snap=dataset.file_name,
        action=action,
        details=details,
    )

    if create_snapshot and dataset.file and os.path.exists(dataset.file.path):
        try:
            snapshot = DatasetSnapshot(dataset=dataset, activity_log=log)
            with open(dataset.file.path, "rb") as f:
                snapshot.file.save(
                    f"snap_{dataset.id}_{timezone.now().strftime('%y%m%d%H%M%S')}.{dataset.file_format}",
                    ContentFile(f.read()),
                    save=False,
                )
            snapshot.save()
        except Exception as e:
            logger.warning("Failed to create snapshot for dataset %s: %s", dataset.id, e)

    if not save_dataframe(df, dataset.file.path, dataset.file_format):
        raise RuntimeError(_SAVE_FAILED)

    dataset.file_size = dataset.file.size
    fields = ["file_size", "updated_date"] + (extra_save_fields or [])
    dataset.save(update_fields=fields)

    try:
        buf = io.BytesIO()
        df.to_parquet(buf, index=True, compression="snappy")
        key = _df_cache_key(dataset.id, dataset.updated_date)
        cache.set(key, buf.getvalue(), timeout=settings.DATAFRAME_CACHE_TTL)
    except Exception as e:
        logger.warning("df cache pre-warm failed for dataset %s: %s", dataset.id, e)


def _validate_casts(df, casts):
    """Run pre-flight validation on each requested cast. Returns (validated, warnings, errors)."""
    validated = {}
    warnings = []
    errors = []
    for col, target in casts.items():
        cast_status, message = validate_cast(df[col], target)
        validated[col] = {"status": cast_status, "message": message}
        if cast_status == "warning":
            warnings.append({"column": col, "warning": message})
        elif cast_status == "error":
            errors.append({"column": col, "target": target, "status": "error", "detail": message})
    return validated, warnings, errors


def _format_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


_DEDUP_MODES = ("all_first", "all_last", "subset_keep", "drop_all")
_ONE_HOT_MAX_CARDINALITY = 15


def _validate_dedup_params(mode, subset, keep):
    """Returns an error string on failure, None on success."""
    if mode not in _DEDUP_MODES:
        return f"Invalid 'mode'. Choose one of: {sorted(_DEDUP_MODES)}"
    if mode == "subset_keep":
        if subset is None:
            return "'subset' is required for mode 'subset_keep'."
        if keep not in ("first", "last"):
            return "For mode 'subset_keep', 'keep' must be 'first' or 'last'."
    return None


def _validate_subset_cols(subset, df):
    """Returns an error string on failure, None on success."""
    if subset is None:
        return None
    if not isinstance(subset, list) or not subset:
        return "'subset' must be a non-empty list of column names."
    if not all(isinstance(c, str) for c in subset):
        return "'subset' must be a list of column name strings."
    unknown_cols = [c for c in subset if c not in df.columns]
    if unknown_cols:
        return f"Columns not found in dataset: {unknown_cols}"
    return None


def _apply_dedup(df, mode, subset, keep):
    if mode == "all_first":
        return df.drop_duplicates(keep="first")
    if mode == "all_last":
        return df.drop_duplicates(keep="last")
    if mode == "subset_keep":
        return df.drop_duplicates(subset=subset, keep=keep)
    return df.drop_duplicates(subset=subset, keep=False)  # drop_all


def _parse_numeric_columns(source, df):
    """
    Parse and validate the 'columns' param for outlier/transform endpoints.
    source: list from request.data, or comma-separated string from query_params.
    Returns (error_str, columns_list) — error_str is None on success.
    """
    if not source:
        return "'columns' is required.", None
    if isinstance(source, str):
        columns = [c.strip() for c in source.split(",") if c.strip()]
    elif isinstance(source, list):
        columns = source
    else:
        return "'columns' must be a list or comma-separated string.", None
    if not columns:
        return "'columns' must not be empty.", None
    unknown = [c for c in columns if c not in df.columns]
    if unknown:
        return f"Columns not found in dataset: {unknown}", None
    non_numeric = [c for c in columns if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        return f"Columns must be numeric: {non_numeric}", None
    return None, columns


def _validate_drop_nulls_params(axis, how, thresh_pct):
    """Returns an error string on failure, None on success."""
    if axis not in ("rows", "columns"):
        return "'axis' must be 'rows' or 'columns'."
    if axis == "rows" and how not in ("any", "all"):
        return "'how' must be 'any' or 'all'."
    if axis == "columns":
        if thresh_pct is None:
            return "'thresh_pct' is required when axis is 'columns'."
        if not isinstance(thresh_pct, (int, float)) or not (0 <= thresh_pct <= 100):
            return "'thresh_pct' must be a number between 0 and 100."
    return None


def _apply_casts(df, casts, error_cols, col_validated_data):
    """Attempt each requested cast, skipping known-error columns. Returns results list."""
    results = []
    for col, target in casts.items():
        if col in error_cols:
            continue
        from_dtype = str(df[col].dtype)
        try:
            df[col] = apply_cast(df[col], target)
            results.append({
                "column": col,
                "from_dtype": from_dtype,
                "to_dtype": str(df[col].dtype),
                "status": "ok",
                "validation": col_validated_data[col],
            })
        except Exception as exc:
            results.append({
                "column": col,
                "from_dtype": from_dtype,
                "to_dtype": None,
                "status": "error",
                "detail": str(exc),
            })
    return results


def _load_and_lock(dataset_id, user):
    """
    Acquire a row-level lock on the dataset and load its DataFrame.
    Must be called inside a transaction.atomic() block.
    Returns (error_response, None, None) on failure or (None, dataset, df) on success.
    """
    dataset = get_object_or_404(Dataset.objects.all().select_for_update(), pk=dataset_id, user=user)
    df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
    if df is None:
        return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR), None, None
    if dataset.column_casts:
        df = apply_stored_casts(df, dataset.column_casts)
    return None, dataset, df


def _resolve_formula_context(request, dataset_id, target_field="target", lock=False):
    """
    Parse and validate common formula endpoint parameters.
    Returns (error_response, None) on failure, or (None, ctx_dict) on success.
    When lock=True, must be called inside transaction.atomic().
    ctx_dict keys: df, dataset, target, formula, operand_a, operand_b, tolerance.
    """
    target = request.data.get(target_field, "").strip()
    formula = request.data.get("formula", "").strip()
    operand_a = request.data.get("operand_a", "").strip()
    operand_b = request.data.get("operand_b", "").strip()
    tolerance = request.data.get("tolerance", 0.01)

    if not all([target, formula, operand_a, operand_b]):
        return Response(
            {"detail": f"'{target_field}', 'formula', 'operand_a', and 'operand_b' are all required."},
            status=status.HTTP_400_BAD_REQUEST,
        ), None

    if formula not in SUPPORTED_FORMULAS:
        return Response(
            {"detail": f"Invalid 'formula'. Choose one of: {list(SUPPORTED_FORMULAS)}"},
            status=status.HTTP_400_BAD_REQUEST,
        ), None

    try:
        tolerance = float(tolerance)
        if tolerance <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return Response(
            {"detail": "'tolerance' must be a positive number (> 0)."},
            status=status.HTTP_400_BAD_REQUEST,
        ), None

    qs = Dataset.objects.all().select_for_update() if lock else Dataset.objects.all()
    dataset = get_object_or_404(qs, pk=dataset_id, user=request.user)
    df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
    if df is None:
        return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR), None

    if dataset.column_casts:
        df = apply_stored_casts(df, dataset.column_casts)

    missing = [c for c in [target, operand_a, operand_b] if c not in df.columns]
    if missing:
        return Response(
            {"detail": f"Columns not found in dataset: {missing}"},
            status=status.HTTP_400_BAD_REQUEST,
        ), None

    non_numeric = [c for c in [target, operand_a, operand_b] if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        return Response(
            {"detail": f"All three columns must be numeric: {non_numeric}"},
            status=status.HTTP_400_BAD_REQUEST,
        ), None

    return None, {
        "df": df,
        "dataset": dataset,
        "target": target,
        "formula": formula,
        "operand_a": operand_a,
        "operand_b": operand_b,
        "tolerance": tolerance,
    }


class DatalabViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def preview(self, request, dataset_id=None):
        """GET /datalab/preview/{dataset_id}/"""
        try:
            limit = int(request.query_params.get("limit", 100))
            if limit < 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": f"'limit' must be a non-negative integer (0 = all rows, max {_MAX_PREVIEW_LIMIT})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if limit > _MAX_PREVIEW_LIMIT:
            return Response(
                {"detail": f"'limit' cannot exceed {_MAX_PREVIEW_LIMIT}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dataset = get_object_or_404(Dataset, pk=dataset_id, user=request.user)
        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
        if df is None:
            return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if dataset.column_casts:
            df = apply_stored_casts(df, dataset.column_casts)

        total_rows = len(df)
        effective_limit = min(limit or total_rows, _MAX_PREVIEW_LIMIT)
        view_df = df.iloc[:effective_limit]
        truncated = total_rows > effective_limit

        return Response({
            "dataset_id": dataset.id,
            "file_name": dataset.file_name,
            "file_format": dataset.file_format,
            "dataset_size": _format_size(dataset.file_size),
            "total_rows": total_rows,
            "total_columns": len(df.columns),
            "limit": effective_limit,
            "truncated": truncated,
            "columns": list(df.columns),
            "rows": view_df.astype(object).where(pd.notna(view_df), None).to_dict(orient="records"),
        })

    def inspect(self, request, dataset_id=None):
        """GET /datalab/inspect/{dataset_id}/"""
        dataset = get_object_or_404(Dataset, pk=dataset_id, user=request.user)
        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
        if df is None:
            return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if dataset.column_casts:
            df = apply_stored_casts(df, dataset.column_casts)

        total_rows = len(df)
        unique_counts = df.nunique()

        return Response({
            "info": {
                "columns": [
                    {
                        "column": col,
                        "dtype": str(df[col].dtype),
                        "non_null_count": int(df[col].notna().sum()),
                        "null_count": int(df[col].isna().sum()),
                        "null_pct": round(df[col].isna().sum() / total_rows * 100, 1) if total_rows > 0 else 0.0,
                        "unique_count": int(unique_counts[col]),
                        "is_unique": bool(unique_counts[col] == int(df[col].notna().sum())),
                    }
                    for col in df.columns
                ],
                "memory_usage_bytes": int(df.memory_usage(deep=True).sum()),
            },
        })

    def describe(self, request, dataset_id=None):
        """GET /datalab/describe/{dataset_id}/"""
        dataset = get_object_or_404(Dataset, pk=dataset_id, user=request.user)
        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
        if df is None:
            return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if dataset.column_casts:
            df = apply_stored_casts(df, dataset.column_casts)

        return Response({"columns": describe_dataframe(df)})

    def detect_outliers(self, request, dataset_id=None):
        """GET /datalab/detect-outliers/{dataset_id}/"""
        method = request.query_params.get("method", "iqr")
        threshold_raw = request.query_params.get("threshold", "1.5" if method == "iqr" else "3.0")
        columns_raw = request.query_params.get("columns", "")

        if method not in OUTLIER_METHODS:
            return Response(
                {"detail": f"'method' must be one of: {sorted(OUTLIER_METHODS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            threshold = float(threshold_raw)
            if threshold <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"detail": _INVALID_THRESHOLD}, status=status.HTTP_400_BAD_REQUEST)
        if threshold > _MAX_OUTLIER_THRESHOLD:
            return Response(
                {"detail": f"'threshold' must be ≤ {_MAX_OUTLIER_THRESHOLD}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dataset = get_object_or_404(Dataset, pk=dataset_id, user=request.user)
        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
        if df is None:
            return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        if dataset.column_casts:
            df = apply_stored_casts(df, dataset.column_casts)

        err, columns = _parse_numeric_columns(columns_raw, df)
        if err:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        result = df_detect_outliers(df, columns, method=method, threshold=threshold)
        return Response({
            "dataset_id": dataset_id,
            "method": method,
            "threshold": threshold,
            "columns": result,
        })

    def validate_formula(self, request, dataset_id=None):
        """POST /datalab/validate-formula/{dataset_id}/ — read-only, no lock needed."""
        err, ctx = _resolve_formula_context(request, dataset_id, target_field="result_column")
        if err:
            return err
        df = ctx["df"]
        result_column, formula = ctx["target"], ctx["formula"]
        operand_a, operand_b, tolerance = ctx["operand_a"], ctx["operand_b"], ctx["tolerance"]

        result = df_validate_formula(df, result_column, formula, operand_a, operand_b, tolerance)
        return Response({
            "result_column": result_column,
            "formula": formula,
            "operand_a": operand_a,
            "operand_b": operand_b,
            **result,
        })

    @action(detail=True, methods=["post"])
    def revert(self, request, dataset_id=None):
        """
        POST /datalab/revert/{dataset_id}/
        Body: { "snapshot_id": <int> } or { "undo": true }
        Replaces current file with a previous snapshot.
        """
        snapshot_id = request.data.get("snapshot_id")
        undo = request.data.get("undo", False)

        with transaction.atomic():
            dataset = get_object_or_404(Dataset.objects.select_for_update(), pk=dataset_id, user=request.user)
            
            if undo:
                snapshot = dataset.snapshots.first()
                if not snapshot:
                    return Response({"detail": "No snapshots available to undo."}, status=status.HTTP_400_BAD_REQUEST)
            elif snapshot_id:
                snapshot = get_object_or_404(dataset.snapshots, pk=snapshot_id)
            else:
                return Response({"detail": "Either 'snapshot_id' or 'undo: true' is required."}, status=status.HTTP_400_BAD_REQUEST)

            # 1. Create a "Safety Snapshot" of the state we are about to overwrite?
            # Probably not needed for a simple Revert, but let's do it for consistency
            # if we want a complete "History" that can go back and forth.
            # For now, let's just revert.

            # 2. Overwrite current file with snapshot file
            try:
                with open(snapshot.file.path, "rb") as sf:
                    with open(dataset.file.path, "wb") as df:
                        df.write(sf.read())
            except Exception as e:
                logger.error("Failed to restore snapshot file: %s", e)
                return Response({"detail": "System error during file restoration."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 3. Clear cache and update metadata
            from apps.core.data_engine import invalidate_dataframe_cache
            invalidate_dataframe_cache(dataset.id)
            
            dataset.file_size = dataset.file.size
            dataset.save(update_fields=["file_size", "updated_date"])

            # 4. Log the revert action (don't create a snapshot of the revert itself)
            DatasetActivityLog.objects.create(
                user=request.user,
                dataset=dataset,
                dataset_name_snap=dataset.file_name,
                action="REVERT",
                details={"snapshot_id": snapshot.id, "was_undo": undo},
            )

            # 5. Delete the snapshot we just used? 
            # If it was an "Undo", typically yes. If it was a "Revert to specific point", maybe no.
            # Let's keep it for now.

            return Response({
                "detail": "Dataset reverted successfully.",
                "updated_at": dataset.updated_date,
            })

    # ------------------------------------------------------------------ #
    # Mutating endpoints — all wrapped in transaction.atomic()            #
    # ------------------------------------------------------------------ #

    def cast_columns(self, request, dataset_id=None):
        """POST /datalab/cast/{dataset_id}/"""
        s = CastColumnsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        casts = s.validated_data["casts"]
        force = s.validated_data["force"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            unknown_cols = [c for c in casts if c not in df.columns]
            if unknown_cols:
                return Response(
                    {"detail": f"Columns not found in dataset: {unknown_cols}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            col_validated_data, validation_warnings, hard_errors = _validate_casts(df, casts)

            if validation_warnings and not force:
                return Response({
                    "detail": "Some conversions are risky. Use 'force: true' to proceed.",
                    "warnings": validation_warnings,
                    "validation_errors": hard_errors,
                }, status=status.HTTP_400_BAD_REQUEST)

            error_cols = {e["column"] for e in hard_errors}
            cast_results = _apply_casts(df, casts, error_cols, col_validated_data)

            successful = {r["column"]: casts[r["column"]] for r in cast_results if r["status"] == "ok"}
            if successful:
                dataset.column_casts = {**(dataset.column_casts or {}), **successful}
                try:
                    _commit_mutation(df, dataset, request.user, "CAST", {"columns": successful},
                                     extra_save_fields=["column_casts"])
                except RuntimeError as exc:
                    return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            all_results = hard_errors + cast_results
            failed_count = len(hard_errors) + sum(1 for r in cast_results if r.get("status") == "error")

            if not successful:
                return Response(
                    {"detail": "All requested casts failed.", "updated_columns": all_results},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            partial_failure = failed_count > 0
            return Response({"partial_failure": partial_failure, "updated_columns": all_results})

    def update_cell(self, request, dataset_id=None):
        """PATCH /datalab/update-cell/{dataset_id}/"""
        s = UpdateCellSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row_index = s.validated_data["row_index"]
        column = s.validated_data["column"].strip()
        value = s.validated_data["value"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if column not in df.columns:
                return Response(
                    {"detail": f"Column '{column}' not found in dataset."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if row_index >= len(df):
                return Response(
                    {"detail": f"Row index {row_index} is out of range (dataset has {len(df)} rows)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                df, coerced = df_update_cell(df, row_index, column, value)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            try:
                _commit_mutation(df, dataset, request.user, "UPDATE_CELL", {
                    "row_index": row_index, "column": column,
                    "value": coerced.isoformat() if hasattr(coerced, "isoformat") else str(coerced),
                })
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serialized = coerced.isoformat() if hasattr(coerced, "isoformat") else coerced
        return Response({"row_index": row_index, "column": column, "value": serialized})

    def rename_column(self, request, dataset_id=None):
        """POST /datalab/rename-column/{dataset_id}/"""
        s = RenameColumnSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        old_name = s.validated_data["old_name"].strip()
        new_name = s.validated_data["new_name"].strip()

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if old_name not in df.columns:
                return Response(
                    {"detail": f"Column '{old_name}' not found in dataset."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if new_name in df.columns:
                return Response(
                    {"detail": f"Column '{new_name}' already exists in dataset."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            df = df_rename_column(df, old_name, new_name)

            extra = []
            if dataset.column_casts and old_name in dataset.column_casts:
                dataset.column_casts[new_name] = dataset.column_casts.pop(old_name)
                extra = ["column_casts"]
            try:
                _commit_mutation(df, dataset, request.user, "RENAME_COLUMN",
                                 {"old_name": old_name, "new_name": new_name},
                                 extra_save_fields=extra)
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"old_name": old_name, "new_name": new_name, "columns": list(df.columns)})

    def drop_duplicates(self, request, dataset_id=None):
        """POST /datalab/drop-duplicates/{dataset_id}/"""
        s = DropDuplicatesSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        mode = s.validated_data["mode"]
        subset = s.validated_data.get("subset")
        keep = s.validated_data.get("keep", "first")

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            err_msg = _validate_subset_cols(subset, df)
            if err_msg:
                return Response({"detail": err_msg}, status=status.HTTP_400_BAD_REQUEST)

            rows_before = len(df)
            df = _apply_dedup(df, mode, subset, keep)
            rows_dropped = rows_before - len(df)

            if rows_dropped == 0:
                return Response({
                    "rows_before": rows_before,
                    "rows_after": rows_before,
                    "rows_dropped": 0,
                    "detail": "No duplicate rows found.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "DROP_DUPLICATES",
                                 {"mode": mode, "rows_dropped": rows_dropped})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"mode": mode, "rows_before": rows_before, "rows_after": len(df), "rows_dropped": rows_dropped})

    def replace_values(self, request, dataset_id=None):
        """POST /datalab/replace-values/{dataset_id}/"""
        s = ReplaceValuesSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        replacements = s.validated_data["replacements"]
        columns = s.validated_data.get("columns")

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if columns is not None:
                if not isinstance(columns, list) or not columns:
                    return Response(
                        {"detail": "'columns' must be a non-empty list of column names."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                unknown_cols = [c for c in columns if c not in df.columns]
                if unknown_cols:
                    return Response(
                        {"detail": f"Columns not found in dataset: {unknown_cols}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            df, cells_replaced = df_replace_values(df, replacements, columns)

            if cells_replaced == 0:
                return Response({
                    "replacements": replacements,
                    "columns_affected": columns or list(df.columns),
                    "cells_replaced": 0,
                    "detail": "No matching values found.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "REPLACE_VALUES",
                                 {"cells_replaced": cells_replaced, "columns": columns})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "replacements": replacements,
            "columns_affected": columns or list(df.columns),
            "cells_replaced": cells_replaced,
        })

    def drop_nulls(self, request, dataset_id=None):
        """POST /datalab/drop-nulls/{dataset_id}/"""
        s = DropNullsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        axis = s.validated_data["axis"]
        how = s.validated_data.get("how", "any")
        subset = s.validated_data.get("subset")
        thresh_pct = s.validated_data.get("thresh_pct")

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if axis == "rows" and subset is not None:
                err_msg = _validate_subset_cols(subset, df)
                if err_msg:
                    return Response({"detail": err_msg}, status=status.HTTP_400_BAD_REQUEST)

            df, stats = df_drop_nulls(df, axis, how=how, subset=subset, thresh_pct=thresh_pct)
            dropped_count = stats.get("rows_dropped") or len(stats.get("columns_dropped", []))

            if dropped_count == 0:
                return Response({"axis": axis, **stats, "detail": "No null rows/columns matched the criteria."})

            try:
                _commit_mutation(df, dataset, request.user, "DROP_NULLS", {"axis": axis, **stats})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"axis": axis, **stats})

    def fill_derived(self, request, dataset_id=None):
        """POST /datalab/fill-derived/{dataset_id}/"""
        with transaction.atomic():
            err, ctx = _resolve_formula_context(request, dataset_id, target_field="target", lock=True)
            if err:
                return err
            df, dataset = ctx["df"], ctx["dataset"]
            target, formula = ctx["target"], ctx["formula"]
            operand_a, operand_b = ctx["operand_a"], ctx["operand_b"]

            df, cells_filled = df_fill_derived(df, target, formula, operand_a, operand_b)

            if cells_filled == 0:
                return Response({
                    "target": target, "formula": formula,
                    "operand_a": operand_a, "operand_b": operand_b,
                    "cells_filled": 0,
                    "detail": f"No null values in '{target}' with complete operand data.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "FILL_DERIVED",
                                 {"target": target, "formula": formula, "cells_filled": cells_filled})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "target": target, "formula": formula,
            "operand_a": operand_a, "operand_b": operand_b,
            "cells_filled": cells_filled,
        })

    def fix_formula(self, request, dataset_id=None):
        """POST /datalab/fix-formula/{dataset_id}/"""
        with transaction.atomic():
            err, ctx = _resolve_formula_context(request, dataset_id, target_field="target", lock=True)
            if err:
                return err
            df, dataset = ctx["df"], ctx["dataset"]
            target, formula = ctx["target"], ctx["formula"]
            operand_a, operand_b, tolerance = ctx["operand_a"], ctx["operand_b"], ctx["tolerance"]

            df, cells_fixed = df_fix_formula_errors(df, target, formula, operand_a, operand_b, tolerance)

            if cells_fixed == 0:
                return Response({
                    "target": target, "formula": formula,
                    "operand_a": operand_a, "operand_b": operand_b,
                    "tolerance": tolerance, "cells_fixed": 0,
                    "detail": "No inconsistent rows found within the given tolerance.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "FIX_FORMULA",
                                 {"target": target, "formula": formula, "cells_fixed": cells_fixed})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "target": target, "formula": formula,
            "operand_a": operand_a, "operand_b": operand_b,
            "tolerance": tolerance, "cells_fixed": cells_fixed,
        })

    def fill_nulls(self, request, dataset_id=None):
        """POST /datalab/fill-nulls/{dataset_id}/"""
        s = FillNullsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        strategy = s.validated_data["strategy"]
        columns = s.validated_data.get("columns")
        value = s.validated_data.get("value")

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if columns is not None:
                err_msg = _validate_subset_cols(columns, df)
                if err_msg:
                    return Response({"detail": err_msg}, status=status.HTTP_400_BAD_REQUEST)

            df, cells_filled, skipped_columns = df_fill_nulls(df, strategy, columns=columns, value=value)

            if cells_filled == 0:
                return Response({
                    "strategy": strategy, "cells_filled": 0,
                    "skipped_columns": skipped_columns,
                    "detail": "No null values found to fill.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "FILL_NULLS",
                                 {"strategy": strategy, "cells_filled": cells_filled})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"strategy": strategy, "cells_filled": cells_filled, "skipped_columns": skipped_columns})

    def trim_outliers(self, request, dataset_id=None):
        """POST /datalab/trim-outliers/{dataset_id}/"""
        s = OutlierParamsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns_raw = s.validated_data["columns"]
        method = s.validated_data["method"]
        threshold = s.validated_data["threshold"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            err, columns = _parse_numeric_columns(columns_raw, df)
            if err:
                return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

            rows_before = len(df)
            df, rows_dropped = df_trim_outliers(df, columns, method=method, threshold=threshold)

            if rows_dropped == 0:
                return Response({
                    "columns": columns, "method": method, "threshold": threshold,
                    "rows_before": rows_before, "rows_after": rows_before,
                    "rows_dropped": 0, "detail": "No outlier rows found.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "TRIM_OUTLIERS",
                                 {"method": method, "threshold": threshold, "rows_dropped": rows_dropped})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "columns": columns, "method": method, "threshold": threshold,
            "rows_before": rows_before, "rows_after": len(df), "rows_dropped": rows_dropped,
        })

    def impute_outliers(self, request, dataset_id=None):
        """POST /datalab/impute-outliers/{dataset_id}/"""
        s = ImputeOutliersSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns_raw = s.validated_data["columns"]
        method = s.validated_data["method"]
        threshold = s.validated_data["threshold"]
        strategy = s.validated_data["strategy"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            err, columns = _parse_numeric_columns(columns_raw, df)
            if err:
                return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

            df, cells_imputed = df_impute_outliers(df, columns, method=method, threshold=threshold, strategy=strategy)

            if cells_imputed == 0:
                return Response({
                    "columns": columns, "method": method, "threshold": threshold,
                    "strategy": strategy, "cells_imputed": 0, "detail": "No outliers found.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "IMPUTE_OUTLIERS",
                                 {"method": method, "strategy": strategy, "cells_imputed": cells_imputed})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "columns": columns, "method": method, "threshold": threshold,
            "strategy": strategy, "cells_imputed": cells_imputed,
        })

    def cap_outliers(self, request, dataset_id=None):
        """POST /datalab/cap-outliers/{dataset_id}/"""
        s = CapOutliersSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns_raw = s.validated_data["columns"]
        lower_pct = s.validated_data["lower_pct"]
        upper_pct = s.validated_data["upper_pct"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            err, columns = _parse_numeric_columns(columns_raw, df)
            if err:
                return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

            df, cells_capped = df_cap_outliers(df, columns, lower_pct=lower_pct, upper_pct=upper_pct)

            if cells_capped == 0:
                return Response({
                    "columns": columns, "lower_pct": lower_pct, "upper_pct": upper_pct,
                    "cells_capped": 0, "detail": "No values outside the percentile bounds.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "CAP_OUTLIERS",
                                 {"lower_pct": lower_pct, "upper_pct": upper_pct, "cells_capped": cells_capped})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"columns": columns, "lower_pct": lower_pct, "upper_pct": upper_pct, "cells_capped": cells_capped})

    def transform_column(self, request, dataset_id=None):
        """POST /datalab/transform-column/{dataset_id}/"""
        s = TransformColumnSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns_raw = s.validated_data["columns"]
        function = s.validated_data["function"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            err, columns = _parse_numeric_columns(columns_raw, df)
            if err:
                return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

            df, transformed, skipped = df_transform_column(df, columns, function=function)

            if not transformed:
                return Response({
                    "function": function, "transformed_columns": [],
                    "skipped_columns": skipped, "detail": "No columns were transformed.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "TRANSFORM_COLUMN",
                                 {"function": function, "columns": transformed})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"function": function, "transformed_columns": transformed, "skipped_columns": skipped})

    def drop_columns(self, request, dataset_id=None):
        """POST /datalab/drop-columns/{dataset_id}/"""
        s = DropColumnsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns = s.validated_data["columns"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            unknown = [c for c in columns if c not in df.columns]
            if unknown:
                return Response(
                    {"detail": f"Columns not found in dataset: {unknown}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            df, dropped = df_drop_columns(df, columns)

            extra = []
            if dataset.column_casts and any(c in dataset.column_casts for c in dropped):
                dataset.column_casts = {k: v for k, v in dataset.column_casts.items() if k not in dropped}
                extra = ["column_casts"]
            try:
                _commit_mutation(df, dataset, request.user, "DROP_COLUMNS",
                                 {"columns_dropped": dropped}, extra_save_fields=extra)
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"columns_dropped": dropped, "remaining_columns": list(df.columns)})

    def add_column(self, request, dataset_id=None):
        """POST /datalab/add-column/{dataset_id}/"""
        s = AddColumnSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        new_name = s.validated_data["new_name"].strip()
        formula = s.validated_data["formula"]
        operand_a = s.validated_data["operand_a"].strip()
        operand_b = s.validated_data["operand_b"].strip()

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if new_name in df.columns:
                return Response(
                    {"detail": f"Column '{new_name}' already exists. Use rename-column or choose a different name."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            missing = [c for c in [operand_a, operand_b] if c not in df.columns]
            if missing:
                return Response(
                    {"detail": f"Columns not found in dataset: {missing}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            non_numeric = [c for c in [operand_a, operand_b] if not pd.api.types.is_numeric_dtype(df[c])]
            if non_numeric:
                return Response(
                    {"detail": f"Operand columns must be numeric: {non_numeric}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            df = df_add_column(df, new_name, formula, operand_a, operand_b)

            try:
                _commit_mutation(df, dataset, request.user, "ADD_COLUMN",
                                 {"new_name": new_name, "formula": formula,
                                  "operand_a": operand_a, "operand_b": operand_b})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "new_column": new_name, "formula": formula,
            "operand_a": operand_a, "operand_b": operand_b,
            "total_columns": len(df.columns),
        })

    def filter_rows(self, request, dataset_id=None):
        """POST /datalab/filter-rows/{dataset_id}/"""
        s = FilterRowsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        column = s.validated_data["column"].strip()
        operator = s.validated_data["operator"]
        value = s.validated_data.get("value")

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if column not in df.columns:
                return Response(
                    {"detail": f"Column '{column}' not found in dataset."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                df, rows_before, rows_after = df_filter_rows(df, column, operator, value)
            except (TypeError, ValueError) as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            rows_removed = rows_before - rows_after

            if rows_removed == 0:
                return Response({
                    "column": column, "operator": operator, "value": value,
                    "rows_before": rows_before, "rows_after": rows_after,
                    "rows_removed": 0,
                    "detail": "No rows were removed — all rows matched the filter.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "FILTER_ROWS",
                                 {"column": column, "operator": operator,
                                  "value": str(value), "rows_removed": rows_removed})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "column": column, "operator": operator, "value": value,
            "rows_before": rows_before, "rows_after": rows_after, "rows_removed": rows_removed,
        })

    def clean_string(self, request, dataset_id=None):
        """POST /datalab/clean-string/{dataset_id}/"""
        s = CleanStringSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns = s.validated_data["columns"]
        operation = s.validated_data["operation"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            unknown = [c for c in columns if c not in df.columns]
            if unknown:
                return Response(
                    {"detail": f"Columns not found in dataset: {unknown}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            non_string = [
                c for c in columns
                if not (
                    pd.api.types.is_object_dtype(df[c])
                    or pd.api.types.is_string_dtype(df[c])
                    or isinstance(df[c].dtype, pd.CategoricalDtype)
                )
            ]
            if non_string:
                return Response(
                    {"detail": f"String operations only apply to text columns: {non_string}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            df, cells_changed = df_clean_string_column(df, columns, operation)

            if cells_changed == 0:
                return Response({
                    "operation": operation, "columns": columns,
                    "cells_changed": 0, "detail": "No values were changed.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "CLEAN_STRING",
                                 {"operation": operation, "columns": columns, "cells_changed": cells_changed})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"operation": operation, "columns": columns, "cells_changed": cells_changed})

    def scale_columns(self, request, dataset_id=None):
        """POST /datalab/scale-columns/{dataset_id}/"""
        s = ScaleColumnsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns_raw = s.validated_data["columns"]
        method = s.validated_data["method"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            err, columns = _parse_numeric_columns(columns_raw, df)
            if err:
                return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

            df, scaled, skipped = df_scale_columns(df, columns, method=method)

            if not scaled:
                return Response({
                    "method": method, "scaled_columns": [],
                    "skipped_columns": skipped, "detail": "No columns were scaled.",
                })

            try:
                _commit_mutation(df, dataset, request.user, "SCALE_COLUMNS",
                                 {"method": method, "columns": scaled})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"method": method, "scaled_columns": scaled, "skipped_columns": skipped})

    def extract_datetime(self, request, dataset_id=None):
        """POST /datalab/extract-datetime/{dataset_id}/"""
        s = ExtractDatetimeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        column = s.validated_data["column"].strip()
        features = s.validated_data["features"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            if column not in df.columns:
                return Response(
                    {"detail": f"Column '{column}' not found in dataset."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            conflict = [f"{column}_{f}" for f in features if f"{column}_{f}" in df.columns]
            if conflict:
                return Response(
                    {"detail": f"Columns already exist: {conflict}. Rename or drop them first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            df, added_columns = df_extract_datetime_features(df, column, features)

            try:
                _commit_mutation(df, dataset, request.user, "EXTRACT_DATETIME",
                                 {"source_column": column, "added_columns": added_columns})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"source_column": column, "added_columns": added_columns, "total_columns": len(df.columns)})

    def encode_columns(self, request, dataset_id=None):
        """POST /datalab/encode-columns/{dataset_id}/"""
        s = EncodeColumnsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        columns = s.validated_data["columns"]
        strategy = s.validated_data["strategy"]

        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            unknown = [c for c in columns if c not in df.columns]
            if unknown:
                return Response(
                    {"detail": f"Columns not found in dataset: {unknown}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            numeric_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
            if numeric_cols:
                return Response(
                    {"detail": f"Encoding requires categorical or text columns. These are numeric: {numeric_cols}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if strategy == "onehot":
                high_card = [c for c in columns if df[c].nunique() > _ONE_HOT_MAX_CARDINALITY]
                if high_card:
                    return Response(
                        {"detail": (
                            f"One-hot encoding is limited to columns with ≤ {_ONE_HOT_MAX_CARDINALITY} "
                            f"unique values. High-cardinality columns: {high_card}"
                        )},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            try:
                df, result_info = df_encode_columns(df, columns, strategy=strategy)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            try:
                _commit_mutation(df, dataset, request.user, "ENCODE_COLUMNS",
                                 {"strategy": strategy, "columns": columns})
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"strategy": strategy, "result": result_info, "total_columns": len(df.columns)})

    def normalize_column_names(self, request, dataset_id=None):
        """POST /datalab/normalize-column-names/{dataset_id}/"""
        with transaction.atomic():
            err, dataset, df = _load_and_lock(dataset_id, request.user)
            if err:
                return err

            try:
                df, rename_map = df_normalize_column_names(df)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            if not rename_map:
                return Response({
                    "detail": "All column names are already normalized.",
                    "columns": list(df.columns),
                })

            if dataset.column_casts:
                dataset.column_casts = {rename_map.get(k, k): v for k, v in dataset.column_casts.items()}
            try:
                _commit_mutation(df, dataset, request.user, "NORMALIZE_COLUMN_NAMES",
                                 {"renamed": rename_map}, extra_save_fields=["column_casts"])
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"renamed": rename_map, "columns": list(df.columns)})

    @action(detail=True, methods=["get"])
    def suggest_cleaning(self, request, dataset_id=None):
        """
        GET /api/v1/datalab/suggest-cleaning/{dataset_id}/
        Streams AI-generated cleaning suggestions based on dataset stats.
        """
        dataset = get_object_or_404(Dataset, pk=dataset_id, user=request.user)
        df = get_cached_dataframe(dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date)
        if df is None:
            return Response({"detail": _LOAD_FAILED}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if dataset.column_casts:
            df = apply_stored_casts(df, dataset.column_casts)

        # Build a stats summary for the AI
        stats_summary = []
        for col in df.columns:
            stats_summary.append({
                "column": col,
                "dtype": str(df[col].dtype),
                "null_pct": round(df[col].isna().mean() * 100, 1),
                "unique_count": int(df[col].nunique()),
            })

        response = StreamingHttpResponse(
            stream_suggest_cleaning(list(df.columns), stats_summary),
            content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
