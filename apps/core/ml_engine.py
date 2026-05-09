import io
import logging
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import Lasso, LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    silhouette_score,
)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

TASK_TYPES = {"regression", "classification", "clustering"}

ALGORITHMS = {
    "regression": {
        "linear":           LinearRegression,
        "ridge":            Ridge,
        "lasso":            Lasso,
        "random_forest":    RandomForestRegressor,
        "gradient_boost":   GradientBoostingRegressor,
    },
    "classification": {
        "logistic":         LogisticRegression,
        "random_forest":    RandomForestClassifier,
        "gradient_boost":   GradientBoostingClassifier,
        "knn":              KNeighborsClassifier,
    },
    "clustering": {
        "kmeans":           KMeans,
        "dbscan":           DBSCAN,
    },
}

# Default hyperparameters per algorithm
_DEFAULTS: dict[str, dict] = {
    "linear":           {},
    "ridge":            {"alpha": 1.0},
    "lasso":            {"alpha": 1.0},
    "random_forest":    {"n_estimators": 100, "max_depth": None, "random_state": 42},
    "gradient_boost":   {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.1, "random_state": 42},
    "logistic":         {"max_iter": 1000, "random_state": 42},
    "knn":              {"n_neighbors": 5},
    "kmeans":           {"n_clusters": 3, "random_state": 42, "n_init": 10},
    "dbscan":           {"eps": 0.5, "min_samples": 5},
}

# Allowed user-overridable hyperparameters per algorithm (whitelist)
HYPERPARAMS_SCHEMA: dict[str, dict] = {
    "linear":           {},
    "ridge":            {"alpha": float},
    "lasso":            {"alpha": float},
    "random_forest":    {"n_estimators": int, "max_depth": int},
    "gradient_boost":   {"n_estimators": int, "max_depth": int, "learning_rate": float},
    "logistic":         {"max_iter": int},
    "knn":              {"n_neighbors": int},
    "kmeans":           {"n_clusters": int},
    "dbscan":           {"eps": float, "min_samples": int},
}

TEST_SIZE_DEFAULT = 0.2


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_algorithms_for_task(task_type: str) -> list[str]:
    return list(ALGORITHMS.get(task_type, {}).keys())


def validate_hyperparams(algorithm: str, hyperparams: dict) -> tuple[bool, str, dict]:
    """
    Validate and coerce user-supplied hyperparams against the whitelist schema.
    Returns (ok, error_message, sanitized_params).
    """
    schema = HYPERPARAMS_SCHEMA.get(algorithm, {})
    sanitized = {}
    for key, value in hyperparams.items():
        if key not in schema:
            return False, f"Unknown hyperparameter '{key}' for algorithm '{algorithm}'.", {}
        expected_type = schema[key]
        try:
            sanitized[key] = expected_type(value)
        except (TypeError, ValueError):
            return False, f"Hyperparameter '{key}' must be of type {expected_type.__name__}.", {}
    return True, "", sanitized


def _build_model(algorithm: str, hyperparams: dict):
    """Instantiate a sklearn estimator with merged defaults + user params."""
    task_type = next(
        (t for t, algos in ALGORITHMS.items() if algorithm in algos), None
    )
    if task_type is None:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    cls = ALGORITHMS[task_type][algorithm]
    params = {**_DEFAULTS.get(algorithm, {}), **hyperparams}
    return cls(**params)


def _extract_feature_importances(model, feature_names: list[str]) -> list[dict]:
    """Extract feature importances from tree-based models or coefficients from linear ones."""
    importances = None
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        coef = model.coef_
        importances = np.abs(coef.flatten() if coef.ndim > 1 else coef)

    if importances is None:
        return []

    total = importances.sum()
    return sorted(
        [
            {
                "feature": name,
                "importance": round(float(imp), 6),
                "importance_pct": round(float(imp / total * 100), 2) if total > 0 else 0.0,
            }
            for name, imp in zip(feature_names, importances)
        ],
        key=lambda x: x["importance"],
        reverse=True,
    )


def _regression_metrics(y_true, y_pred) -> dict:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "r2":   round(float(r2_score(y_true, y_pred)), 6),
        "mae":  round(float(mean_absolute_error(y_true, y_pred)), 6),
        "mse":  round(float(mse), 6),
        "rmse": round(float(np.sqrt(mse)), 6),
    }


