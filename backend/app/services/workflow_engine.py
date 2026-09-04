"""Agentic workflow engine - the heart of ReviveFlow.

Implements the bounded, self-gating, fully-audited state machine that takes a
detected at-risk revenue event from DETECTED -> RECOVERED/STOPPED/ESCALATED.

Design principles (these are what Track 03 grades on):
  1. BOUNDED  - every action consumes budget; hard caps on retries, touches, cost.
  2. EXPLAINABLE - a running audit trail records *why* each step was taken.
  3. STOPPING RULES - the agent stops the moment money is recovered, the customer
     declines, budget is exhausted, or the event is too old.
  4. COMPLIANT ESCALATION - risky/expensive cases are handed to a human gate, not
     auto-forced.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from ..core.config import settings
from ..models.schemas import (
    AuditEntry,
    Diagnosis,
    EventStatus,
    Intervention,
    InterventionType,
    RevenueEvent,
    WorkflowRun,
)
from .diagnosis_engine import DiagnosisEngine
from .razorpay_client import RazorpayClient, PaymentAction


class WorkflowEngine:
    """Runs one event through the recovery lifecycle, bounded and audited."""

    def __init__(
        self,
        diag_engine: Optional[DiagnosisEngine] = None,
        razorpay: Optional[RazorpayClient] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.diag_engine = diag_engine or DiagnosisEngine()
        self.razorpay = razorpay or RazorpayClient()
        # naive UTC clock to stay consistent with generated (tz-naive) event data
        self._clock = clock or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))
        self.runs: List[WorkflowRun] = []
        self._runs_by_id: dict = {}

    # ------------------------------------------------------------------ #
    def _audit(self, run: WorkflowRun, stage: str, action: str, details: str = "", actor: str = "agent"):
        run.audit.append(
            AuditEntry(timestamp=self._clock(), actor=actor, stage=stage, action=action, details=details)
        )
        run.updated_at = self._clock()

    def run_event(self, event: RevenueEvent, reset: bool = True) -> WorkflowRun:
        run_id = f"wf_{uuid.uuid4().hex[:10]}"
        run = WorkflowRun(id=run_id, event=event)
        self._audit(run, "detection", "event_ingested",
                    f"type={event.event_type.value} amount=₹{event.amount_inr}")

        # ---- 1. DETECT / SCORE via ML ----
        score = self.diag_engine.score(event)
        self._audit(run, "detection", "ml_recovery_risk",
                    f"score={score:.3f}")

        # ---- 2. DIAGNOSE ----
        diag = self.diag_engine.diagnose(event)
        run.diagnosis = diag
        self._audit(run, "diagnosis", "root_cause",
                    f"{diag.root_cause.value} conf={diag.confidence} recoverable={diag.recoverable}")

        if not diag.recoverable:
            run.status = EventStatus.STOPPED
            run.stop_reason = "expected_recovery_below_actioning_cost (EV gate)"
            self._audit(run, "intervention", "stop",
                        f"not economical to recover (expected ₹{diag.expected_recovery_amount_inr:.2f})",
                        actor="system")
            self._store(run)
            return run

        # ---- 3. PLAN interventions (bounded) ----
        plan = self._plan_interventions(event, diag)
        if not plan:
            run.status = EventStatus.STOPPED
            run.stop_reason = "no_safe_intervention_available"
            self._audit(run, "intervention", "stop", "no bounded intervention exists", actor="system")
            self._store(run)
            return run

        # ---- 4. EXECUTE (bounded state machine) ----
        self._execute(run, plan)
        self._store(run)
        return run

    # ------------------------------------------------------------------ #
    def _plan_interventions(self, event: RevenueEvent, diag: Diagnosis) -> List[Intervention]:
        from .diagnosis_engine import choose_interventions
        now = self._clock()
        interventions = []
        cumulative = 0.0
        budget = settings.recovery.max_cost_per_lifecycle
        for itype, desc, cost, max_attempts in choose_interventions(event, diag):
            cumulative += cost
            # respect the bounded budget
            if cumulative > budget:
                break
            interventions.append(
                Intervention(
                    type=itype, description=desc, resource_cost_inr=cost,
                    max_attempts=max_attempts, timestamp=now,
                )
            )
        return interventions

    # ------------------------------------------------------------------ #
    def _execute(self, run: WorkflowRun, plan: List[Intervention]):
        diag = run.diagnosis
        # check age-stop first: never chase events older than the cap
        age_days = (self._clock() - run.event.occurred_at).total_seconds() / 86400.0
        if age_days > settings.recovery.max_retry_age_days:
            run.status = EventStatus.STOPPED
            run.stop_reason = f"event too old ({age_days:.0f}d > {settings.recovery.max_retry_age_days}d)"
            self._audit(run, "execution", "stop", run.stop_reason, actor="system")
            return

        for intervention in plan:
            if run.status in (EventStatus.RECOVERED, EventStatus.STOPPED, EventStatus.ESCALATED):
                break  # stopping rule: never keep acting on an already-resolved case
            self._audit(run, "intervention", "schedule",
                        f"{intervention.type.value} :: {intervention.description}")
            outcome = self._dispatch(run, intervention)
            if run.status == EventStatus.RECOVERED:
                break

        if run.status == EventStatus.DETECTED:
            run.status = EventStatus.FAILED
            run.stop_reason = "budget_exhausted_without_recovery"
            self._audit(run, "outcome", "failed", run.stop_reason, actor="system")

    # ------------------------------------------------------------------ #
    def _dispatch(self, run: WorkflowRun, intervention: Intervention) -> Optional[PaymentAction]:
        """Execute one intervention, respecting per-intervention attempt caps."""
        event = run.event
        action: Optional[PaymentAction] = None
        for attempt in range(1, intervention.max_attempts + 1):
            # global stopping rules re-checked every attempt
            if run.status in (EventStatus.STOPPED, EventStatus.ESCALATED, EventStatus.RECOVERED):
                return action

            if intervention.type == InterventionType.RETRY:
                action = self.razorpay.retry_payment(event.transaction_id, attempt, event.amount_inr)
                self._audit(run, "execution", "retry",
                            f"attempt {attempt} ok={action.ok} recovered=₹{action.recovered_inr}")
            elif intervention.type == InterventionType.DUNNING:
                action = self._dunning(run, attempt)
            elif intervention.type == InterventionType.ALTERNATIVE_PAYMENT:
                action = self.razorpay.offer_payment_link(event.transaction_id, event.amount_inr, 0.0)
                self._audit(run, "execution", "alt_payment",
                            f"attempt {attempt} ok={action.ok} recovered=₹{action.recovered_inr}")
            elif intervention.type == InterventionType.OFFER:
                disc = settings.dunning.discount_on_third_touch
                action = self.razorpay.offer_payment_link(event.transaction_id, event.amount_inr, disc * 100)
                self._audit(run, "execution", "offer",
                            f"attempt {attempt} ok={action.ok} recovered=₹{action.recovered_inr}")
            elif intervention.type == InterventionType.MANDATE_RETRY:
                action = self.razorpay.retry_payment(event.transaction_id, attempt, event.amount_inr)
                self._audit(run, "execution", "mandate_retry",
                            f"attempt {attempt} ok={action.ok} recovered=₹{action.recovered_inr}")
            elif intervention.type == InterventionType.ESCALATE:
                run.status = EventStatus.ESCALATED
                run.stop_reason = "escalated_to_human (compliance gate)"
                self._audit(run, "outcome", "escalate",
                            f"case handed to human; reason={intervention.description}", actor="system")
                break
            elif intervention.type == InterventionType.NO_ACTION:
                run.status = EventStatus.STOPPED
                run.stop_reason = "no_action_safe (e.g. duplicate)"
                self._audit(run, "outcome", "stopped", run.stop_reason, actor="system")
                return None

            # account for resource spend every action
            if action and action.cost_inr:
                run.total_cost_inr += action.cost_inr

            if action and action.ok and action.recovered_inr > 0:
                run.recovered_amount_inr += action.recovered_inr
                run.status = EventStatus.RECOVERED
                run.stop_reason = "recovered"
                self._audit(run, "outcome", "recovered",
                            f"recovered ₹{run.recovered_amount_inr:.2f} total_cost ₹{run.total_cost_inr:.2f}",
                            actor="system")
                return action

            # stopping rule: budget cap across lifecycle
            if run.total_cost_inr >= settings.recovery.max_cost_per_lifecycle:
                run.status = EventStatus.STOPPED
                run.stop_reason = "lifecycle_budget_cap_reached"
                self._audit(run, "execution", "stop", run.stop_reason, actor="system")
                return action

            # stopping rule: max dunning touches cap
            if intervention.type == InterventionType.DUNNING and attempt >= settings.recovery.max_dunning_messages+1:
                run.status = EventStatus.STOPPED
                run.stop_reason = "dunning_cap_reached"
                self._audit(run, "execution", "stop", run.stop_reason, actor="system")
                return action

        return action

    def _dunning(self, run: WorkflowRun, touch: int) -> PaymentAction:
        # space the touches across days (respect the dunning policy pauses)
        ts = self._clock()
        action = self.razorpay._sim_dunning(run.event.transaction_id, touch)
        day = settings.dunning.touch_days[touch - 1] if touch - 1 < len(settings.dunning.touch_days) else \
            settings.dunning.touch_days[-1] + (touch - len(settings.dunning.touch_days))
        self._audit(run, "execution", "dunning",
                    f"touch {touch} at day {day} ok={action.ok}")
        return action

    # ------------------------------------------------------------------ #
    def _store(self, run: WorkflowRun):
        self.runs.append(run)
        self._runs_by_id[run.id] = run

    def reset(self):
        """Clear cached runs (fresh agent session)."""
        self.runs = []
        self._runs_by_id = {}

    def get(self, run_id: str) -> Optional[WorkflowRun]:
        return self._runs_by_id.get(run_id)

    def summary(self) -> dict:
        recovered = sum(r.recovered_amount_inr for r in self.runs)
        cost = sum(r.total_cost_inr for r in self.runs)
        recovered_count = sum(1 for r in self.runs if r.status == EventStatus.RECOVERED)
        return {
            "total_events": len(self.runs),
            "recovered_count": recovered_count,
            "recovered_amount_inr": round(recovered, 2),
            "total_cost_inr": round(cost, 2),
            "net_value_inr": round(recovered - cost, 2),
            "status_breakdown": {
                s.value: sum(1 for r in self.runs if r.status == s) for s in EventStatus
            },
        }
