import logging
import threading

from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.data_engine import apply_stored_casts, get_cached_dataframe
from apps.core.ml_engine import (
    ALGORITHMS,
    HYPERPARAMS_SCHEMA,
    predict_with_model,
    train_model,
    validate_hyperparams,
)
from apps.datasets.models import Dataset

from .models import MLModel
from .serializers import MLModelSerializer, PredictSerializer, TrainModelSerializer

logger = logging.getLogger(__name__)


def _load_df(dataset):
    """Load and cast a dataset's DataFrame. Returns (df, error_response)."""
    df = get_cached_dataframe(
        dataset.id, dataset.file.path, dataset.file_format, version=dataset.updated_date
    )
    if df is None:
        return None, Response(
            {"detail": "Could not load dataset file."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if dataset.column_casts:
        df = apply_stored_casts(df, dataset.column_casts)
    return df, None


def _run_training(ml_model_id, df_clean):
    """Background task to train the model and update its status."""
    from django.db import connections
    try:
        ml_model = MLModel.objects.get(pk=ml_model_id)
        ml_model.progress = 10
        ml_model.save(update_fields=["progress"])

        result = train_model(
            df=df_clean,
            task_type=ml_model.task_type,
            algorithm=ml_model.algorithm,
            feature_columns=ml_model.feature_columns,
            target_column=ml_model.target_column or None,
            hyperparams=ml_model.hyperparams,
            test_size=ml_model.test_size,
        )

        ml_model.progress = 90
        ml_model.save(update_fields=["progress"])

        # Persist model artifact
        filename = f"{ml_model.pk}.joblib"
        ml_model.model_file.save(filename, ContentFile(result["model_bytes"]), save=False)
        
        ml_model.status              = MLModel.STATUS_READY
        ml_model.progress            = 100
        ml_model.metrics             = result["metrics"]
        ml_model.feature_importances = result["feature_importances"]
        ml_model.label_classes       = result["label_classes"]
        ml_model.train_samples       = result["train_samples"]
        ml_model.test_samples        = result["test_samples"]
        ml_model.training_time_seconds = result["training_time_seconds"]
        ml_model.save()

    except Exception as exc:
        logger.exception("Background training failed for MLModel %s", ml_model_id)
        try:
            ml_model = MLModel.objects.get(pk=ml_model_id)
            ml_model.status = MLModel.STATUS_FAILED
            ml_model.error_message = str(exc)
            ml_model.save(update_fields=["status", "error_message"])
        except Exception:
            pass
    finally:
        connections.close_all()


class MLModelViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """GET /mlstudio/"""
        qs = MLModel.objects.filter(user=request.user).select_related("dataset")
        dataset_id = request.query_params.get("dataset_id")
        if dataset_id:
            qs = qs.filter(dataset_id=dataset_id)
        task_type = request.query_params.get("task_type")
        if task_type:
            qs = qs.filter(task_type=task_type)
        return Response(MLModelSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        """GET /mlstudio/{id}/"""
        model = get_object_or_404(MLModel, pk=pk, user=request.user)
        return Response(MLModelSerializer(model).data)

    def create(self, request):
        """
        POST /mlstudio/
        Validate input, launch background training, return immediately with 202 Accepted.
        """
        s = TrainModelSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        dataset = get_object_or_404(Dataset, pk=data["dataset_id"], user=request.user)

        df, err = _load_df(dataset)
        if err:
            return err

        # Column existence checks
        all_cols = list(df.columns)
        missing_features = [c for c in data["feature_columns"] if c not in all_cols]
        if missing_features:
            return Response(
                {"detail": f"Feature columns not found in dataset: {missing_features}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_col = data.get("target_column", "")
        if data["task_type"] != "clustering":
            if target_col not in all_cols:
                return Response(
                    {"detail": f"Target column '{target_col}' not found in dataset."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if target_col in data["feature_columns"]:
                return Response(
                    {"detail": "Target column must not appear in feature_columns."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Drop rows with any null in feature + target columns
        cols_to_check = list(data["feature_columns"]) + ([target_col] if target_col else [])
        df_clean = df[cols_to_check].dropna()
        if len(df_clean) < 10:
            return Response(
                {"detail": f"Not enough clean rows to train ({len(df_clean)} after dropping nulls). Need at least 10."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate & sanitize hyperparams
        _, _, sanitized_hp = validate_hyperparams(data["algorithm"], data.get("hyperparams", {}))

        # Create model record (status=training)
        ml_model = MLModel.objects.create(
            user=request.user,
            dataset=dataset,
            name=data["name"],
            description=data.get("description", ""),
            task_type=data["task_type"],
            algorithm=data["algorithm"],
            feature_columns=data["feature_columns"],
            target_column=target_col,
            hyperparams=sanitized_hp,
            test_size=data["test_size"],
            status=MLModel.STATUS_TRAINING,
            progress=0,
        )

        # Launch background thread
        thread = threading.Thread(target=_run_training, args=(ml_model.pk, df_clean))
        thread.start()

        return Response(MLModelSerializer(ml_model).data, status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, pk=None):
        """DELETE /mlstudio/{id}/"""
        model = get_object_or_404(MLModel, pk=pk, user=request.user)
        if model.model_file:
            model.model_file.delete(save=False)
        model.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="predict")
    def predict(self, request, pk=None):
        """
        POST /mlstudio/{id}/predict/
        Body: { "dataset_id": <optional int> }
        Returns predictions for every row in the dataset.
        """
        ml_model = get_object_or_404(MLModel, pk=pk, user=request.user)
        if not ml_model.is_ready:
            return Response(
                {"detail": f"Model is not ready (status: {ml_model.status})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        s = PredictSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        dataset_id = s.validated_data.get("dataset_id") or ml_model.dataset_id

        dataset = get_object_or_404(Dataset, pk=dataset_id, user=request.user)
        df, err = _load_df(dataset)
        if err:
            return err

        missing = [c for c in ml_model.feature_columns if c not in df.columns]
        if missing:
            return Response(
                {"detail": f"Dataset is missing feature columns: {missing}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Load model bytes
        try:
            ml_model.model_file.open("rb")
            model_bytes = ml_model.model_file.read()
            ml_model.model_file.close()
        except Exception:
            logger.exception("Could not read model file for MLModel %s", ml_model.pk)
            return Response(
                {"detail": "Could not read model artifact."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Prepare df — drop nulls in feature columns only
        df_pred = df[ml_model.feature_columns].dropna()
        original_index = df_pred.index.tolist()

        try:
            predictions = predict_with_model(model_bytes, df_pred, ml_model.feature_columns)
        except Exception as exc:
            logger.exception("Prediction failed for MLModel %s", ml_model.pk)
            return Response(
                {"detail": f"Prediction failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "model_id":       ml_model.pk,
            "model_name":     ml_model.name,
            "dataset_id":     dataset.pk,
            "task_type":      ml_model.task_type,
            "algorithm":      ml_model.algorithm,
            "feature_columns": ml_model.feature_columns,
            "target_column":  ml_model.target_column,
            "label_classes":  ml_model.label_classes,
            "total_rows":     len(df),
            "predicted_rows": len(predictions),
            "predictions": [
                {"row_index": idx, "prediction": pred}
                for idx, pred in zip(original_index, predictions)
            ],
        })

    @action(detail=False, methods=["get"], url_path="algorithms")
    def algorithms(self, request):
        """GET /mlstudio/algorithms/?task_type=regression"""
        task_type = request.query_params.get("task_type")
        if task_type and task_type not in ALGORITHMS:
            return Response(
                {"detail": f"'task_type' must be one of: {list(ALGORITHMS.keys())}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = {}
        for t, algos in ALGORITHMS.items():
            if task_type and t != task_type:
                continue
            result[t] = [
                {
                    "algorithm": algo,
                    "hyperparams": {
                        k: v.__name__ for k, v in HYPERPARAMS_SCHEMA.get(algo, {}).items()
                    },
                }
                for algo in algos
            ]
        return Response(result)
