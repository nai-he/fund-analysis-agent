import type { BatchFundResult, UserFundItem } from '../types'
import { riskColor, batchActionColor, directionColor, directionLabel } from '../utils/format'

export function PortfolioSummaryCard({ batchResults, myFunds }: { batchResults: BatchFundResult[]; myFunds: UserFundItem[] }) {
  const totalFunds = myFunds.length
  const successResults = batchResults.filter(r => r.success)
  const successCount = successResults.length
  const failCount = batchResults.length - successCount

  // 总持有金额
  const totalHolding = myFunds.reduce((sum, f) => sum + (f.holding_amount || 0), 0)

  // 估算总盈亏
  let totalPnlAbs = 0
  let totalCost = 0
  for (const r of successResults) {
    const fi = myFunds.find(f => f.code === r.code)
    if (!fi || fi.cost_nav == null || fi.cost_nav <= 0) continue
    const nav = r.metrics?.latest_nav
    if (nav == null) continue
    const units = fi.holding_units || (fi.holding_amount ? fi.holding_amount / fi.cost_nav : 0)
    if (units <= 0) continue
    totalCost += fi.cost_nav * units
    totalPnlAbs += (nav - fi.cost_nav) * units
  }
  const totalPnlPct = totalCost > 0 ? (totalPnlAbs / totalCost * 100) : null

  // 平均风险评分
  const riskScores = successResults.filter(r => r.risk?.risk_score != null).map(r => r.risk!.risk_score!)
  const avgRisk = riskScores.length > 0 ? riskScores.reduce((a, b) => a + b, 0) / riskScores.length : null

  // 高风险基金（risk_score > 70）
  const highRiskCount = successResults.filter(r => (r.risk?.risk_score || 0) > 70).length

  // 低回测质量
  const lowQualityCount = successResults.filter(r => r.forecast?.validation?.probability_quality === 'low').length

  // 偏谨慎/降低仓位风险
  const cautiousCount = successResults.filter(r => {
    const bias = r.forecast?.decision_support?.action_bias
    return bias === '偏谨慎' || bias === '降低仓位风险'
  }).length

  return (
    <div className="portfolio-summary">
      <h4 className="portfolio-summary-title">组合概览</h4>
      <div className="portfolio-summary-grid">
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">基金数量</span>
          <span className="portfolio-summary-value">{totalFunds}</span>
        </div>
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">分析成功/失败</span>
          <span className="portfolio-summary-value">
            <span style={{ color: '#16a34a' }}>{successCount}</span>
            {failCount > 0 && <span style={{ color: '#dc2626' }}> / {failCount}</span>}
          </span>
        </div>
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">总持有金额</span>
          <span className="portfolio-summary-value">{totalHolding > 0 ? `${totalHolding.toLocaleString()}元` : 'N/A'}</span>
        </div>
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">估算总盈亏</span>
          <span className="portfolio-summary-value" style={{ color: totalPnlPct != null ? (totalPnlPct >= 0 ? '#16a34a' : '#dc2626') : '#9ca3af' }}>
            {totalPnlPct != null ? `${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct.toFixed(2)}%` : 'N/A'}
            {totalPnlAbs !== 0 ? ` (${totalPnlAbs >= 0 ? '+' : ''}${totalPnlAbs.toFixed(0)}元)` : ''}
          </span>
        </div>
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">平均风险评分</span>
          <span className="portfolio-summary-value" style={{ color: avgRisk != null ? riskColor(avgRisk) : '#9ca3af' }}>
            {avgRisk != null ? avgRisk.toFixed(0) : 'N/A'}
          </span>
        </div>
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">高风险基金（{'>'}70）</span>
          <span className="portfolio-summary-value" style={{ color: highRiskCount > 0 ? '#dc2626' : '#16a34a' }}>
            {highRiskCount}只
          </span>
        </div>
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">低回测质量</span>
          <span className="portfolio-summary-value" style={{ color: lowQualityCount > 0 ? '#f59e0b' : '#16a34a' }}>
            {lowQualityCount}只
          </span>
        </div>
        <div className="portfolio-summary-item">
          <span className="portfolio-summary-label">偏谨慎/降仓位</span>
          <span className="portfolio-summary-value" style={{ color: cautiousCount > 0 ? '#f59e0b' : '#16a34a' }}>
            {cautiousCount}只
          </span>
        </div>
      </div>
    </div>
  )
}

