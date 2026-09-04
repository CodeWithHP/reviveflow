"""ReviveFlow interactive demo - produces the pitch-video narrative.

Run:  python -m app.services.demo
Run:  python run_demo.py   (from backend/)

Shows, end to end:
  1. Model quality (on a held-out set)
  2. A live single-case walkthrough with the full audit trail
  3. Batch economics (money recovered vs ops cost)
  4. Honest detection metrics vs an oracle
"""
from datetime import datetime, timedelta

from app.models.schemas import RevenueEvent, RevenueEventType, EventStatus
from app.services.ml_model import train_and_evaluate
from app.services.orchestrator import ReviveOrchestrator

SEP = "=" * 74
INR = "\u20b9"


def p(text=""):
    print(text)


def main():
    p(SEP)
    p("  ReviveFlow - Agentic Revenue Recovery Copilot (Razorpay AI Buildathon, Track 03)")
    p(SEP)

    # ---------- 1. MODEL ----------
    p("\n[1] ML RECOVERY-RISK DETECTOR (trained, evaluated on a HELD-OUT set)")
    r = train_and_evaluate(1500, seed=42)
    p(f"    Best model             : {r.best_model_name}")
    p(f"    Precision / Recall     : {r.precision:.1%} / {r.recall:.1%}")
    p(f"    F1 / Accuracy          : {r.f1:.1%} / {r.accuracy:.1%}")
    p(f"    Confusion (tn/fp/fn/tp): {r.confusion}")
    p(f"    FP actioning cost      : {INR}{r.fp_cost_total_inr:.2f}   (honest cost of acting on 0s)")
    p(f"    Gross recovery value   : {INR}{r.recovered_gross_inr:,.2f}")
    p(f"    NET leverage           : {INR}{r.net_leverage_inr:,.2f}")

    # ---------- 2. SINGLE CASE ----------
    p("\n[2] LIVE SINGLE CASE - the agent in action (bounded + audited)")
    orch = ReviveOrchestrator(retrain=False)
    event = RevenueEvent(
        transaction_id="txn_LIVE_8421",
        merchant_id="M1001",
        customer_id="C800813",
        event_type=RevenueEventType.CHECKOUT_ABANDON,
        amount_inr=2499.0,
        occurred_at=datetime.utcnow() - timedelta(days=2),
        last_payment_method="upi",
        attempts=0,
        metadata={"root_cause": "insufficient_funds"},
    )
    run = orch.run_single(event)
    p(f"    Event  : {event.transaction_id} | {event.event_type.value} | {INR}{event.amount_inr:,.2f}")
    if run.diagnosis:
        d = run.diagnosis
        p(f"    Diag   : root_cause={d.root_cause.value}  conf={d.confidence:.0%}")
        p(f"    Reason : {d.reason}")
    p(f"    Status : {run.status.value}")
    if run.stop_reason:
        p(f"    Stop   : {run.stop_reason}")
    p(f"    Recovered {INR}{run.recovered_amount_inr:,.2f} | cost {INR}{run.total_cost_inr:.2f}")
    p("    --- Audit trail ---")
    for a in run.audit:
        t = a.timestamp.strftime("%H:%M:%S")
        p(f"    [{t}] {a.stage:<12} {a.action:<18} {a.details}")

    # ---------- 3. BATCH ----------
    p("\n[3] BATCH RECOVERY (Track bar: measured money recovered across a batch)")
    orch.engine.reset()
    batch = orch.run_batch(n=500, seed=7)
    s = batch["summary"]
    m = orch.metrics_from_oracle(batch)
    p(f"    Events scanned      : {s['total_events']}")
    p(f"    Recovered (cases)   : {s['recovered_count']}")
    p(f"    Money recovered     : {INR}{s['recovered_amount_inr']:,.2f}")
    p(f"    Ops cost (bounded)  : {INR}{s['total_cost_inr']:,.2f}")
    p(f"    Net value created   : {INR}{s['net_value_inr']:,.2f}")
    p(f"    Status breakdown    : {s['status_breakdown']}")
    p("    Detection vs oracle (honest):")
    p(f"      TP={m['true_positives']} FP={m['false_positives']} FN={m['false_negatives']}")
    p(f"      Precision={m['precision']:.1%} Recall={m['recall']:.1%} F1={m['f1']:.1%}")

    p("\n[4] WHAT MAKES IT A *BOUNDED* AGENT (not a wrapper)")
    p("     - Every action spends tracked resource budget (config caps).")
    p("     - Hard stopping rules: stop on recovery, on customer 'no', on budget cap,")
    p("       on age cap, on max dunning touches.")
    p("     - Risk/expensive / fraud cases are ESCALATED to a human gate, never auto-forced.")
    p("     - Full audit trail on every case; nothing acts without a logged reason.")
    p(SEP)
    p("  Detect -> Diagnose -> Plan -> Execute(bounded) -> Audit -> Measure")
    p(SEP)


if __name__ == "__main__":
    main()
