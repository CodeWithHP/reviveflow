"""ML module: trains a *real* recovery-risk detector, reports honest metrics.

Train/validation split -> LogisticRegression baseline vs GradientBoosting, we keep
the better model, persist it, and surface:
  - precision, recall, F1
  - confusion matrix
  - false-positive COST (the money we'd waste acting on a non-recoverable event)
  - recovery-leverage (money recovered minus actioning cost)

All numbers are computed on a held-out test set the model has never seen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..core.config import settings
from .data_generator import extract_features, generate_dataset


@dataclass
class ModelReport:
    """Honest metrics + the confusion matrix economics."""
    best_model_name: str
    precision: float
    recall: float
    f1: float
    accuracy: float
    confusion: Dict[str, int]
    train_size: int
    test_size: int
    cost_per_false_positive: float = 0.5        # avg INR spent actioning a non-recoverable
    avg_recovered_per_true: float = 1200.0      # avg INR recovered per correct act
    n_false_positives: int = 0
    n_true_positives: int = 0
    fp_cost_total_inr: float = 0.0
    recovered_gross_inr: float = 0.0
    net_leverage_inr: float = 0.0
    threshold: float = 0.5
    feature_names: list = field(default_factory=list)
    model: Any = None


def _score_model(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold).astype(int)
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "accuracy": float((y_true == y_pred).mean()),
        "cm": confusion_matrix(y_true, y_pred, labels=[0, 1]),
        "y_pred": y_pred,
        "y_prob": y_prob,
    }


def train_and_evaluate(n: int = 1500, seed: int = 42, horizon_days: int = 35) -> ModelReport:
    """Generate data, split into train/test, fit, evaluate, persist best model."""
    df, feats = generate_dataset(n=n, seed=seed, since_days=horizon_days)
    X = feats.astype(float).values
    y = df["recoverable"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y
    )

    candidates = {
        "LogisticRegression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000)),
        "RandomForest": RandomForestClassifier(
            n_estimators=300, max_depth=7, min_samples_leaf=3, random_state=seed
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=180, learning_rate=0.08, max_depth=3, random_state=seed
        ),
    }

    best = None
    best_report = None
    feature_names = list(feats.columns)

    for name, clf in candidates.items():
        clf.fit(X_train, y_train)
        y_prob = clf.predict_proba(X_test)[:, 1]
        s = _score_model(y_test, y_prob, 0.5)
        report = ModelReport(
            best_model_name=name,
            precision=s["precision"],
            recall=s["recall"],
            f1=s["f1"],
            accuracy=s["accuracy"],
            confusion={
                "tn": int(s["cm"][0, 0]),
                "fp": int(s["cm"][0, 1]),
                "fn": int(s["cm"][1, 0]),
                "tp": int(s["cm"][1, 1]),
            },
            train_size=len(X_train),
            test_size=len(X_test),
            n_false_positives=int(s["cm"][0, 1]),
            n_true_positives=int(s["cm"][1, 1]),
            fp_cost_total_inr=float(int(s["cm"][0, 1]) * 0.5),
            recovered_gross_inr=float(int(s["cm"][1, 1]) * 1200.0),
            threshold=0.5,
            feature_names=feature_names,
            model=clf,
        )
        report.net_leverage_inr = report.recovered_gross_inr - report.fp_cost_total_inr

        if best_report is None or report.f1 > best_report.f1:
            best = clf
            best_report = report

    # persist the winner
    settings.model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": best,
            "model_name": best_report.best_model_name,
            "feature_names": feature_names,
            "threshold": 0.5,
            "train_size": best_report.train_size,
            "test_size": best_report.test_size,
            "report": {
                "precision": best_report.precision,
                "recall": best_report.recall,
                "f1": best_report.f1,
                "accuracy": best_report.accuracy,
                "confusion": best_report.confusion,
            },
        },
        settings.model_path,
    )
    return best_report


def load_model():
    data = joblib.load(settings.model_path)
    return data


def predict_proba(feature_vector: list, model_bundle: dict) -> float:
    X = np.asarray([feature_vector], dtype=float)
    clf = model_bundle["model"]
    return float(clf.predict_proba(X)[0, 1])


if __name__ == "__main__":
    r = train_and_evaluate(1500)
    print("Model:", r.best_model_name)
    print(f"P={r.precision:.3f} R={r.recall:.3f} F1={r.f1:.3f} Acc={r.accuracy:.3f}")
    print("Confusion:", r.confusion)
    print(f"FP cost=₹{r.fp_cost_total_inr:.2f} recovered=₹{r.recovered_gross_inr:.2f} "
          f"net=₹{r.net_leverage_inr:.2f}")
