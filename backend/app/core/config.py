"""Application configuration.

Centralises every tunable so the whole system is governed by a single,
auditable config blob (rather than magic numbers scattered across the code).
This is deliberate: a revenue-recovery agent must be *bounded* and *explainable*,
so all stopping rules, budgets and escalation thresholds live here.
"""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
MODELS_DIR = DATA_DIR / "models"


class RecoveryBudget(BaseSettings):
    """Bounded resource spend. Every executed action consumes budget units."""
    max_cost_per_lifecycle: float = 0.75      # max INR spend recovering one txn
    max_dunning_messages: int = 3             # hard cap on customer touches
    max_retry_attempts: int = 4               # hard cap on payment retries
    max_retry_age_days: int = 30              # do not chase transactions older than this
    max_exposure_per_merchant: float = 5000.0  # aggregate cap before human escalation


class DunningPolicy(BaseSettings):
    """When and how aggressively to contact the customer."""
    touch_days: List[int] = [1, 3, 7]          # n days after failure to send msg n
    pause_after_failure_days: int = 2          # back-off window between touches
    discount_on_third_touch: float = 0.10      # 10% nudge if strong willingness signal


class StopRule(BaseSettings):
    """Compliant stopping rules - when the agent MUST stop and/or escalate."""
    stop_after_recovery: bool = True           # never keep chasing a recovered txn
    stop_after_refund_or_cancel: bool = True   # respect the customer's explicit no
    escrow_escalation_threshold_rs: float = 2000.0  # escalate spends above this value
    max_open_negative_feedback: int = 2        # if customer says "no" N times, stop


class Settings(BaseSettings):
    """Top-level runtime settings."""
    app_name: str = "ReviveFlow"
    environment: str = "development"

    # Razorpay test-mode credentials (leave blank to run in offline/simulated mode)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ML
    model_path: Path = MODELS_DIR / "recovery_risk_model.joblib"
    retrain_on_boot: bool = False

    # Budget / policy objects
    recovery: RecoveryBudget = RecoveryBudget()
    dunning: DunningPolicy = DunningPolicy()
    stops: StopRule = StopRule()

    model_config = SettingsConfigDict(env_prefix="REVIVEFLOW_", extra="ignore")


settings = Settings()

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
