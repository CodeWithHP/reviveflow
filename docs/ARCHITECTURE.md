# ReviveFlow — System Architecture

```
┌───────────────────────────── ReviveFlow ─────────────────────────────┐
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐  │
│  │  DATA LAYER  │   │  ML LAYER    │   │   AGENT CORE             │  │
│  │              │   │              │   │                          │  │
│  │ Synthetic    │──▶│ recovery-    │──▶│ DiagnosisEngine          │  │
│  │ merchant     │   │ risk model   │   │  · root-cause inference  │  │
│  │ events +     │   │ (sklearn)    │   │  · expected-value gating │  │
│  │ oracle label │   │  · train     │   └──────────┬───────────────┘  │
│  │              │   │  · evaluate  │              │                  │
│  └──────────────┘   └──────────────┘   ┌──────────▼───────────────┐  │
│                                        │ WorkflowEngine           │  │
│                                        │  bounded state machine   │  │
│                                        │  · budgets               │  │
│                                        │  · stopping rules        │  │
│                                        │  · escalation gates      │  │
│                                        │  · audit trail           │  │
│                                        └──────────┬───────────────┘  │
│                                                   ▼                  │
│                                        ┌──────────────────────────┐ │
│                                        │ RazorpayClient           │ │
│                                        │ · test-mode orders       │ │
│                                        │ · payment links          │ │
│                                        │ · simulated (offline)    │ │
│                                        └──────────────────────────┘ │
│                                                                      │
│  FastAPI (/api) ──────▶ React dashboard (Vite, /api proxy)          │
└──────────────────────────────────────────────────────────────────────┘
```

## Runtime flow for one revenue event

| # | Stage | Component | What happens | Boundary enforced |
|---|-------|-----------|--------------|-------------------|
| 1 | **Detect** | ML model | score recoverability 0..1 | threshold gate |
| 2 | **Diagnose** | DiagnosisEngine | root cause + confidence | EV > action cost |
| 3 | **Plan** | DiagnosisEngine | ordered interventions | budget cap |
| 4 | **Execute** | WorkflowEngine | run retry/dunning/etc | attempts, touches, stop rules |
| 5 | **Audit** | WorkflowEngine | log every step | — |
| 6 | **Measure** | Orchestrator | recovered − cost, P/R/F1 | honest held-out metrics |

## Key design decisions
- **Real ML, not a lookup** — a trained scikit-learn classifier with honest
  held-out evaluation (precision, recall, F1, false-positive cost).
- **Boundaries in config, enforced in code** — every cap lives in
  `core/config.py` and is *checked* in `workflow_engine.py`, not assumed.
- **Razorpay-first but offline-friendly** — `RazorpayClient` uses simulated
  PSP responses by default (zero keys needed) and switches to real test-mode
  Razorpay Orders/Payment Links when `REVIVEFLOW_RAZORPAY_KEY_*` are set.
- **Defense-only** — no ability to do anything 'offensive'; risk cases only
  escalate to a human gate.
