import { riskColor } from '../utils/format'
import type { PeriodDetail } from '../types'

export function MetricItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`metric-item ${highlight ? 'metric-highlight' : ''}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  )
}

export function RiskScoreBar({ label, score }: { label: string; score?: number | null }) {
  const s = score ?? 50
  return (
    <div className="risk-score-bar-row">
      <span className="risk-score-bar-label">{label}</span>
      <div className="risk-score-bar-bg-sm">
        <div className="risk-score-bar-fill" style={{ width: `${s}%`, backgroundColor: riskColor(s) }} />
      </div>
      <span className="risk-score-bar-num">{s?.toFixed(0)}</span>
    </div>
  )
}

export function PeriodRange({ period }: { period?: PeriodDetail | null }) {
  if (!period || !period.start_date || !period.end_date) return null
  return (
    <p className="period-range-text">
      按 {period.start_date} 至 {period.end_date} 的单位净值计算
    </p>
  )
}

export function FormField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <input
        type="text"
        className="form-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}

export function EditField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="edit-form-group">
      <label className="edit-form-label">{label}</label>
      <input
        type="text"
        className="edit-form-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}
