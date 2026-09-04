# ReviveFlow — 5-Minute Pitch Script (Track 03: AI Revenue Recovery)

Use this as the blueprint for your pitch video. ~4.5 minutes of talking, 30s of
close. Includes the exact talking points the judges grade on.

---

## 0:00 – Hook (15s)
> "Every business is leaking revenue in small, quiet ways — a payment that times
> out, a checkout that gets abandoned, a subscription that silently fails, an
> invoice that slips past due. Individually each is tiny. Together they eat margin.
> Most 'solutions' just detect the leak. **ReviveFlow is an agent that finds it,
> diagnoses it, and actually gets the money back — safely, measurably, and with
> a full audit trail.**"

---

## 0:20 – The problem (30s)
- Revenue loss rarely happens in one clean step; it degrades across channels.
- The bottleneck isn't *generating* interventions — it's **verification capacity**
  and doing it **safely** at scale (the 2026 consensus the track cites).
- Manual recovery doesn't scale; naive auto-retries annoy customers and burn budget.

## 0:50 – The architecture (60s)
Show this on screen (see `docs/ARCHITECTURE.md`):
```
Detect → Diagnose → Plan → Execute(bounded) → Audit → Measure
```
- **Detect**: a real scikit-learn model scores each event's recoverability.
- **Diagnose**: root-cause inference + expected-value gating (never act if the
  recovery isn't worth the cost).
- **Plan**: ordered, bounded intervention set per cause.
- **Execute**: a bounded state machine with hard caps.
- **Audit / Measure**: full per-case trail + money-recovered economics.

## 1:50 – What makes it a *bounded agent* (the core selling point, 60s)
This is the heart. Emphasize:
1. **Bounded** – every action spends tracked resource budget; caps on cost,
   retries, and customer touches are enforced in code (`core/config.py`).
2. **Stopping rules** – it *stops* the moment money is recovered, on customer "no",
   on budget cap, on age cap. It never chases a resolved case.
3. **Compliant escalation** – fraud / high-risk / expensive cases **escalate to a
   human gate**, never auto-forced.
4. **Explainable** – a timestamped audit trail on every case.

## 2:50 – Demo (live, 60s)
Run `backend/run_demo.py` on screen:
- **Model quality** (held-out set): Precision 77.6% · Recall 66.7% · F1 71.7% ·
  Accuracy 86.1%.
- **One live case** → show the audit trail: detected → diagnosed
  `insufficient_funds` → dunning → retry → **recovered**, cost ₹0.60.
- **Batch of 500**: recovered **₹50,696** at **₹66** ops cost → **₹50,630 net**.

## 3:50 – Honest metrics (30s)
> "Here's the part most demos skip: the *cost of being wrong*."
- False positives cost **₹9.50** to action.
- Precision, recall and F1 are reported **against a held-out oracle**, not cherry-picked.
- I train a real model, evaluate it honestly, and publish the confusion matrix.

## 4:20 – Why this solves a real problem (30s)
- Directly returns real money to merchants (₹50k on one demo batch).
- Bounded + audited → actually deployable in finance ops, not a research toy.
- Built on Razorpay's test-mode APIs, extensible to live test-mode with keys.

## 4:50 – Close (10s)
> "ReviveFlow turns leaking revenue into recovered cash — measurably, safely, and
> autonomously. Recruit me and I'll build the next one with you."

---

# Key numbers to quote (reproduced by `run_demo.py`)

| Metric | Value |
|--------|-------|
| Model F1 (held-out) | 71.7% |
| Precision / Recall | 77.6% / 66.7% |
| False-positive actioning cost | ₹9.50 |
| Batch money recovered (500) | ₹50,696 |
| Batch ops cost | ₹66 |
| **Batch net value created** | **₹50,630** |

> Compute these yourself anytime: `cd backend && python run_demo.py`

---

# Advice for the submission checklist
The buildathon asks for: **public repo**, **5-min pitch video**, **the architecture**.
- [ ] Push the repo (public) — include this README and `docs/`.
- [ ] Film the pitch video following the script above; demo `run_demo.py` live.
- [ ] Include the architecture diagram (ASCII above or a rendered `ARCHITECTURE.md`).
- [ ] Add test-mode Razorpay keys placeholder in README so judges see the live path.
- [ ] Mention Track 03 explicitly and call out the *bounded / audit / stopping-rule* bar.
- [ ] Record honest metrics on a *held-out* set (already built in).