export function PortfolioWarningsCard({ batchResults, myFunds }: { batchResults: BatchFundResult[]; myFunds: UserFundItem[] }) {
  const warnings: string[] = []
  const successResults = batchResults.filter(r => r.success)

  // 1. 高风险占比过高
  const highRiskCount = successResults.filter(r => (r.risk?.risk_score || 0) > 70).length
  if (highRiskCount > 0 && successResults.length > 0 && highRiskCount / successResults.length > 0.3) {
    warnings.push(`组合中有 ${highRiskCount} 只基金风险评分较高（>70），占比 ${(highRiskCount / successResults.length * 100).toFixed(0)}%，建议关注整体风险敞口。`)
  }

  // 2. 多数基金回测质量偏低
  const lowQualityCount = successResults.filter(r => r.forecast?.validation?.probability_quality === 'low').length
  if (lowQualityCount > 0 && successResults.length > 0 && lowQualityCount / successResults.length > 0.5) {
    warnings.push(`多数基金（${lowQualityCount}/${successResults.length}）回测质量偏低，历史回测未证明规则优于基准，概率判断仅作低置信参考，建议结合其他信息辅助判断。`)
  }

  // 3. 偏谨慎基金较多
  const cautiousCount = successResults.filter(r => {
    const bias = r.forecast?.decision_support?.action_bias
    return bias === '偏谨慎' || bias === '降低仓位风险'
  }).length
  if (cautiousCount > 0 && successResults.length > 0 && cautiousCount / successResults.length > 0.5) {
    warnings.push(`${cautiousCount} 只基金操作倾向偏谨慎或降低仓位风险，整体市场环境可能偏弱，建议观察。`)
  }

  // 4. 盈亏接近最大可承受亏损线
  for (const r of successResults) {
    const fi = myFunds.find(f => f.code === r.code)
    if (!fi || fi.max_loss_percent == null || fi.cost_nav == null || fi.cost_nav <= 0) continue
    const nav = r.metrics?.latest_nav
    if (nav == null) continue
    const pnlPct = (nav - fi.cost_nav) / fi.cost_nav * 100
    if (pnlPct < 0 && Math.abs(pnlPct) >= fi.max_loss_percent * 0.7) {
      const name = r.fund?.name || r.code
      warnings.push(`${name}（${r.code}）亏损 ${Math.abs(pnlPct).toFixed(1)}% 已接近最大可承受亏损线（${fi.max_loss_percent}%），建议警惕。`)
      break
    }
  }

  // 5. 分析失败
  const failCount = batchResults.filter(r => !r.success).length
  if (failCount > 0) {
    warnings.push(`${failCount} 只基金分析失败，建议检查基金代码是否正确或稍后重试。`)
  }

  if (warnings.length === 0) {
    warnings.push('当前组合未触发明显风险提示。历史表现不代表未来，请持续关注市场变化。')
  }

  return (
    <div className="portfolio-warnings">
      <h4 className="portfolio-warnings-title">组合风险提示</h4>
      <ul className="portfolio-warnings-list">
        {warnings.slice(0, 5).map((w, i) => (
          <li key={i} className="portfolio-warning-item">{w}</li>
        ))}
      </ul>
    </div>
  )
}

