"""Synthetic merchant revenue data generator.

Generates realistic Razorpay-style payment/checkout/subscription/invoice events
with an *oracle* ground-truth label of whether the revenue is recoverable.

Having an oracle matters: it lets ReviveFlow train a *real* ML detector and then
report honest precision / recall / false-positive-cost on a held-out test set -
exactly the bar Track 03 sets ("Honest metrics"). In production the oracle would
be replaced by observed recovery outcomes, but for the demo it gives us a correct
label to measure the detector against.

The generation is deterministic (seeded) so results are reproducible.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

import numpy as np
import pandas as pd

from ..models.schemas import RevenueEvent, RevenueEventType

MERCHANTS = [
    ("M1001", "UrbanCart", "fashion"),
    ("M1002", "FitFuel", "health"),
    ("M1003", "TechieZone", "electronics"),
    ("M1004", "GreenGrocery", "grocery"),
    ("M1005", "BookWorm", "books"),
    ("M1006", "TravelPe", "travel"),
    ("M1007", "CraftVault", "handicrafts"),
    ("M1008", "CloudSprint", "saas"),
]

PAYMENT_METHODS = ["upi", "card", "netbanking", "wallet", "emandate", "nach"]

# Per root-cause: (how likely we observe this cause, how recoverable it is)
# recoverability is the oracle P(recovered | cause, intervention applied)
ROOT_CAUSES = {
    "insufficient_funds":     {"prob": 0.22, "recoverable": 0.62},
    "bank_decline":           {"prob": 0.18, "recoverable": 0.30},
    "network_timeout":        {"prob": 0.16, "recoverable": 0.85},
    "card_expired":           {"prob": 0.08, "recoverable": 0.70},
    "fraud_flag":             {"prob": 0.07, "recoverable": 0.15},
    "invalid_details":        {"prob": 0.06, "recoverable": 0.45},
    "duplicate":              {"prob": 0.04, "recoverable": 0.05},
    "subscription_suspended": {"prob": 0.09, "recoverable": 0.55},
    "follow_up_needed":       {"prob": 0.10, "recoverable": 0.75},
}
CAUSES = list(ROOT_CAUSES.keys())

# feature engineering helpers (kept here so training & inference share the logic)


def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the numeric feature matrix used by the training & inference paths.

    The engineered features mirror the (domain-honest) physics of recoverability:
      - recency matters (fresher = more recoverable)
      - repeated attempts degrade recoverability
      - the event type & payment rail shape the likely cause and best action
      - value of the amount interacts with the chosen intervention (big-ticket
        invoices behave differently from tiny checkouts)
    """
    out = pd.DataFrame(index=df.index)
    out["amount_inr"] = df["amount_inr"]
    out["days_since"] = df["days_since"]
    out["is_checkout_abandon"] = (df["event_type"] == RevenueEventType.CHECKOUT_ABANDON.value).astype(int)
    out["is_subscription_failure"] = (df["event_type"] == RevenueEventType.SUBSCRIPTION_FAILURE.value).astype(int)
    out["is_overdue_invoice"] = (df["event_type"] == RevenueEventType.OVERDUE_INVOICE.value).astype(int)
    out["is_payment_failure"] = (df["event_type"] == RevenueEventType.PAYMENT_FAILURE.value).astype(int)
    out["attempts"] = df["attempts"]
    out["is_upi"] = (df["payment_method"] == "upi").astype(int)
    out["is_card"] = (df["payment_method"] == "card").astype(int)
    out["is_netbanking"] = (df["payment_method"] == "netbanking").astype(int)
    out["is_emandate"] = (df["payment_method"] == "emandate").astype(int)
    out["is_nach"] = (df["payment_method"] == "nach").astype(int)

    # ----- interaction / non-linear features the trees can exploit -----
    out["recency_score"] = 1.0 / (1.0 + df["days_since"])          # fresher -> higher
    out["attempts_penalty"] = 1.0 / (1.0 + df["attempts"])
    out["log_amount"] = np.log1p(df["amount_inr"])
    out["value_tier"] = pd.cut(
        df["amount_inr"], bins=[0, 500, 2000, 10000, 1e12], labels=[0, 1, 2, 3]
    ).astype(int)
    # willingness signal: abandon + few attempts + fresh is a strong recovery cue
    out["strong_willingness"] = (
        (df["event_type"] == RevenueEventType.CHECKOUT_ABANDON.value)
        & (df["attempts"] == 0)
        & (df["days_since"] < 5)
    ).astype(int)
    # 1-hot for root cause
    for c in CAUSES:
        out[f"cause_{c}"] = (df["root_cause"] == c).astype(int)
    return out


