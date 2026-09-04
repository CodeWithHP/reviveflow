import { useCallback, useEffect, useState } from 'react'
import './App.css'

function fmtINR(v) {
  return '₹' + Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

function KpiCard({ label, value, sub, accent }) {
  return (
    <div className={`kpi ${accent || ''}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}

function Bar({ label, value, max, color }) {
  const pct = max ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track"><div className="bar-fill" style={{ width: pct + '%', background: color }} /></div>
      <span className="bar-val">{value}</span>
    </div>
  )
}

function AuditTrail({ audit }) {
  if (!audit || !audit.length) return null
  return (
    <div className="audit">
      <h3>Agent Audit Trail</h3>
      <ol>
        {audit.map((a, i) => (
          <li key={i}>
            <code>{a.stage}</code> <strong>{a.action}</strong>
            <span className="audit-detail">{a.details}</span>
            <span className="audit-time">{new Date(a.timestamp).toLocaleTimeString()}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function StatusBadge({ status }) {
  const cls = { recovered: 'ok', failed: 'bad', stopped: 'warn', escalated: 'esc' }[status] || 'neutral'
  return <span className={`badge ${cls}`}>{status}</span>
}

function App() {
  const [model, setModel] = useState(null)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [batchSize, setBatchSize] = useState(200)

  const loadReport = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await fetch(`/api/batch-report?n=${batchSize}&seed=11`)
      if (!res.ok) throw new Error('Failed to run batch')
      const data = await res.json()
      setReport(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [batchSize])

  useEffect(() => {
    (async () => {
      try {
        const m = await (await fetch('/api/model')).json()
        setModel(m)
      } catch { /* model endpoint optional for first paint */ }
    })()
  }, [])

  useEffect(() => { if (!report) loadReport() }, [])

  const runSingle = async () => {
    setLoading(true); setError(null)
    const event = {
      transaction_id: 'txn_demo_' + Date.now(),
      merchant_id: 'M1001',
      customer_id: 'C_DEMO',
      event_type: 'checkout_abandon',
      amount_inr: 2499,
      occurred_at: new Date(Date.now() - 2 * 86400000).toISOString(),
      last_payment_method: 'upi',
      attempts: 0,
      metadata: { root_cause: 'insufficient_funds' },
    }
    try {
      const res = await fetch('/api/detect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(event),
      })
      if (!res.ok) throw new Error('detect failed')
      const data = await res.json()
      setSelected(data)
      loadReport()
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  const s = report?.summary
  const dm = report?.detection_metrics

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">⟳</span>
          <div>
            <h1>ReviveFlow</h1>
            <span className="tagline">Agentic Revenue Recovery Copilot for Razorpay</span>
          </div>
        </div>
        <div className="controls">
          <label>Batch
            <select value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))}>
              {[100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button className="primary" onClick={loadReport} disabled={loading}>
            {loading ? 'Running…' : 'Run Batch'}
          </button>
          <button className="ghost" onClick={runSingle} disabled={loading}>Run Single Case</button>
        </div>
      </header>

      {error && <div className="error">⚠ {error}</div>}

      <main>
        {model && (
          <section className="panel model">
            <h2>ML Recovery-Risk Detector <em>(held-out test set)</em></h2>
            <div className="model-cards">
              <KpiCard label="Model" value={model.model} />
              <KpiCard label="Precision" value={(model.precision * 100).toFixed(1) + '%'} />
              <KpiCard label="Recall" value={(model.recall * 100).toFixed(1) + '%'} />
              <KpiCard label="F1" value={(model.f1 * 100).toFixed(1) + '%'} />
              <KpiCard label="Accuracy" value={(model.accuracy * 100).toFixed(1) + '%'} />
            </div>
            <div className="model-econ">
              <span>False-positives cost {fmtINR(model.fp_cost_total_inr)} to act</span>
              <span>Gross recovery {fmtINR(model.recovered_gross_inr)}</span>
              <span className="pos">Net leverage {fmtINR(model.net_leverage_inr)}</span>
            </div>
          </section>
        )}

        {s && (
          <section className="panel">
            <h2>Recovery Performance — batch of {report.batch_size}</h2>
            <div className="kpis">
              <KpiCard label="Events scanned" value={s.total_events} />
              <KpiCard label="Recovered" value={s.recovered_count} accent="pos" />
              <KpiCard label="Money recovered" value={fmtINR(s.recovered_amount_inr)} accent="pos" />
              <KpiCard label="Ops cost" value={fmtINR(s.total_cost_inr)} />
              <KpiCard label="Net value created" value={fmtINR(s.net_value_inr)} accent="pos" />
            </div>
            <div className="split">
              <div className="sub">
                <h4>Outcomes</h4>
                <Bar label="Recovered" value={s.status_breakdown.recovered || 0} max={s.total_events} color="#16a34a" />
                <Bar label="Stopped (safe)" value={s.status_breakdown.stopped || 0} max={s.total_events} color="#f59e0b" />
                <Bar label="Failed" value={s.status_breakdown.failed || 0} max={s.total_events} color="#ef4444" />
                <Bar label="Escalated" value={s.status_breakdown.escalated || 0} max={s.total_events} color="#6366f1" />
              </div>
              <div className="sub">
                <h4>Detection vs Oracle (honest metrics)</h4>
                {dm && (
                  <div className="dm">
                    <Bar label="True positives" value={dm.true_positives} max={dm.oracle_positives} color="#16a34a" />
                    <Bar label="False positives" value={dm.false_positives} max={Math.max(1, dm.oracle_negatives)} color="#ef4444" />
                    <Bar label="False negatives" value={dm.false_negatives} max={Math.max(1, dm.oracle_positives)} color="#f59e0b" />
                    <div className="dm-metrics">
                      <span>P {(dm.precision * 100).toFixed(1)}%</span>
                      <span>R {(dm.recall * 100).toFixed(1)}%</span>
                      <span>F1 {(dm.f1 * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

        {selected && (
          <section className="panel case">
            <h2>Live Case — {selected.event.transaction_id}</h2>
            <div className="case-head">
              <StatusBadge status={selected.status} />
              <span>Amount {fmtINR(selected.event.amount_inr)}</span>
              <span>Recovered {fmtINR(selected.recovered_inr)}</span>
              <span>Cost {fmtINR(selected.total_cost_inr)}</span>
            </div>
            {selected.diagnosis && (
              <div className="diag">
                <strong>Root cause:</strong> {selected.diagnosis.root_cause}
                <span className="muted"> (conf {selected.diagnosis.confidence}, recoverable {String(selected.diagnosis.recoverable)})</span>
                <div className="reason">{selected.diagnosis.reason}</div>
              </div>
            )}
            {selected.stop_reason && <div className="stop">Stopped: {selected.stop_reason}</div>}
            <AuditTrail audit={selected.audit} />
          </section>
        )}
      </main>

      <footer>
        ReviveFlow — bounded · explainable · audited. Every money action gated by
        stopping rules & compliance escalation. Built for Razorpay AI Buildathon (Track 03).
      </footer>
    </div>
  )
}

export default App
