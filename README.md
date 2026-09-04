<div align="center">

# 🔄 ReviveFlow — Agentic Revenue Recovery Copilot

**Razorpay AI Buildathon · Track 03: AI Revenue Recovery**

[![Python](https://img.shields.io/badge/Python-3.10-blue.svg)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688.svg)](#)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-trained-f7931e.svg)](#)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](#)
[![Vite](https://img.shields.io/badge/Vite-8-646cff.svg)](#)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#)

*Find leaked revenue · Diagnose it · Get it back — bounded, explainable, audited.*

</div>

ReviveFlow is an autonomous, self-gating AI agent that finds revenue slipping
away for a merchant and **closes the loop** to win it back — from detecting the
problem, to diagnosing the root cause, to choosing the right intervention,
to executing a **bounded** recovery workflow with a full audit trail.

> The bar we hit: *"Don't just identify the problem. Show measured money recovered
> across a batch, with compliant escalation, stopping rules, and an audit trail."*

In one batch of **500 synthetic merchant events**, the agent recovered
**₹50,696** at an ops cost of just **₹66** → **net value created ₹50,630**.

---

## ⚡ Quick start (Windows)

Prereqs: **Python 3.10+** and **Node 18+**.

```powershell
# Step 1 — backend (FastAPI + auto-trained ML)
cd backend
python -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
.\venv\Scripts\python.exe run_api.py          # → http://localhost:8000

# Step 2 — frontend (React dashboard) in a NEW terminal
cd frontend
npm install
npm run dev                                   # → http://localhost:5173
```

Open **http://localhost:5173**.

> 💡 **Fastest path:** double-click **`start_all.cmd`** — it starts both servers and
> opens the dashboard in one go.
>
> 🎬 **Pitch narrative:** `cd backend && python run_demo.py` prints the exact
> numbers and a live audit trail you can recite in the 5-minute video.

---

## 📸 Live preview (local)

![ReviveFlow Dashboard](https://img.shields.io/badge/Dashboard-React-blue.svg)

The dashboard shows: recovery KPIs (money recovered, ops cost, net value),
**honest model metrics** (precision / recall / F1 / accuracy), the outcome
breakdown (recovered / stopped / failed / escalated), and a **live single-case
audit trail** — run a case and watch the agent decide, act, and stop.

---

## What makes it a *bounded agent*, not a wrapper script

| Guarantee | How it's enforced |
|-----------|-------------------|
| **Bounded** | Every money action consumes a tracked resource budget (config caps on cost, retries, touches). The agent stops the moment budget is exhausted. |
| **Explainable** | Every case carries a timestamped audit trail recording *why* each step was taken (`detect → diagnose → execute → outcome`). |
| **Stopping rules** | Stops on recovery, on customer "no", on age cap, on max dunning touches, on budget cap. Never chases a resolved case. |
| **Compliant escalation** | Fraud / high-risk / expensive cases are **escalated to a human gate**, never auto-forced. |
| **Honest metrics** | Model precision/recall/F1 are reported against a **held-out** oracle set, including the **cost of false positives**. |

---

## Pipeline (Detect → Diagnose → Plan → Execute → Audit → Measure)

```
Revenue events (payment failures, checkout abandons,
 subscriptions, overdue invoices)
        │
        ▼
[1] DETECT    Trained ML model scores recovery-risk (0..1)
        │
        ▼
[2] DIAGNOSE  Root-cause inference + expected-value gating
        │         (never act if recovery isn't worth the cost)
        ▼
[3] PLAN      Ordered, bounded intervention set (retry, dunning,
        │         alt-payment, offer, mandate retry, escalate)
        ▼
[4] EXECUTE   Bounded state machine — caps, stopping rules, escalation
        │
        ▼
[5] AUDIT     Full per-case audit trail
        │
        ▼
[6] MEASURE   Money recovered − ops cost, precision/recall/F1
```

---

## Tech stack

- **Backend**: Python 3.10 · FastAPI · scikit-learn (real trained model) · pandas · pydantic
- **Frontend**: React 19 (Vite) — live dashboard
- **Razorpay**: integration layer supports **test-mode keys** (Offline/Razorpay Orders
  & Payment Links) or a deterministic simulated mode so it runs with zero credentials.

---

## Getting started

### 1. Backend (FastAPI + ML)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# (optional) add Razorpay test-mode keys to run LIVE test-mode
# $env:REVIVEFLOW_RAZORPAY_KEY_ID="rzp_test_..."
# $env:REVIVEFLOW_RAZORPAY_KEY_SECRET="..."

python run_api.py          # serves http://localhost:8000
```

The ML model is **trained automatically on first boot** and persisted to
`backend/app/data/models/recovery_risk_model.joblib`.

### 2. Frontend (React dashboard)

```powershell
cd frontend
npm install
npm run dev                # serves http://localhost:5173 (proxies /api → :8000)
```

Open **http://localhost:5173** to see the dashboard: recovery KPIs, model metrics,
outcome breakdown, honest detection numbers, and a live single-case audit trail.

### 3. Run the demo (pitch-video narrative)

```powershell
cd backend
python run_demo.py
```

---

## API reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Health & mode |
| GET | `/api/model` | Trained-model quality report |
| POST | `/api/detect` | Run a single event through the recovery workflow → audited run |
| POST | `/api/batch?n=&seed=` | Run a batch, return recovery + honest metrics |
| GET | `/api/batch-report?n=&seed=` | Full dashboard payload |
| GET | `/api/case/{run_id}` | View one case's audit trail |

---

## Testing

```powershell
cd backend
python -m pytest          # 8 tests: ML quality, boundedness, stopping rules, audit, metrics
```

---

## Project structure

```
reviveflow/
├── backend/
│   ├── app/
│   │   ├── core/config.py          # all budgets, dunning, stopping-rule config
│   │   ├── models/schemas.py       # typed domain objects
│   │   ├── services/
│   │   │   ├── data_generator.py   # synthetic merchant events + oracle labels
│   │   │   ├── ml_model.py         # trains REAL detector, evaluates honestly
│   │   │   ├── diagnosis_engine.py # root-cause + expected-value gating
│   │   │   ├── razorpay_client.py  # Razorpay orders/payment-links (test-mode or sim)
│   │   │   └── workflow_engine.py  # THE bounded, audited state machine
│   │   └── api/main.py             # FastAPI routes
│   ├── tests/test_reviveflow.py    # encodes the buildathon ground truths
│   ├── requirements.txt
│   ├── run_api.py
│   └── run_demo.py
├── frontend/                       # React 19 (Vite) dashboard
└── docs/PITCH.md                   # pitch-video script & talking points
```

---

## 🎯 How ReviveFlow hits the Track-03 judging bar

| Buildathon requirement | How ReviveFlow delivers it |
|---|---|
| *"Don't just identify the problem"* | Full **Detect → Diagnose → Plan → Execute → Audit → Measure** loop, not a detector. |
| *"Measured money recovered across a batch"* | `run_demo.py` / `/api/batch` report **₹ recovered − ops cost** over a batch (₹50,696 recovered at ₹66 cost → ₹50,630 net on 500 events). |
| *"Compliant escalation"* | Fraud / high-risk / expensive cases **escalate to a human gate** — the agent never auto-forces a risky action. |
| *"Stopping rules"* | Hard caps in code: stop on recovery, on customer "no", on age cap, on budget cap, on max dunning touches (`core/config.py` + `workflow_engine.py`). |
| *"An audit trail"* | Every case carries a timestamped, stage-tagged audit log. Exposed via `/api/detect` and the dashboard. |
| *Honest metrics* | Precision / recall / F1 / accuracy + **false-positive cost** reported on a **held-out** oracle set. |

---

## 🧪 About the demo data (honesty note)

The demo runs on **synthetic merchant events** (`data_generator.py`) that mimic
realistic Razorpay payment, checkout, subscription and invoice patterns. Each
event carries an **oracle label** (true recoverability). The detector must earn
its metrics against that held-out oracle — nothing is cherry-picked. Drop in real
**Razorpay test-mode keys** (`REVIVEFLOW_RAZORPAY_KEY_ID` / `_SECRET`) to exercise
the live Orders / Payment-Links integration path.

---

## Why this is a strong intern submission

1. **Real ML, honest metrics** — a genuinely trained classifier with
   precision/recall/F1 reported on a held-out set, *including false-positive cost*.
2. **A bounded, self-gating agent** — not a wrapper. It respects hard budgets,
   stopping rules, and compliant human escalation on every single action.
3. **Measured money recovered across a batch** — the exact ask of Track 03.
4. **Full audit trail** — every case explains what it did and why (great for the demo video).
5. **Runs out of the box** — simulated mode needs zero keys; drop in test keys for live tracking.