def _classification_metrics(y_true, y_pred) -> dict:
    avg = "binary" if len(np.unique(y_true)) == 2 else "weighted"
    return {
        "accuracy":  round(float(accuracy_score(y_true, y_pred)), 6),
        "precision": round(float(precision_score(y_true, y_pred, average=avg, zero_division=0)), 6),
        "recall":    round(float(recall_score(y_true, y_pred, average=avg, zero_division=0)), 6),
        "f1":        round(float(f1_score(y_true, y_pred, average=avg, zero_division=0)), 6),
    }


def _clustering_metrics(X, labels) -> dict:
    unique_labels = set(labels)
    n_clusters = len(unique_labels - {-1})  # exclude DBSCAN noise label
    metrics = {"n_clusters": n_clusters}
    if n_clusters > 1:
        try:
            metrics["silhouette_score"] = round(float(silhouette_score(X, labels)), 6)
        except Exception:
            metrics["silhouette_score"] = None
    return metrics


# ── Public API ─────────────────────────────────────────────────────────────────

def train_model(
    df: pd.DataFrame,
    task_type: str,
    algorithm: str,
    feature_columns: list[str],
    target_column: str | None,
    hyperparams: dict,
    test_size: float = TEST_SIZE_DEFAULT,
) -> dict:
    """
    Train a model and return a result dict:
      - model_bytes: joblib-serialized bytes
      - metrics: dict of evaluation metrics
      - feature_importances: list of {feature, importance, importance_pct}
      - training_time_seconds: float
      - train_samples / test_samples: int
      - label_classes: list (classification only)
    """
    started = time.time()

    # ── Prepare features ──────────────────────────────────────────────────────
    X = df[feature_columns].copy()

    # Encode any remaining object columns (categorical)
    label_encoders: dict[str, LabelEncoder] = {}
    for col in X.select_dtypes(include=["object", "category"]).columns:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col].astype(str))
        label_encoders[col] = le

    X = X.astype(float)

    if task_type == "clustering":
        model = _build_model(algorithm, hyperparams)
        model.fit(X)
        labels = model.labels_ if hasattr(model, "labels_") else model.predict(X)
        metrics = _clustering_metrics(X, labels)
        if hasattr(model, "inertia_"):
            metrics["inertia"] = round(float(model.inertia_), 4)

        buf = io.BytesIO()
        joblib.dump({"model": model, "label_encoders": label_encoders}, buf)

        return {
            "model_bytes": buf.getvalue(),
            "metrics": metrics,
            "feature_importances": [],
            "training_time_seconds": round(time.time() - started, 3),
            "train_samples": len(X),
            "test_samples": 0,
            "label_classes": [],
        }

    # ── Supervised: prepare target ────────────────────────────────────────────
    y = df[target_column].copy()
    label_classes = []

    if task_type == "classification":
        if y.dtype == object or str(y.dtype) == "category":
            le_y = LabelEncoder()
            y = le_y.fit_transform(y.astype(str))
            label_classes = list(le_y.classes_)
        else:
            label_classes = [str(c) for c in sorted(y.unique())]

    y = pd.Series(y).astype(float if task_type == "regression" else int)

    # ── Train / test split ────────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42
    )

    model = _build_model(algorithm, hyperparams)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    metrics = (
        _regression_metrics(y_test, y_pred)
        if task_type == "regression"
        else _classification_metrics(y_test, y_pred)
    )

    buf = io.BytesIO()
    joblib.dump({"model": model, "label_encoders": label_encoders}, buf)

    return {
        "model_bytes": buf.getvalue(),
        "metrics": metrics,
        "feature_importances": _extract_feature_importances(model, feature_columns),
        "training_time_seconds": round(time.time() - started, 3),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "label_classes": label_classes,
    }


def predict_with_model(model_bytes: bytes, df: pd.DataFrame, feature_columns: list[str]) -> list:
    """
    Run predictions on df using a stored model artifact.
    Returns a list of predictions (one per row).
    """
    artifact = joblib.load(io.BytesIO(model_bytes))
    model = artifact["model"]
    label_encoders = artifact.get("label_encoders", {})

    X = df[feature_columns].copy()
    for col, le in label_encoders.items():
        if col in X.columns:
            X[col] = le.transform(X[col].astype(str))
    X = X.astype(float)

    preds = model.predict(X)
    return [round(float(p), 6) if isinstance(p, (float, np.floating)) else int(p) for p in preds]
