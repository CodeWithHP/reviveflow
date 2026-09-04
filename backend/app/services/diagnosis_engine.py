"""Diagnosis engine.

Given a detected at-risk event + the ML recovery-risk score, produce a typed
:class:`Diagnosis` with a root cause, confidence, whether it's worth recovering,
and the expected recovery amount. In production the root cause would come from
Razorpay's error code + payment_status; here we expose a pluggable function that
maps "raw signal" -> RootCause. We back it with the ML score for confidence and
an expected-value gating: if expected recovery < actioning cost, we say no-op.
"""
from datetime import datetime, timezone

import numpy as np

from ..models.schemas import (
    Diagnosis,
    InterventionType,
    RevenueEvent,
    RevenueEventType,
    RootCause,
)
from .ml_model import load_model, predict_proba
from .data_generator import extract_features
import pandas as pd


class DiagnosisEngine:
    """Backed by the trained ML model for the recoverability score."""

    def __init__(self):
        self.model_bundle = load_model()

    def score(self, event: RevenueEvent) -> float:
        """ML probability the revenue is recoverable (0..1)."""
        occurred = event.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        days_since = max(0.0, (datetime.now(timezone.utc) - occurred).total_seconds() / 86400.0)
        row = {
            "amount_inr": event.amount_inr,
            "days_since": days_since,
            "event_type": event.event_type.value,
            "attempts": event.attempts,
            "payment_method": event.last_payment_method or "upi",
            "root_cause": event.metadata.get("root_cause", "unknown"),
        }
        df = pd.DataFrame([row])
        try:
            feats = extract_features(df)
        except Exception:
            # fall back to a neutral feature set if root_cause is unknown
            feats = extract_features(df.assign(root_cause="follow_up_needed"))
        feature_vector = feats.iloc[0].tolist()
        # align to model feature order / cardinality
        expected = self.model_bundle["feature_names"]
        padded = []
        for name in expected:
            if name in df.columns or name in feats.columns:
                padded.append(float(feats.iloc[0][name]) if name in feats.columns else 0.0)
            else:
                padded.append(float(df.iloc[0][name]) if name in df.columns else 0.0)
        # fallback: pad or trim to match model width
        while len(padded) < len(expected):
            padded.append(0.0)
        padded = padded[: len(expected)]
        return predict_proba(padded, self.model_bundle)

    def diagnose(self, event: RevenueEvent) -> Diagnosis:
        score = self.score(event)
        # root cause determination (pluggable; in production from Razorpay error code)
        cause = self._infer_root_cause(event, score)
        # expected-value gating: is recovery worth more than it costs to attempt?
        expected_recovery = event.amount_inr * score
        # cost to attempt ≈ dunning/retry resource spend (bounded by config)
        actioning_cost = self._actioning_cost(event, cause)
        recoverable = expected_recovery > actioning_cost and score >= 0.35
        confidence = float(np.clip(0.5 + abs(score - 0.5), 0.5, 0.97))
        return Diagnosis(
            root_cause=cause,
            confidence=round(confidence, 3),
            reason=self._reason(cause, score, expected_recovery),
            recoverable=recoverable,
            expected_recovery_amount_inr=round(expected_recovery, 2),
        )

    def _infer_root_cause(self, event: RevenueEvent, score: float) -> RootCause:
        if event.event_type == RevenueEventType.OVERDUE_INVOICE.value:
            return RootCause.FOLLOW_UP_NEEDED
        if event.event_type == RevenueEventType.SUBSCRIPTION_FAILURE.value:
            return RootCause.SUBSCRIPTION_SUSPENDED
        raw = event.metadata.get("root_cause")
        if raw and raw in [c.value for c in RootCause]:
            return RootCause(raw)
        # default by payment method / attempt pattern when no raw signal
        if event.attempts >= 3:
            return RootCause.BANK_DECLINE
        if event.last_payment_method == "card":
            return RootCause.CARD_EXPIRED
        return RootCause.NETWORK_TIMEOUT  # most common, recoverable default

    def _actioning_cost(self, event: RevenueEvent, cause: RootCause) -> float:
        # higher cost for channels that need human / expensive touches
        base = 0.5
        if cause == RootCause.FOLLOW_UP_NEEDED:
            return 1.2
        if cause in (RootCause.FRAUD_FLAG, RootCause.DUPLICATE):
            return 2.5
        return base

    def _reason(self, cause: RootCause, score: float, expected: float) -> str:
        return (
            f"Root cause '{cause.value}'. ML recovery-risk score {score:.0%}; "
            f"expected recoverable value ~₹{expected:.2f}."
        )


def choose_interventions(event: RevenueEvent, diag: Diagnosis):
    """Map a diagnosis to an ordered, bounded set of interventions to try."""
    cause = diag.root_cause
    plans = {
        RootCause.INSUFFICIENT_FUNDS: [
            (InterventionType.DUNNING, "Funds-then-retry: notify & auto retry in 48h", 0.4, 2),
            (InterventionType.RETRY, "Scheduled auto retry after 48h", 0.2, 2),
        ],
        RootCause.NETWORK_TIMEOUT: [
            (InterventionType.RETRY, "Immediate retry (transient failure)", 0.15, 2),
            (InterventionType.ALTERNATIVE_PAYMENT, "Offer alternate UPI/card rail", 0.3, 1),
        ],
        RootCause.CARD_EXPIRED: [
            (InterventionType.ALTERNATIVE_PAYMENT, "Request updated card / UPI", 0.4, 2),
            (InterventionType.DUNNING, "Card expiry dunning email", 0.3, 1),
        ],
        RootCause.BANK_DECLINE: [
            (InterventionType.DUNNING, "Decline-notice + retry in 3d", 0.5, 2),
            (InterventionType.ALTERNATIVE_PAYMENT, "Suggest alternate method", 0.3, 1),
        ],
        RootCause.FRAUD_FLAG: [
            (InterventionType.ESCALATE, "Human verification (compliance gate)", 2.5, 1),
        ],
        RootCause.SUBSCRIPTION_SUSPENDED: [
            (InterventionType.MANDATE_RETRY, "Re-run eMandate retry sequencer", 0.4, 3),
            (InterventionType.DUNNING, "Subscription-hold dunning", 0.3, 2),
        ],
        RootCause.FOLLOW_UP_NEEDED: [
            (InterventionType.DUNNING, "Overdue-invoice follow-up (t1)", 0.6, 3),
            (InterventionType.OFFER, "Early-pay discount incentive", 0.8, 1),
        ],
        RootCause.INVALID_DETAILS: [
            (InterventionType.ALTERNATIVE_PAYMENT, "Collect correct details", 0.3, 2),
            (InterventionType.DUNNING, "Details-correction nudge", 0.3, 1),
        ],
        RootCause.DUPLICATE: [
            (InterventionType.NO_ACTION, "Duplicate - do not action (stop rule)", 0.0, 0),
        ],
    }
    return plans.get(cause, [(InterventionType.NO_ACTION, "No intervention", 0.0, 0)])
