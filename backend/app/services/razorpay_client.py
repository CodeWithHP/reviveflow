"""Razorpay integration layer.

Runs in two modes:
  * SIMULATED (default, offline) - a deterministic environment that mimics
    Razorpay payment/order responses so the whole demo works with no keys.
  * LIVE test-mode - if REVIVEFLOW_RAZORPAY_KEY_ID/SECRET are set, we call
    the real Razorpay Orders API in test mode.

Every money action returns a typed result and is recorded through the audit
trail upstream. Nothing here is 'offense' capable - it only reads orders /
creates recoveries and payment links within test mode.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field

import requests

from ..core.config import settings


@dataclass
class PaymentAction:
    ok: bool
    action: str
    reference: str
    cost_inr: float
    recovered_inr: float
    reason: str = ""
    raw: dict = field(default_factory=dict)


class RazorpayClient:
    """Thin, safe wrapper around Razorpay payment/order primitives."""

    def __init__(self):
        self.live = bool(settings.razorpay_key_id and settings.razorpay_key_secret)
        self.base = "https://api.razorpay.com/v1"
        self._sim_cache: dict = {}

    # ------------------------------------------------------------------ #
    # simulation - deterministic, seeded by inputs so it's reproducible
    # ------------------------------------------------------------------ #
    def _sim_recover(self, event_id: str, attempt: int) -> PaymentAction:
        # Deterministic pseudo-randomness from the event id + attempt counter
        h = int(hashlib.sha256(f"{event_id}:{attempt}".encode()).hexdigest(), 16)
        roll = (h % 100) / 100.0
        # recovery success chance grows a little with each well-timed attempt
        success = roll < (0.15 + attempt * 0.18)
        cost = 0.15 + (attempt * 0.05)
        recovered = 500.0 if success else 0.0
        return PaymentAction(
            ok=success,
            action="payment_retry",
            reference=f"sim_order_{event_id}",
            cost_inr=round(cost, 2),
            recovered_inr=recovered,
            reason="simulated_psp_success" if success else "simulated_psp_decline",
        )

    def _sim_dunning(self, event_id: str, touch: int) -> PaymentAction:
        # Dunning (customer contact) has a modest independent recovery chance
        h = int(hashlib.sha256(f"dun:{event_id}:{touch}".encode()).hexdigest(), 16)
        roll = (h % 100) / 100.0
        success = roll < (0.08 + touch * 0.12)
        cost = 0.2
        recovered = 400.0 if success else 0.0
        return PaymentAction(
            ok=success,
            action=f"dunning_touch_{touch}",
            reference=f"mail_{event_id}_{touch}",
            cost_inr=round(cost, 2),
            recovered_inr=recovered,
            reason="customer_returned" if success else "no_response",
        )

    # ------------------------------------------------------------------ #
    # public API (shared by simulated & live paths)
    # ------------------------------------------------------------------ #
    def retry_payment(self, order_id: str, attempt: int, amount_inr: float) -> PaymentAction:
        if self.live:
            return self._live_action("retry", order_id, amount_inr)
        return self._sim_recover(order_id, attempt)

    def offer_payment_link(self, order_id: str, amount_inr: float, discount_pct: float) -> PaymentAction:
        if self.live:
            return self._live_action("payment_link", order_id, amount_inr)
        h = int(hashlib.sha256(f"link:{order_id}".encode()).hexdigest(), 16)
        success = (h % 100) / 100.0 < 0.35
        return PaymentAction(
            ok=success,
            action="payment_link",
            reference=f"link_{order_id}",
            cost_inr=round(amount_inr * (discount_pct or 0) * 0.01, 2),
            recovered_inr=amount_inr if success else 0.0,
            reason="customer_paid_link" if success else "link_unclaimed",
        )

    def escalate(self, order_id: str, amount_inr: float) -> PaymentAction:
        """Compliance gate: hand over to a human. Costs a fixed ops unit."""
        if self.live:
            return self._live_action("escalate", order_id, amount_inr)
        h = int(hashlib.sha256(f"esc:{order_id}".encode()).hexdigest(), 16)
        success = (h % 100) / 100.0 < 0.6
        return PaymentAction(
            ok=success,
            action="escalate_human",
            reference=f"ticket_{order_id}",
            cost_inr=2.5,
            recovered_inr=amount_inr if success else 0.0,
            reason="human_resolved" if success else "human_unresolved",
        )

    # ------------------------------------------------------------------ #
    # live follow-through (only reached in test mode with real keys)
    # ------------------------------------------------------------------ #
    def _live_action(self, kind: str, order_id: str, amount_inr: float) -> PaymentAction:
        auth = (settings.razorpay_key_id, settings.razorpay_key_secret)
        try:
            if kind == "payment_link":
                resp = requests.post(
                    f"{self.base}/payment_links",
                    json={"amount": int(amount_inr * 100), "currency": "INR", "description": "ReviveFlow recovery"},
                    auth=auth,
                    timeout=10,
                )
                data = resp.json()
                return PaymentAction(
                    ok=resp.ok,
                    action="payment_link",
                    reference=data.get("id", ""),
                    cost_inr=0.0,
                    recovered_inr=0.0,
                    reason=data.get("error", {}).get("description", "") or "pending_payment",
                    raw=data,
                )
            if kind == "escalate":
                # no pure "escalate" endpoint; we simply surface the queued ticket
                return PaymentAction(
                    ok=True, action="escalate_human", reference=f"ticket_{order_id}",
                    cost_inr=2.5, recovered_inr=0.0, reason="queued_for_human",
                )
        except Exception as exc:  # noqa: BLE001
            return PaymentAction(
                ok=False, action=kind, reference=order_id, cost_inr=0.0,
                recovered_inr=0.0, reason=f"live_error:{exc}",
            )
        return PaymentAction(
            ok=False, action=kind, reference=order_id, cost_inr=0.0,
            recovered_inr=0.0, reason="unsupported_live_action",
        )
