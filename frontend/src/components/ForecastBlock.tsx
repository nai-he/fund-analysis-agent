import type { ForecastPeriod } from '../types'
import { riseFallColor } from '../utils/format'

export function ForecastBlock({ fp }: { fp?: ForecastPeriod }) {
  if (!fp) return <p className="forecast-na">数据不足</p>
  const up = fp.up_probability ?? 33
  const sw = fp.sideways_probability ?? 34
  const dn = fp.down_probability ?? 33
  const range = fp.expected_return_range
  const rangeText = range && range.low != null && range.high != null
    ? `${range.low}% ~ ${range.high}%`
    : 'N/A'

  const label = fp.rise_fall || fp.direction || 'N/A'
  const labelColor = riseFallColor(fp.rise_fall, fp.direction)

  return (
    <div className="forecast-block">
      <div className="forecast-direction" style={{ color: labelColor }}>
        涨跌判断：{label}
        <span className="forecast-confidence">（置信度：{fp.confidence || 'N/A'}）</span>
      </div>
      <div className="forecast-range">
        <span>概率涨跌幅区间</span>
        <strong>{rangeText}</strong>
      </div>

      {/* 概率条 */}
      <div className="prob-bars">
        <div className="prob-row">
          <span className="prob-label up-label">上行</span>
          <div className="prob-bar-bg">
            <div className="prob-bar up-bar" style={{ width: `${up}%` }} />
          </div>
          <span className="prob-val">{up}%</span>
        </div>
        <div className="prob-row">
          <span className="prob-label sw-label">震荡</span>
          <div className="prob-bar-bg">
            <div className="prob-bar sw-bar" style={{ width: `${sw}%` }} />
          </div>
          <span className="prob-val">{sw}%</span>
        </div>
        <div className="prob-row">
          <span className="prob-label dn-label">下行</span>
          <div className="prob-bar-bg">
            <div className="prob-bar dn-bar" style={{ width: `${dn}%` }} />
          </div>
          <span className="prob-val">{dn}%</span>
        </div>
      </div>

      {/* 理由 */}
      {fp.reasons && fp.reasons.length > 0 && (
        <div className="forecast-reasons">
          <span className="forecast-subtitle">判断依据：</span>
          {fp.reasons.map((r, i) => <span key={i} className="forecast-reason-tag">{r}</span>)}
        </div>
      )}
      {fp.estimate_used && fp.estimate_note && (
        <p className="forecast-estimate-note">{fp.estimate_note}</p>
      )}

      {/* 上行情景 */}
      {fp.up_triggers && fp.up_triggers.length > 0 && (
        <div className="forecast-triggers">
          <span className="forecast-subtitle up-trigger-title">上行情景：</span>
          <ul className="trigger-list">
            {fp.up_triggers.map((t, i) => <li key={i} className="trigger-item up-trigger">{t}</li>)}
          </ul>
        </div>
      )}

      {/* 下行情景 */}
      {fp.down_triggers && fp.down_triggers.length > 0 && (
        <div className="forecast-triggers">
          <span className="forecast-subtitle dn-trigger-title">下行情景：</span>
          <ul className="trigger-list">
            {fp.down_triggers.map((t, i) => <li key={i} className="trigger-item dn-trigger">{t}</li>)}
          </ul>
        </div>
      )}

      {/* 模型基础和回测信息 */}
      {fp.model_basis && (
        <p style={{ fontSize: 11, marginTop: 6, color: fp.probability_quality === 'low' ? '#f59e0b' : '#9ca3af' }}>
          模型：{fp.model_basis === 'calibrated_rule_based' ? '校准规则模型' : '规则模型'}
          {fp.probability_quality && (
            <span> | 概率质量：{fp.probability_quality === 'high' ? '高' : fp.probability_quality === 'medium' ? '中' : '低（回测未验证优于基准）'}</span>
          )}
        </p>
      )}
      {fp.main_uncertainties && fp.main_uncertainties.length > 0 && (
        <ul style={{ fontSize: 11, color: '#9ca3af', margin: '2px 0 0 16px', padding: 0, listStyle: 'disc' }}>
          {fp.main_uncertainties.map((u, i) => <li key={i}>{u}</li>)}
        </ul>
      )}

      {/* 风险提示 */}
      <p className="forecast-risk-hint">以上为概率化情景判断，不是确定预测。不构成投资建议。</p>
    </div>
  )
}