def generate_dataset(
    n: int = 1200,
    seed: int = 42,
    since_days: int = 35,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate `n` events with oracle labels. Returns (events_df, features_df)."""
    rng = np.random.default_rng(seed)
    now = datetime.utcnow()

    merchants = [m[0] for m in MERCHANTS]
    rows = []
    causes = rng.choice(CAUSES, size=n, p=[ROOT_CAUSES[c]["prob"] for c in CAUSES])

    for i in range(n):
        merchant_id = merchants[rng.integers(len(merchants))]
        cause = causes[i]
        event_type = rng.choice(
            [e.value for e in RevenueEventType],
            p=[0.35, 0.25, 0.20, 0.20],
        )

        # amount distribution differs slightly by type
        if event_type == RevenueEventType.OVERDUE_INVOICE.value:
            amount = float(round(rng.lognormal(mean=7.5, sigma=1.1), 2))   # larger B2B
        elif event_type == RevenueEventType.SUBSCRIPTION_FAILURE.value:
            amount = float(round(rng.uniform(199, 4999), 2))
        elif event_type == RevenueEventType.CHECKOUT_ABANDON.value:
            amount = float(round(rng.lognormal(mean=5.5, sigma=0.9), 2))
        else:
            amount = float(round(rng.lognormal(mean=5.8, sigma=1.0), 2))

        method_weights = {
            "upi": 0.35, "card": 0.30, "netbanking": 0.12,
            "wallet": 0.08, "emandate": 0.08, "nach": 0.07,
        }
        method = rng.choice(list(method_weights.keys()), p=list(method_weights.values()))
        attempts = int(rng.integers(0, 4))
        days_ago = float(rng.uniform(0, since_days))
        occurred_at = now - timedelta(days=days_ago)

        # oracle label - deterministic latent recoverability from domain physics
        # (this is what the ML model must learn), plus modest label noise.
        recoverable_prob = ROOT_CAUSES[cause]["recoverable"]
        # recency: fresher events are far more recoverable (the #1 real signal)
        recency_boost = np.clip(2.0 - (days_ago / 10.0), 0.15, 2.0)
        # attempts: every failed retry hardens resistance
        attempts_penalty = np.clip(1.0 - attempts * 0.18, 0.35, 1.0)
        # payment rail geometry shapes actionability
        method_boost = {"upi": 1.15, "emandate": 1.05, "nach": 1.0,
                        "card": 0.95, "netbanking": 0.9, "wallet": 0.85}[method]
        # event type nuance
        if event_type == RevenueEventType.CHECKOUT_ABANDON.value:
            event_boost = 1.15 if attempts == 0 else 0.95
        elif event_type == RevenueEventType.SUBSCRIPTION_FAILURE.value:
            event_boost = 1.05
        elif event_type == RevenueEventType.OVERDUE_INVOICE.value:
            event_boost = 0.85 if days_ago > 15 else 1.10   # older invoices harden
        else:
            event_boost = 1.0
        latent = recoverable_prob * recency_boost * attempts_penalty * method_boost * event_boost
        oracle_p = np.clip(latent, 0.02, 0.97)
        # add label noise so it's not trivially memorisable
        recovered = bool(rng.random() < oracle_p)

        rows.append({
            "transaction_id": f"txn_{merchant_id}_{i:05d}",
            "merchant_id": merchant_id,
            "customer_id": f"C{i:06d}",
            "event_type": event_type,
            "amount_inr": amount,
            "occurred_at": occurred_at,
            "payment_method": method,
            "attempts": attempts,
            "root_cause": cause,
            "recoverable": int(recovered),
            "days_since": days_ago,
        })

    df = pd.DataFrame(rows)
    feats = extract_features(df)
    return df, feats


if __name__ == "__main__":
    d, f = generate_dataset(500)
    print(d[["transaction_id", "event_type", "amount_inr", "root_cause", "recoverable"]].head(10))
    print("class balance recoverable:", d["recoverable"].mean().round(3))
