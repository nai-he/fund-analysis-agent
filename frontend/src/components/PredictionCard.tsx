import type { PredictionResult, PredictionPeriod } from '../types'

function confidenceClass(confidence?: string) {
  if (confidence === '高') return 'confidence-high'
  if (confidence === '低') return 'confidence-low'
  return 'confidence-medium'
}

function edgeClass(edge?: number | null) {
  if (edge == null) return 'prediction-edge-neutral'
  if (edge > 0) return 'prediction-edge-positive'
  if (edge < 0) return 'prediction-edge-negative'
  return 'prediction-edge-neutral'
}

function fmtPct(value?: number | null) {
  return value == null ? 'N/A' : `${value}%`
}

function fmtNum(value?: number | null) {
  return value == null ? 'N/A' : `${value}`
}

function PredictionPeriodBlock({ label, period }: { label: string; period?: PredictionPeriod }) {
  if (!period) {
    return (
      <div className="prediction-period">
        <h4 className="prediction-period-title">{label}</h4>
        <p className="forecast-na">数据不足</p>
      </div>
    )
  }

  const up = period.up_probability ?? 50
  const downOrFlat = period.down_or_flat_probability ?? 50
  const noEdge = period.has_positive_edge === false
  const selectiveActive = period.current_passes_selective_threshold === true
  const targetHitRate = period.selective_target_hit_rate
  const isSpecificTarget = targetHitRate != null && targetHitRate >= 80

  return (
    <div className={`prediction-period ${noEdge ? 'prediction-period-weak' : ''} ${selectiveActive ? 'prediction-period-strong' : ''}`}>
      <div className="prediction-period-head">
        <h4 className="prediction-period-title">{label}</h4>
        <span className={`decision-confidence ${confidenceClass(period.confidence)}`}>
          {period.confidence || '低'}
        </span>
      </div>

      <div className="prediction-direction-row">
        <span className={`prediction-direction prediction-direction-${period.predicted_direction || 'uncertain'}`}>
          {period.direction_label || '不确定'}
        </span>
        {noEdge && <span className="prediction-no-edge">无可验证优势</span>}
        {selectiveActive && <span className="prediction-high-win">{isSpecificTarget ? '80%专训触发' : '高胜率触发'}</span>}
        {!selectiveActive && isSpecificTarget && <span className="prediction-trained-wait">80%专训等待</span>}
      </div>

      <div className="prediction-prob-main">
        <span>上涨概率</span>
        <strong>{fmtPct(up)}</strong>
      </div>
      <div className="prediction-prob-bars">
        <div className="prediction-prob-up" style={{ width: `${Math.max(0, Math.min(100, up))}%` }} />
        <div className="prediction-prob-down" style={{ width: `${Math.max(0, Math.min(100, downOrFlat))}%` }} />
      </div>
      <div className="prediction-prob-legend">
        <span>涨 {fmtPct(up)}</span>
        <span>不涨 {fmtPct(downOrFlat)}</span>
      </div>

      <div className="prediction-stats-grid">
        <div>
          <span>历史命中</span>
          <strong>{fmtPct(period.historical_hit_rate)}</strong>
        </div>
        <div>
          <span>基线命中</span>
          <strong>{fmtPct(period.baseline_hit_rate)}</strong>
        </div>
        <div>
          <span>模型优势</span>
          <strong className={edgeClass(period.edge_vs_baseline)}>
            {period.edge_vs_baseline == null ? 'N/A' : `${period.edge_vs_baseline > 0 ? '+' : ''}${period.edge_vs_baseline}%`}
          </strong>
        </div>
        <div>
          <span>样本数</span>
          <strong>{period.sample_size ?? 0}</strong>
        </div>
        <div>
          <span>精筛命中</span>
          <strong>{fmtPct(period.selective_hit_rate)}</strong>
        </div>
        <div>
          <span>精筛阈值</span>
          <strong>{fmtPct(period.selective_threshold)}</strong>
        </div>
        <div>
          <span>触发样本</span>
          <strong>{period.selective_signal_count ?? 0}</strong>
        </div>
        <div>
          <span>精筛优势</span>
          <strong className={edgeClass(period.selective_edge_vs_baseline)}>
            {period.selective_edge_vs_baseline == null ? 'N/A' : `${period.selective_edge_vs_baseline > 0 ? '+' : ''}${period.selective_edge_vs_baseline}%`}
          </strong>
        </div>
        <div>
          <span>目标胜率</span>
          <strong>{fmtPct(period.selective_target_hit_rate)}</strong>
        </div>
        <div>
          <span>最低样本</span>
          <strong>{period.selective_min_required_signals ?? 0}</strong>
        </div>
        <div>
          <span>训练命中</span>
          <strong>{fmtPct(period.selective_train_hit_rate)}</strong>
        </div>
        <div>
          <span>训练样本</span>
          <strong>{period.selective_train_signal_count ?? 0}</strong>
        </div>
        <div>
          <span>样本外命中</span>
          <strong>{fmtPct(period.selective_validation_hit_rate)}</strong>
        </div>
        <div>
          <span>样本外样本</span>
          <strong>{period.selective_validation_signal_count ?? 0}</strong>
        </div>
        <div>
          <span>多折通过</span>
          <strong>{fmtPct(period.selective_cv_pass_rate)}</strong>
        </div>
        <div>
          <span>可评估折数</span>
          <strong>{period.selective_cv_evaluable_folds ?? 0}</strong>
        </div>
        <div>
          <span>命中下界</span>
          <strong>{fmtPct(period.selective_hit_rate_lower_bound)}</strong>
        </div>
        <div>
          <span>精筛均收</span>
          <strong>{fmtPct(period.selective_avg_return)}</strong>
        </div>
        <div>
          <span>最差收益</span>
          <strong>{fmtPct(period.selective_worst_return)}</strong>
        </div>
        <div>
          <span>收益因子</span>
          <strong>{fmtNum(period.selective_profit_factor)}</strong>
        </div>
        <div>
          <span>验证状态</span>
          <strong>{period.selective_validation_passed ? '通过' : '未过'}</strong>
        </div>
      </div>

      {period.selective_rule_text && (
        <p className="prediction-rule-text">专训规则：{period.selective_rule_text}</p>
      )}
      {period.selective_training_status && (
        <p className="prediction-rule-text">训练状态：{period.selective_training_status}</p>
      )}

      {period.main_reasons && period.main_reasons.length > 0 && (
        <ul className="prediction-reasons">
          {period.main_reasons.slice(0, 4).map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}

      {period.warning && <p className="prediction-warning">{period.warning}</p>}
    </div>
  )
}

export function PredictionCard({ prediction }: { prediction?: PredictionResult }) {
  if (!prediction || prediction.status === 'unavailable') return null
  const periods = prediction.periods || {}
  const specificTraining = prediction.specific_training

  return (
    <div className="card prediction-card">
      <h3 className="prediction-title">上涨概率验证</h3>
      <p className="prediction-hint">
        二分类判断“涨 / 不涨”，并用历史 walk-forward 回测对比简单基线；没跑赢基线的周期会降为低置信。
      </p>

      {specificTraining?.enabled && (
        <div className="prediction-trained-banner">
          <strong>指定基金专属训练</strong>
          <span>
            目标历史命中率 {fmtPct(specificTraining.target_hit_rate)}，只在满足专训规则时触发；未触发时默认等待。
          </span>
          {specificTraining.factor_status === 'available' && (
            <span>
              已纳入重仓股/行业代理因子：
              {specificTraining.factor_sources?.[0]?.holdings?.slice(0, 4).join('、') || '股票篮子'}
            </span>
          )}
          {specificTraining.factor_status && specificTraining.factor_status !== 'available' && (
            <span>{specificTraining.factor_note || '未取得可回测代理因子，本次仅使用基金净值训练。'}</span>
          )}
        </div>
      )}

      {prediction.summary && <p className="prediction-summary">{prediction.summary}</p>}

      <div className="prediction-grid">
        <PredictionPeriodBlock label="未来1天" period={periods['1d']} />
        <PredictionPeriodBlock label="未来3天" period={periods['3d']} />
        <PredictionPeriodBlock label="未来7天" period={periods['7d']} />
        <PredictionPeriodBlock label="未来30天" period={periods['30d']} />
      </div>

      <p className="prediction-disclaimer">
        {prediction.disclaimer || '仅供个人研究参考，不构成投资建议。历史回测不代表未来表现。'}
      </p>
    </div>
  )
}