export function BatchResultCard({ result: r, fundItem }: { result: BatchFundResult; fundItem?: UserFundItem }) {
  if (!r.success) {
    return (
      <div className="batch-card batch-card-error">
        <span className="batch-card-code">{r.code || '???'}</span>
        <span className="batch-card-error-text">{r.error || '分析失败'}</span>
      </div>
    )
  }

  const risk = r.risk
  const forecast = r.forecast
  const ds = forecast?.decision_support
  const validation = forecast?.validation
  const metrics = r.metrics
  const fund = r.fund

  // 计算持仓盈亏
  let pnlText = ''
  if (fundItem && metrics?.latest_nav != null) {
    if (fundItem.cost_nav != null && fundItem.cost_nav > 0) {
      const pnlPct = ((metrics.latest_nav - fundItem.cost_nav) / fundItem.cost_nav * 100)
      pnlText = `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`
    }
    if (fundItem.holding_amount != null && fundItem.cost_nav != null && fundItem.cost_nav > 0) {
      const units = fundItem.holding_units || (fundItem.holding_amount / fundItem.cost_nav)
      const pnlAbs = (metrics.latest_nav - fundItem.cost_nav) * units
      pnlText += ` (${pnlAbs >= 0 ? '+' : ''}${pnlAbs.toFixed(0)}元)`
    }
  }

  return (
    <div className="batch-card">
      <div className="batch-card-header">
        <span className="batch-card-name">{fund?.name || r.code}</span>
        <span className="batch-card-code">{r.code}</span>
        {metrics?.latest_nav != null && (
          <span className="batch-card-nav">净值 {metrics.latest_nav}</span>
        )}
        {pnlText && (
          <span className={`batch-card-pnl ${pnlText.startsWith('+') ? 'pnl-positive' : 'pnl-negative'}`}>
            盈亏 {pnlText}
          </span>
        )}
      </div>

      <div className="batch-card-body">
        {/* 风险评分 */}
        {risk && (
          <div className="batch-risk-row">
            <span className="batch-risk-label">风险</span>
            <div className="batch-risk-bar-bg">
              <div className="batch-risk-bar" style={{
                width: `${risk.risk_score || 50}%`,
                backgroundColor: riskColor(risk.risk_score || 50),
              }} />
            </div>
            <span className="batch-risk-score" style={{ color: riskColor(risk.risk_score || 50) }}>
              {risk.risk_score} {risk.risk_level}
            </span>
          </div>
        )}

        {/* 操作倾向 + 预测 */}
        <div className="batch-insight-row">
          {ds?.action_bias && (
            <span className="batch-action-bias" style={{ color: batchActionColor(ds.action_bias) }}>
              操作倾向：{ds.action_bias}
            </span>
          )}
          <span className="batch-forecast-short">
            7d <span style={{ color: directionColor(forecast?.forecast_7d?.direction) }}>{directionLabel(forecast?.forecast_7d?.direction)}</span>
            {' '}30d <span style={{ color: directionColor(forecast?.forecast_30d?.direction) }}>{directionLabel(forecast?.forecast_30d?.direction)}</span>
          </span>
        </div>

        {/* 回测概率质量 */}
        {validation && validation.sample_size != null && validation.sample_size > 0 && (
          <div className="batch-validation-row">
            <span className="batch-quality" style={{ color: validation.probability_quality === 'low' ? '#f59e0b' : validation.probability_quality === 'medium' ? '#eab308' : '#16a34a' }}>
              回测质量：{validation.probability_quality === 'high' ? '高' : validation.probability_quality === 'medium' ? '中' : '低'}
            </span>
            <span className="batch-accuracy">（7d准确率 {validation.periods?.['7d']?.directional_accuracy ?? 'N/A'}%）</span>
          </div>
        )}

        {/* 主要风险 1-2 条 */}
        {r.analysis?.main_risks && r.analysis.main_risks.length > 0 && (
          <div className="batch-risks-row">
            {r.analysis.main_risks.slice(0, 2).map((riskText, i) => (
              <span key={i} className="batch-risk-tag">{riskText}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
