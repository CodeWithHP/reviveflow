"""FastAPI application entrypoint for ReviveFlow."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.config import settings
from ..models.schemas import RevenueEvent
from ..services.orchestrator import ReviveOrchestrator

app = FastAPI(
    title="ReviveFlow API",
    description="Agentic Revenue Recovery Copilot - detect, diagnose, recover.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = ReviveOrchestrator(retrain=settings.retrain_on_boot)


class HealthOut(BaseModel):
    status: str
    app: str
    mode: str
    model_loaded: bool


@app.get("/", response_model=HealthOut)
def health():
    return HealthOut(
        status="ok",
        app=settings.app_name,
        mode="simulated" if not settings.razorpay_key_id else "live_test",
        model_loaded=True,
    )


@app.get("/api/model")
def get_model_report():
    report = orchestrator.model_report
    if report is None:
        raise HTTPException(404, "Model not trained")
    return {
        "model": report.best_model_name,
        "precision": report.precision,
        "recall": report.recall,
        "f1": report.f1,
        "accuracy": report.accuracy,
        "confusion": report.confusion,
        "train_size": report.train_size,
        "test_size": report.test_size,
        "fp_cost_total_inr": report.fp_cost_total_inr,
        "recovered_gross_inr": report.recovered_gross_inr,
        "net_leverage_inr": report.net_leverage_inr,
        "threshold": report.threshold,
    }


@app.post("/api/detect")
def detect_event(event: RevenueEvent):
    """Run a single event through the recovery workflow; return the audited run."""
    run = orchestrator.run_single(event)
    return {
        "run_id": run.id,
        "status": run.status.value,
        "stop_reason": run.stop_reason,
        "recovered_inr": run.recovered_amount_inr,
        "total_cost_inr": run.total_cost_inr,
        "diagnosis": (
            {
                "root_cause": run.diagnosis.root_cause.value,
                "confidence": run.diagnosis.confidence,
                "recoverable": run.diagnosis.recoverable,
                "reason": run.diagnosis.reason,
                "expected_recovery_inr": run.diagnosis.expected_recovery_amount_inr,
            }
            if run.diagnosis
            else None
        ),
        "audit": [a.dict() for a in run.audit],
        "event": event.dict(),
    }


@app.post("/api/batch")
def run_batch(n: int = 200, seed: int = 7):
    result = orchestrator.run_batch(n=n, seed=seed)
    metrics = orchestrator.metrics_from_oracle(result)
    return {"summary": result["summary"], "detection_metrics": metrics}


@app.get("/api/batch-report")
def batch_report(n: int = 200, seed: int = 7):
    """Run a fresh batch and return the full dashboard payload."""
    result = orchestrator.run_batch(n=n, seed=seed)
    metrics = orchestrator.metrics_from_oracle(result)
    status_breakdown = result["summary"]["status_breakdown"]
    return {
        "batch_size": n,
        "summary": result["summary"],
        "detection_metrics": metrics,
        "status_breakdown": status_breakdown,
    }


@app.get("/api/case/{run_id}")
def case(run_id: str):
    run = orchestrator.engine.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {
        "inr": ("\u20b9" + str(run.recovered_amount_inr)),
        "status": run.status.value,
        "audit": [a.dict() for a in run.audit],
    }
