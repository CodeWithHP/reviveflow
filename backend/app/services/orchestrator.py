"""Orchestrator - ties data, ML, workflow & metrics into a single service.

Exposes batch evaluation (the Track-03 bar: "measured money recovered across a
batch") and singleton run endpoints for the API.
"""
from __future__ import annotations

import pandas as pd

from ..models.schemas import RevenueEvent, RevenueEventType
from .data_generator import generate_dataset
from .diagnosis_engine import DiagnosisEngine
from .ml_model import train_and_evaluate
from .workflow_engine import WorkflowEngine


class ReviveOrchestrator:
    """High-level API the FastAPI layer talks to."""

    def __init__(self, retrain: bool = None):
        # train (and persist) only if requested or if no model exists yet
        if retrain is None:
            retrain = settings.retrain_on_boot or not settings.model_path.exists()
        if retrain:
            self.model_report = train_and_evaluate(n=1500, seed=42)
        else:
            from .ml_model import ModelReport, load_model
            bundle = load_model()
            report = bundle.get("report", {})
            self.model_report = ModelReport(
                best_model_name=bundle.get("model_name", "cached"),
                precision=report.get("precision", 0),
                recall=report.get("recall", 0),
                f1=report.get("f1", 0),
                accuracy=report.get("accuracy", 0),
                confusion=report.get("confusion", {
                    "tn": 0, "fp": 0, "fn": 0, "tp": 0,
                }),
                train_size=bundle.get("train_size", 0),
                test_size=bundle.get("test_size", 0),
                n_false_positives=report.get("confusion", {}).get("fp", 0),
                n_true_positives=report.get("confusion", {}).get("tp", 0),
                fp_cost_total_inr=report.get("confusion", {}).get("fp", 0) * 0.5,
                recovered_gross_inr=report.get("confusion", {}).get("tp", 0) * 1200.0,
                threshold=bundle.get("threshold", 0.5),
                feature_names=bundle.get("feature_names", []),
            )
            self.model_report.net_leverage_inr = (
                self.model_report.recovered_gross_inr - self.model_report.fp_cost_total_inr
            )
        self.engine = WorkflowEngine()

    def run_single(self, event: RevenueEvent):
        return self.engine.run_event(event)

    def run_batch(self, n: int = 200, seed: int = 7) -> dict:
        df, feats = generate_dataset(n=n, seed=seed)
        results = []
        for _, row in df.iterrows():
            event = RevenueEvent(
                transaction_id=row["transaction_id"],
                merchant_id=row["merchant_id"],
                customer_id=row["customer_id"],
                event_type=RevenueEventType(row["event_type"]),
                amount_inr=row["amount_inr"],
                occurred_at=row["occurred_at"],
                last_payment_method=row["payment_method"],
                attempts=int(row["attempts"]),
                metadata={"root_cause": row["root_cause"]},
            )
            run = self.engine.run_event(event)
            results.append(
                {
                    "transaction_id": event.transaction_id,
                    "amount_inr": event.amount_inr,
                    "status": run.status.value,
                    "recovered_inr": run.recovered_amount_inr,
                    "cost_inr": run.total_cost_inr,
                    "root_cause": run.diagnosis.root_cause.value if run.diagnosis else None,
                    "oracle_recoverable": int(row["recoverable"]),
                    "ml_score_high": bool(self.engine.diag_engine.score(event) >= 0.5),
                }
            )
        summary = self.engine.summary()
        return {
            "batch_size": n,
            "summary": summary,
            "rows": results,
        }

    @staticmethod
    def metrics_from_oracle(batch: dict) -> dict:
        """Honest detection metrics against the oracle on the batch."""
        rows = batch["rows"]
        n = len(rows)
        tp = sum(1 for r in rows if r["oracle_recoverable"] == 1 and r["status"] == "recovered")
        # recovered means we acted and got money; treat acted+recovered on oracle-true as TP
        acted = sum(1 for r in rows if r["status"] in ("recovered", "escalated"))
        oracle_pos = sum(1 for r in rows if r["oracle_recoverable"] == 1)
        oracle_neg = sum(1 for r in rows if r["oracle_recoverable"] == 0)
        fp = sum(1 for r in rows if r["oracle_recoverable"] == 0 and r["status"] in ("recovered", "escalated"))
        fn = max(0, oracle_pos - tp)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / oracle_pos if oracle_pos else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        return {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "oracle_positives": oracle_pos,
            "oracle_negatives": oracle_neg,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }
