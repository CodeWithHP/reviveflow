"""Domain models for ReviveFlow.

These are the typed contracts that flow through the whole system:
detection -> diagnosis -> intervention -> execution -> audit.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RevenueEventType(str, Enum):
    PAYMENT_FAILURE = "payment_failure"
    CHECKOUT_ABANDON = "checkout_abandon"
    SUBSCRIPTION_FAILURE = "subscription_failure"
    OVERDUE_INVOICE = "overdue_invoice"


class RootCause(str, Enum):
    INSUFFICIENT_FUNDS = "insufficient_funds"
    BANK_DECLINE = "bank_decline"
    NETWORK_TIMEOUT = "network_timeout"
    CARD_EXPIRED = "card_expired"
    FRAUD_FLAG = "fraud_flag"
    INVALID_DETAILS = "invalid_details"
    DUPLICATE = "duplicate"
    SUBSCRIPTION_SUSPENDED = "subscription_suspended"
    FOLLOW_UP_NEEDED = "follow_up_needed"


class InterventionType(str, Enum):
    RETRY = "retry"
    ALTERNATIVE_PAYMENT = "alternative_payment"
    DUNNING = "dunning"
    OFFER = "offer"
    PRORATE_INVOICE = "prorate_invoice"
    MANDATE_RETRY = "mandate_retry"
    ESCALATE = "escalate"
    NO_ACTION = "no_action"


class EventStatus(str, Enum):
    DETECTED = "detected"
    DIAGNOSED = "diagnosed"
    INTERVENTION_SCHEDULED = "intervention_scheduled"
    RECOVERED = "recovered"
    FAILED = "failed"
    STOPPED = "stopped"
    ESCALATED = "escalated"
    CLOSED = "closed"


class RevenueEvent(BaseModel):
    """A discrete piece of revenue that is at risk."""
    transaction_id: str
    merchant_id: str
    customer_id: str
    event_type: RevenueEventType
    amount_inr: float
    currency: str = "INR"
    occurred_at: datetime
    last_payment_method: Optional[str] = None
    attempts: int = 0
    metadata: dict = Field(default_factory=dict)


class Diagnosis(BaseModel):
    root_cause: RootCause
    confidence: float
    reason: str
    recoverable: bool
    expected_recovery_amount_inr: float


class Intervention(BaseModel):
    type: InterventionType
    description: str
    resource_cost_inr: float
    max_attempts: int
    timestamp: datetime
    params: dict = Field(default_factory=dict)


class AuditEntry(BaseModel):
    timestamp: datetime
    actor: str          # "agent" | "system" | "human"
    stage: str          # detection | diagnosis | intervention | execution | outcome
    action: str
    details: str = ""


class WorkflowRun(BaseModel):
    id: str
    event: RevenueEvent
    diagnosis: Optional[Diagnosis] = None
    interventions: List[Intervention] = Field(default_factory=list)
    status: EventStatus = EventStatus.DETECTED
    audit: List[AuditEntry] = Field(default_factory=list)
    recovered_amount_inr: float = 0.0
    total_cost_inr: float = 0.0
    stop_reason: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
