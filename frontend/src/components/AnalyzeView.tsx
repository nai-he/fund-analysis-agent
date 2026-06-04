import type { AnalyzeResult, PositionInput, TabKey, SectionKey } from '../types'
import { fmtVal, fmtNum, conclusionColor, riskColor, profileLabel } from '../utils/format'
import { MetricItem, RiskScoreBar, PeriodRange, FormField } from './common'
import { ForecastBlock } from './ForecastBlock'
import { PredictionCard } from './PredictionCard'

interface AnalyzeViewProps {
  code: string
  setCode: (v: string) => void
  loading: boolean
  error: string | null
  result: AnalyzeResult | null
  showPosition: boolean
  setShowPosition: (v: boolean) => void
  position: PositionInput
  setPosition: (p: PositionInput) => void
  activeTab: TabKey
  setActiveTab: (t: TabKey) => void
  activeSection: SectionKey
  setActiveSection: (s: SectionKey) => void
  showRaw: boolean
  setShowRaw: (v: boolean) => void
  handleAnalyze: () => void
  handleKeyDown: (e: React.KeyboardEvent) => void
}

export function AnalyzeView({
  code, setCode, loading, error, result,
  showPosition, setShowPosition, position, setPosition,
  activeTab, setActiveTab, activeSection, setActiveSection,
  showRaw, setShowRaw, handleAnalyze, handleKeyDown,
}: AnalyzeViewProps) {
  const fund = result?.fund
  const profile = result?.fund_profile
  const metrics = result?.metrics
  const macro = result?.macro
  const risk = result?.risk
  const forecast = result?.forecast
  const prediction = result?.prediction
  const analysis = result?.analysis
  const decision_advice = result?.decision_advice
  const final_decision = result?.final_decision
  const high_confidence_decision = result?.high_confidence_decision

  return (
    <div className="tab-fade-in">
    <>
    {/* 输入区域 */}
    <div className="search-bar">
      <input
        type="text"
        className="code-input"
        placeholder="输入基金代码，如 161725、110022、510300"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={handleKeyDown}
        maxLength={6}
      />
      <button className="analyze-btn" onClick={handleAnalyze} disabled={loading}>
        {loading ? '分析中...' : '开始分析'}
      </button>
    </div>

    {/* 持仓输入折叠 */}
    <div className="position-toggle-row">
      <button className="position-toggle" onClick={() => setShowPosition(!showPosition)}>
        {showPosition ? '收起我的持仓 ▲' : '填写我的持仓（可选） ▼'}
      </button>
    </div>

    {showPosition && (
      <div className="card position-form">
        <h3>我的持仓（全部可选）</h3>
        <div className="position-grid">
          <FormField label="持仓成本价" value={position.cost_nav} onChange={(v) => setPosition({ ...position, cost_nav: v })} placeholder="如 0.75" />
          <FormField label="持有金额（元）" value={position.holding_amount} onChange={(v) => setPosition({ ...position, holding_amount: v })} placeholder="如 10000" />
          <FormField label="持有份额（份）" value={position.holding_units} onChange={(v) => setPosition({ ...position, holding_units: v })} placeholder="如 13000" />
          <FormField label="计划买入金额（元）" value={position.planned_buy_amount} onChange={(v) => setPosition({ ...position, planned_buy_amount: v })} placeholder="如 5000（选填）" />
          <FormField label="每月定投金额" value={position.monthly_dca_amount} onChange={(v) => setPosition({ ...position, monthly_dca_amount: v })} placeholder="如 1000" />
          <FormField label="最大可承受亏损%" value={position.max_loss_percent} onChange={(v) => setPosition({ ...position, max_loss_percent: v })} placeholder="如 15" />
          <div className="form-group">
            <label className="form-label">是否定投</label>
            <label className="checkbox-label">
              <input type="checkbox" checked={position.is_dca} onChange={(e) => setPosition({ ...position, is_dca: e.target.checked })} />
              是，我正在进行定投
            </label>
          </div>
          <div className="form-group">
            <label className="form-label">计划持有周期</label>
            <select className="form-select" value={position.holding_horizon} onChange={(e) => setPosition({ ...position, holding_horizon: e.target.value })}>
              <option value="">不填写</option>
              <option value="短期">短期</option>
              <option value="3-6个月">3-6个月</option>
              <option value="1年以上">1年以上</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">操作偏好</label>
            <select className="form-select" value={position.risk_preference} onChange={(e) => setPosition({ ...position, risk_preference: e.target.value })}>
              <option value="">不填写</option>
              <option value="保守">保守</option>
              <option value="平衡">平衡</option>
              <option value="激进">激进</option>
            </select>
          </div>
        </div>
      </div>
    )}

    {/* 错误 */}
    {error && <div className="error-banner"><span className="error-icon">!</span><span>{error}</span></div>}

    {/* 加载 */}
    {loading && (
      <div className="loading-area">
        <div className="spinner" />
        <p>正在获取基金数据并进行分析...</p>
        <p className="loading-hint">流程：基金信息 → 基金画像 → 净值数据 → 指标计算 → 风险评分 → AI分析</p>
      </div>
    )}

    {/* 结果 */}
    {result && result.success && fund && metrics && analysis && (
      <div className="results">
        {/* 基金名称 + 风险评分 */}
        <div className="card fund-card">
          <div className="fund-header">
            <div className="fund-title-row">
              <h2>{fund.name}</h2>
              <span className="fund-code-badge">{fund.code}</span>
            </div>
            <div className="fund-meta">
              <span className="meta-tag">{fund.type}</span>
              <span className="meta-tag">{fund.company}</span>
              <span className="meta-tag">净值 {metrics.latest_nav}</span>
            </div>
            {(fund.type?.includes('QDII') || fund.name?.includes('QDII') || fund.name?.includes('海外') || fund.name?.includes('纳斯达克') || fund.name?.includes('标普') || fund.name?.includes('港股')) && (
              <p className="qdii-delay-notice">QDII 净值存在披露延迟，最新净值日期可能滞后。</p>
            )}
            {metrics.note_nav_delay && !(fund.type?.includes('QDII') || fund.name?.includes('QDII')) && (
              <p className="qdii-delay-notice">{metrics.note_nav_delay}</p>
            )}
            {metrics.current_estimate?.estimated_change_pct != null && (
              <p className="estimate-notice">
                当日估算：{metrics.current_estimate.estimated_change_pct >= 0 ? '+' : ''}{metrics.current_estimate.estimated_change_pct}%
                {metrics.current_estimate.estimated_nav != null ? `，估算净值 ${metrics.current_estimate.estimated_nav}` : ''}
                {metrics.current_estimate.estimate_time ? `（${metrics.current_estimate.estimate_time}）` : ''}
                ，非正式净值
              </p>
            )}
          </div>

          {/* 风险评分仪表 */}
          {risk && (
            <div className="risk-gauge-row">
              <div className="risk-gauge">
                <div className="risk-gauge-bar-bg">
                  <div className="risk-gauge-bar" style={{
                    width: `${risk.risk_score || 50}%`,
                    backgroundColor: riskColor(risk.risk_score || 50),
                  }} />
                </div>
                <div className="risk-gauge-label">
                  <span className="risk-score-num">{risk.risk_score}</span>
                  <span className="risk-level-text" style={{ color: riskColor(risk.risk_score || 50) }}>
                    {risk.risk_level}
                  </span>
                  {risk.position_personal_score != null && (
                    <span className="risk-personal-note">（含个人持仓）</span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 分析结论 */}
          <div className="conclusion-row">
            <span className="conclusion-label">AI 分析结论</span>
            <span className="conclusion-value" style={{ color: conclusionColor(analysis.conclusion) }}>
              {analysis.conclusion || 'N/A'}
            </span>
            <span className="confidence">置信度：{analysis.confidence || 'N/A'}</span>
          </div>
          {analysis.note && <p className="note-text">{analysis.note}</p>}
        </div>

        {/* 最终参考结论 */}
        {final_decision && (
          <div className="card final-decision-card">
            <div className="final-decision-topline">
              <span className="final-decision-kicker">最终参考结论</span>
              <h3 className="final-decision-headline">{final_decision.headline || '暂无结论'}</h3>
            </div>
            <div className="final-decision-meta">
              <span className={`decision-action-value decision-action-${final_decision.action}`}>
                {final_decision.action_label || '观察'}
              </span>
              <span className={`decision-confidence confidence-${final_decision.confidence === '高' ? 'high' : final_decision.confidence === '低' ? 'low' : 'medium'}`}>
                置信度：{final_decision.confidence || '中'}
              </span>
              <span className="final-decision-direction" style={{
                color: final_decision.direction === 'up' ? '#16a34a' :
                       final_decision.direction === 'down' ? '#dc2626' :
                       final_decision.direction === 'neutral' ? '#f59e0b' : '#6b7280'
              }}>
                {final_decision.direction_label || '不确定'}
              </span>
            </div>
            {final_decision.summary && (
              <p className="final-decision-summary">{final_decision.summary}</p>
            )}
            <div className="final-decision-stats">
              {final_decision.up_probability_7d != null && (
                <span>7天上涨概率 <strong>{final_decision.up_probability_7d}%</strong></span>
              )}
              {final_decision.up_probability_30d != null && (
                <span>30天上涨概率 <strong>{final_decision.up_probability_30d}%</strong></span>
              )}
              {final_decision.risk_score != null && (
                <span>风险分 <strong style={{ color: riskColor(final_decision.risk_score) }}>{final_decision.risk_score}</strong></span>
              )}
            </div>
            {final_decision.why && final_decision.why.length > 0 && (
              <ul className="final-decision-list">
                {final_decision.why.slice(0, 2).map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            )}
            {final_decision.warning && final_decision.warning.length > 0 && (
              <div className="final-decision-warning">
                {final_decision.warning.slice(0, 1).map((w: string, i: number) => (
                  <p key={i}>⚠ {w}</p>
                ))}
              </div>
            )}
            <p className="decision-disclaimer">{final_decision.disclaimer || '仅供个人研究参考，不构成投资建议。'}</p>
          </div>
        )}

        {/* 高置信度小资金决策 */}
        {high_confidence_decision && (
          <div className={`card high-confidence-card high-confidence-${high_confidence_decision.action}`}>
            <h3 className="high-confidence-title">小额资金决策</h3>
            <p className="high-confidence-hint">"小资金、高胜率优先、少出手" — 默认等待，仅在所有硬条件同时满足时才考虑小额试探。</p>

            <div className="high-confidence-main">
              <div className="high-confidence-action-row">
                <span className="high-confidence-action-label">操作建议</span>
                <span className={`high-confidence-action-value hc-action-${high_confidence_decision.action}`}>
                  {high_confidence_decision.action_label}
                </span>
                <span className={`decision-confidence confidence-${high_confidence_decision.confidence === 'high' ? 'high' : high_confidence_decision.confidence === 'low' ? 'low' : 'medium'}`}>
                  置信度：{high_confidence_decision.confidence === 'high' ? '高' : high_confidence_decision.confidence === 'medium' ? '中' : '低'}
                </span>
              </div>

              <div className="high-confidence-stats">
                <span>综合评分 <strong>{high_confidence_decision.score}</strong></span>
                {high_confidence_decision.max_position_pct > 0 && (
                  <span>最大仓位 <strong>{high_confidence_decision.max_position_pct}%</strong></span>
                )}
              </div>
            </div>

            {high_confidence_decision.reasons.length > 0 && (
              <div className="high-confidence-section">
                <h4 className="high-confidence-section-title" style={{ color: '#16a34a' }}>通过的条件</h4>
                <ul className="high-confidence-list hc-passed">
                  {high_confidence_decision.reasons.slice(0, 3).map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}

            {high_confidence_decision.blockers.length > 0 && (
              <div className="high-confidence-section">
                <h4 className="high-confidence-section-title" style={{ color: '#dc2626' }}>未通过的条件</h4>
                <ul className="high-confidence-list hc-blocked">
                  {high_confidence_decision.blockers.slice(0, 3).map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </div>
            )}

            {high_confidence_decision.risk_controls.length > 0 && (
              <div className="high-confidence-section">
                <h4 className="high-confidence-section-title" style={{ color: '#f59e0b' }}>风险控制规则</h4>
                <ul className="high-confidence-list hc-controls">
                  {high_confidence_decision.risk_controls.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </div>
            )}

            <p className="decision-disclaimer">{high_confidence_decision.disclaimer}</p>
          </div>
        )}

        {/* 买卖辅助判断 */}
            {decision_advice && (
          <div className="card decision-card">
            <h3 className="decision-title">操作参考</h3>
            <p className="decision-hint">以下为规则引擎生成的保守决策参考，不构成投资建议。</p>

            <div className="decision-main">
              <div className="decision-action-row">
                <span className="decision-action-label">操作倾向</span>
                <span className={`decision-action-value decision-action-${decision_advice.action}`}>
                  {decision_advice.action_label || '观望'}
                </span>
                <span className={`decision-confidence confidence-${decision_advice.confidence === '高' ? 'high' : decision_advice.confidence === '低' ? 'low' : 'medium'}`}>
                  置信度：{decision_advice.confidence || '中'}
                </span>
              </div>

              {decision_advice.summary && (
                <p className="decision-summary">{decision_advice.summary}</p>
              )}

              {(decision_advice.suggested_buy_amount != null && decision_advice.suggested_buy_amount > 0) && (
                <p className="decision-buy-amount">
                  本次参考执行金额：{decision_advice.suggested_buy_amount} 元
                  {decision_advice.suggested_buy_pct != null && `（按规则折算，计划金额的 ${decision_advice.suggested_buy_pct}%）`}
                </p>
              )}

              {decision_advice.position_hint && (
                <p className="decision-position-hint">{decision_advice.position_hint}</p>
              )}
            </div>

            {decision_advice.reasons && decision_advice.reasons.length > 0 && (
              <div className="decision-section">
                <h4 className="decision-section-title">判断依据</h4>
                <ul className="decision-list">
                  {decision_advice.reasons.slice(0, 3).map((r: string, i: number) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}

            {decision_advice.risk_warnings && decision_advice.risk_warnings.length > 0 && (
              <div className="decision-section">
                <h4 className="decision-section-title" style={{ color: '#dc2626' }}>风险提示</h4>
                <ul className="decision-list decision-list-warn">
                  {decision_advice.risk_warnings.slice(0, 3).map((w: string, i: number) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}

            {decision_advice.buy_conditions && decision_advice.buy_conditions.length > 0 && (
              <div className="decision-section">
                <h4 className="decision-section-title" style={{ color: '#16a34a' }}>买入关注条件</h4>
                <ul className="decision-list decision-list-buy">
                  {decision_advice.buy_conditions.slice(0, 3).map((c: string, i: number) => <li key={i}>{c}</li>)}
                </ul>
              </div>
            )}

            {decision_advice.sell_or_reduce_conditions && decision_advice.sell_or_reduce_conditions.length > 0 && (
              <div className="decision-section">
                <h4 className="decision-section-title" style={{ color: '#dc2626' }}>减仓/止损条件</h4>
                <ul className="decision-list decision-list-sell">
                  {decision_advice.sell_or_reduce_conditions.slice(0, 3).map((c: string, i: number) => <li key={i}>{c}</li>)}
                </ul>
              </div>
            )}

            {decision_advice.invalidation_signals && decision_advice.invalidation_signals.length > 0 && (
              <div className="decision-section">
                <h4 className="decision-section-title" style={{ color: '#f59e0b' }}>判断失效信号</h4>
                <ul className="decision-list decision-list-invalid">
                  {decision_advice.invalidation_signals.slice(0, 3).map((s: string, i: number) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}

            <p className="decision-disclaimer">{decision_advice.disclaimer || '仅供个人研究参考，不构成投资建议。'}</p>
          </div>
        )}

        {/* 三周期时间轴 */}
        <div className="card period-card">
          <div className="period-tabs">
            <button className={`period-tab ${activeTab === '7d' ? 'active' : ''}`} onClick={() => setActiveTab('7d')}>近7个自然日</button>
            <button className={`period-tab ${activeTab === '30d' ? 'active' : ''}`} onClick={() => setActiveTab('30d')}>近30个自然日</button>
            <button className={`period-tab ${activeTab === '90d' ? 'active' : ''}`} onClick={() => setActiveTab('90d')}>近90个自然日</button>
          </div>

          {activeTab === '7d' && (
            <div className="period-content">
              <div className="metric-grid metric-cols-3">
                <MetricItem label="涨跌幅（自然日）" value={fmtVal(metrics.return_7d_calendar)} highlight />
                <MetricItem label="最大回撤（自然日）" value={fmtVal(metrics.max_drawdown_7d_calendar)} />
                <MetricItem label="近5交易日涨跌" value={fmtVal(metrics.return_5trading)} />
              </div>
              <PeriodRange period={metrics.period_7d_calendar} />
              <p className="period-summary">{analysis.summary_7d}</p>
            </div>
          )}
          {activeTab === '30d' && (
            <div className="period-content">
              <div className="metric-grid metric-cols-3">
                <MetricItem label="涨跌幅（自然日）" value={fmtVal(metrics.return_30d_calendar)} highlight />
                <MetricItem label="最大回撤（自然日）" value={fmtVal(metrics.max_drawdown_30d_calendar)} />
                <MetricItem label="年化波动率" value={fmtVal(metrics.volatility_30d)} />
                <MetricItem label="夏普比率" value={fmtVal(metrics.sharpe_30d, '')} />
                <MetricItem label="近20交易日涨跌" value={fmtVal(metrics.return_20trading)} />
                <MetricItem label="区间位置" value={metrics.position_in_30d_range != null ? `${metrics.position_in_30d_range}%` : 'N/A'} />
              </div>
              <PeriodRange period={metrics.period_30d_calendar} />
              <p className="period-summary">{analysis.summary_30d}</p>
            </div>
          )}
          {activeTab === '90d' && (
            <div className="period-content">
              <div className="metric-grid metric-cols-3">
                <MetricItem label="涨跌幅（自然日）" value={fmtVal(metrics.return_90d_calendar)} highlight />
                <MetricItem label="最大回撤（自然日）" value={fmtVal(metrics.max_drawdown_90d_calendar)} />
                <MetricItem label="年化波动率" value={fmtVal(metrics.volatility_90d)} />
                <MetricItem label="Calmar比率" value={fmtVal(metrics.calmar_90d, '')} />
                <MetricItem label="近60交易日涨跌" value={fmtVal(metrics.return_60trading)} />
                <MetricItem label="区间位置" value={metrics.position_in_90d_range != null ? `${metrics.position_in_90d_range}%` : 'N/A'} />
                <MetricItem label="回落幅度" value={fmtVal(metrics.pullback_from_30d_high)} />
                <MetricItem label="60日均线" value={fmtVal(metrics.ma_60, '')} />
                <MetricItem label="趋势" value={metrics.trend || 'N/A'} />
              </div>
              <PeriodRange period={metrics.period_90d_calendar} />
              <p className="period-summary">{analysis.summary_90d}</p>
            </div>
          )}
        </div>

        <PredictionCard prediction={prediction} />

        {/* 未来走势情景判断 */}
        {forecast && (
          <div className="card forecast-card">
            <h3 className="forecast-title">未来涨跌情景判断</h3>
            <p className="forecast-hint">以下为基于历史净值、短线动能、趋势、回撤、波动率、风险评分和中国市场风险偏好生成的概率化情景判断，不代表确定预测，不构成投资建议。</p>

            <div className="forecast-grid-4">
              {/* 未来1天 */}
              <div className="forecast-period">
                <h4 className="forecast-period-title">未来1天</h4>
                <ForecastBlock fp={forecast.forecast_1d} />
              </div>
              {/* 未来3天 */}
              <div className="forecast-period">
                <h4 className="forecast-period-title">未来3天</h4>
                <ForecastBlock fp={forecast.forecast_3d} />
              </div>
              {/* 未来7天 */}
              <div className="forecast-period">
                <h4 className="forecast-period-title">未来7天</h4>
                <ForecastBlock fp={forecast.forecast_7d} />
              </div>
              {/* 未来30天 */}
              <div className="forecast-period">
                <h4 className="forecast-period-title">未来30天</h4>
                <ForecastBlock fp={forecast.forecast_30d} />
              </div>
            </div>

            {/* LLM 情景解读 */}
            {(analysis?.forecast_summary_1d || analysis?.forecast_summary_3d || analysis?.forecast_summary_7d) && (
              <div className="forecast-llm-summary" style={{ marginTop: 12 }}>
                {analysis.forecast_summary_1d && (
                  <p className="forecast-llm-text">1天：{analysis.forecast_summary_1d}</p>
                )}
                {analysis.forecast_summary_3d && (
                  <p className="forecast-llm-text">3天：{analysis.forecast_summary_3d}</p>
                )}
                {analysis.forecast_summary_7d && (
                  <p className="forecast-llm-text">7天：{analysis.forecast_summary_7d}</p>
                )}
                {analysis.forecast_summary_30d && (
                  <p className="forecast-llm-text">30天：{analysis.forecast_summary_30d}</p>
                )}
              </div>
            )}
            {analysis?.forecast_risks && analysis.forecast_risks.length > 0 && (
              <div className="forecast-risk-notes" style={{ marginTop: 8 }}>
                {analysis.forecast_risks.map((r, i) => (
                  <span key={i} className="forecast-risk-tag">{r}</span>
                ))}
              </div>
            )}

            {/* 回测历史准确率 */}
            {forecast?.validation && forecast.validation.sample_size != null && forecast.validation.sample_size > 0 && (
              <div style={{ fontSize: 12, marginTop: 8 }}>
                <p style={{ color: forecast.validation.probability_quality === 'low' ? '#f59e0b' : '#9ca3af' }}>
                  回测 {forecast.validation.sample_size} 次 |
                  7d方向准确率 {forecast.validation.periods?.['7d']?.directional_accuracy ?? 'N/A'}% |
                  概率质量：{forecast.validation.probability_quality === 'high' ? '高' : forecast.validation.probability_quality === 'medium' ? '中' : '低'} |
                  校准：{forecast.validation.is_calibrated ? '是' : '否'}
                </p>
                {forecast.validation.probability_quality === 'low' && (
                  <p style={{ color: '#f59e0b', fontSize: 11, marginTop: 2, fontStyle: 'italic' }}>
                    回测未证明规则模型稳定优于基准模型，概率仅作低置信参考，历史回测不代表未来表现。
                  </p>
                )}
              </div>
            )}

            {/* 决策辅助区 */}
            {forecast?.decision_support && (
              <div style={{ marginTop: 14, padding: 12, background: '#f9fafb', borderRadius: 8 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
                  操作倾向：<span style={{
                    color: forecast.decision_support.action_bias === '偏积极' ? '#16a34a' :
                           forecast.decision_support.action_bias === '偏谨慎' ? '#f59e0b' :
                           forecast.decision_support.action_bias === '降低仓位风险' ? '#dc2626' : '#6b7280'
                  }}>{forecast.decision_support.action_bias || '观望'}</span>
                </div>
                {forecast.decision_support.buy_watch_conditions && forecast.decision_support.buy_watch_conditions.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 600 }}>买入/加仓关注条件</span>
                    <ul style={{ margin: '4px 0 0 16px', fontSize: 13, color: '#166534' }}>
                      {forecast.decision_support.buy_watch_conditions.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  </div>
                )}
                {forecast.decision_support.reduce_watch_conditions && forecast.decision_support.reduce_watch_conditions.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>减仓/止损警惕条件</span>
                    <ul style={{ margin: '4px 0 0 16px', fontSize: 13, color: '#991b1b' }}>
                      {forecast.decision_support.reduce_watch_conditions.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  </div>
                )}
                {forecast.decision_support.invalidation_signals && forecast.decision_support.invalidation_signals.length > 0 && (
                  <div style={{ fontSize: 12, color: '#f59e0b', marginTop: 4 }}>
                    判断失效信号：{forecast.decision_support.invalidation_signals.slice(0, 2).join('；')}
                  </div>
                )}
                {forecast.decision_support.model_quality_note && (
                  <p style={{ fontSize: 11, color: '#9ca3af', marginTop: 6, fontStyle: 'italic' }}>
                    {forecast.decision_support.model_quality_note}
                  </p>
                )}
                {forecast.decision_support.time_horizon_note && (
                  <p style={{ fontSize: 11, color: '#9ca3af', marginTop: 4, whiteSpace: 'pre-line' }}>
                    {forecast.decision_support.time_horizon_note}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* 子 Tab 切换 */}
        <div className="card section-card">
          <div className="section-tabs">
            <button className={`section-tab ${activeSection === 'indicators' ? 'active' : ''}`} onClick={() => setActiveSection('indicators')}>详细指标</button>
            <button className={`section-tab ${activeSection === 'risk' ? 'active' : ''}`} onClick={() => setActiveSection('risk')}>风险分析</button>
            <button className={`section-tab ${activeSection === 'profile' ? 'active' : ''}`} onClick={() => setActiveSection('profile')}>基金画像</button>
            <button className={`section-tab ${activeSection === 'macro' ? 'active' : ''}`} onClick={() => setActiveSection('macro')}>宏观因素</button>
            <button className={`section-tab ${activeSection === 'conditions' ? 'active' : ''}`} onClick={() => setActiveSection('conditions')}>操作参考</button>
          </div>

          {activeSection === 'indicators' && (
            <div className="tab-body">
              <h4>自然日口径（阶段涨跌）</h4>
              <div className="metric-grid metric-cols-3">
                <MetricItem label="近7个自然日涨跌" value={fmtVal(metrics.return_7d_calendar)} highlight />
                <MetricItem label="近30个自然日涨跌" value={fmtVal(metrics.return_30d_calendar)} />
                <MetricItem label="近90个自然日涨跌" value={fmtVal(metrics.return_90d_calendar)} />
                <MetricItem label="近7个自然日回撤" value={fmtVal(metrics.max_drawdown_7d_calendar)} />
                <MetricItem label="近30个自然日回撤" value={fmtVal(metrics.max_drawdown_30d_calendar)} />
                <MetricItem label="近90个自然日回撤" value={fmtVal(metrics.max_drawdown_90d_calendar)} />
              </div>
              <PeriodRange period={metrics.period_7d_calendar} />
              <PeriodRange period={metrics.period_30d_calendar} />
              <PeriodRange period={metrics.period_90d_calendar} />
              {metrics.return_30d_acc_nav != null && (
                <p className="acc-nav-note">累计净值口径：近30日 {fmtVal(metrics.return_30d_acc_nav)}，近90日 {fmtVal(metrics.return_90d_acc_nav)}</p>
              )}
              <p className="nav-note">阶段涨跌默认按单位净值计算，若基金期间分红，可能与部分平台的复权收益口径存在差异。</p>

              <h4 style={{ marginTop: 14 }}>交易日口径</h4>
              <div className="metric-grid metric-cols-3">
                <MetricItem label="近1个交易日涨跌" value={fmtVal(metrics.return_1trading)} highlight />
                <MetricItem label="近5个交易日涨跌" value={fmtVal(metrics.return_5trading)} />
                <MetricItem label="近10个交易日涨跌" value={fmtVal(metrics.return_10trading)} />
                <MetricItem label="近20个交易日涨跌" value={fmtVal(metrics.return_20trading)} />
                <MetricItem label="近60个交易日涨跌" value={fmtVal(metrics.return_60trading)} />
                <MetricItem label="近5交易日回撤" value={fmtVal(metrics.max_drawdown_5trading)} />
                <MetricItem label="近20交易日回撤" value={fmtVal(metrics.max_drawdown_20trading)} />
                <MetricItem label="近60交易日回撤" value={fmtVal(metrics.max_drawdown_60trading)} />
              </div>

              <h4 style={{ marginTop: 14 }}>波动与趋势</h4>
              <div className="metric-grid metric-cols-3">
                <MetricItem label="30日波动率" value={fmtVal(metrics.volatility_30d)} />
                <MetricItem label="60日波动率" value={fmtVal(metrics.volatility_60d)} />
                <MetricItem label="20日EWMA波动率" value={fmtVal(metrics.ewma_volatility_20d)} />
                <MetricItem label="30日波动分位" value={metrics.volatility_percentile_30d != null ? `${metrics.volatility_percentile_30d}% · ${metrics.volatility_regime_30d || '未知'}` : 'N/A'} />
                <MetricItem label="下行波动率(30d)" value={fmtVal(metrics.downside_volatility_30d)} />
                <MetricItem label="5日均线" value={fmtVal(metrics.ma_5, '')} />
                <MetricItem label="10日均线" value={fmtVal(metrics.ma_10, '')} />
                <MetricItem label="20日均线" value={fmtVal(metrics.ma_20, '')} />
                <MetricItem label="60日均线" value={fmtVal(metrics.ma_60, '')} />
                <MetricItem label="均线趋势" value={metrics.trend || 'N/A'} />
                <MetricItem label="7日区间位置" value={metrics.position_in_7d_range != null ? `${metrics.position_in_7d_range}%` : 'N/A'} />
                <MetricItem label="5日动能加速度" value={fmtVal(metrics.momentum_acceleration_5d)} />
                <MetricItem label="反弹强度(30d)" value={fmtVal(metrics.rebound_from_30d_low)} />
                <MetricItem label="回落幅度(30d)" value={fmtVal(metrics.pullback_from_30d_high)} />
                <MetricItem label="Calmar(60d)" value={fmtVal(metrics.calmar_60d, '')} />
                <MetricItem label="夏普比率(30d)" value={fmtVal(metrics.sharpe_30d, '')} />
                <MetricItem label="数据覆盖" value={`${metrics.data_days || 0}个交易日`} />
                <MetricItem label="数据区间" value={metrics.data_start && metrics.data_end ? `${metrics.data_start} ~ ${metrics.data_end}` : 'N/A'} />
              </div>
            </div>
          )}

          {activeSection === 'risk' && (
            <div className="tab-body">
              <h4>风险评分分解</h4>
              <div className="risk-scores-grid">
                <RiskScoreBar label="趋势评分" score={risk?.trend_score} />
                <RiskScoreBar label="回撤评分" score={risk?.drawdown_score} />
                <RiskScoreBar label="波动率评分" score={risk?.volatility_score} />
                <RiskScoreBar label="位置评分" score={risk?.position_score} />
                <RiskScoreBar label="宏观评分" score={risk?.macro_score} />
                {risk?.position_personal_score != null && (
                  <RiskScoreBar label="个人持仓评分" score={risk.position_personal_score} />
                )}
              </div>
              <p className="risk-desc">{analysis.risk_explanation}</p>

              {risk?.reasons && risk.reasons.length > 0 && (
                <div className="risk-sub">
                  <h4>评分依据</h4>
                  <ul className="simple-list">
                    {risk.reasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}

              {risk?.warnings && risk.warnings.length > 0 && (
                <div className="risk-sub">
                  <h4 style={{ color: '#dc2626' }}>风险警示</h4>
                  <ul className="warn-list">
                    {risk.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

              {/* 持仓分析 */}
              {analysis.position_advice && analysis.position_advice !== '未提供持仓信息，仅分析基金本身' && (
                <div className="position-box">
                  <h4>持仓分析</h4>
                  <p>{analysis.position_advice}</p>
                  {analysis.dca_suggestion && analysis.dca_suggestion !== '数据不足' && (
                    <p className="dca-tip">定投建议：{analysis.dca_suggestion}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {activeSection === 'profile' && (
            <div className="tab-body">
              {profile && (
                <div className="profile-grid">
                  {Object.entries(profile).filter(([k]) => k !== 'data_quality').map(([key, val]) => (
                    <div key={key} className="profile-item">
                      <span className="profile-label">{profileLabel(key)}</span>
                      <span className={`profile-value ${val === 'unavailable' ? 'unavailable' : ''}`}>
                        {val === 'unavailable' ? '不可用' : val === '未知' ? '未知' : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <p className="data-quality">数据完整度：{profile?.data_quality === 'good' ? '良好' : profile?.data_quality === 'partial' ? '部分' : '有限'}</p>
            </div>
          )}

          {activeSection === 'macro' && (
            <div className="tab-body">
              {macro && macro.status !== 'unavailable' ? (
                <>
                  <p className="macro-text">{macro.summary}</p>
                  {macro.global_indices && macro.global_indices.length > 0 && (
                    <div className="macro-grid">
                      {macro.global_indices.map((item, i) => (
                        <div key={i} className="macro-item">
                          <span className="macro-name">{item.name}</span>
                          <span className="macro-val">{item.status === 'unavailable' ? '不可用' : item.latest != null ? fmtNum(item.latest, 2) : 'N/A'}</span>
                          {item.change_pct != null && (
                            <span className={item.change_pct >= 0 ? 'macro-up' : 'macro-down'}>
                              {item.change_pct >= 0 ? '+' : ''}{item.change_pct.toFixed(2)}%
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {macro.forex && macro.forex.length > 0 && (
                    <div className="macro-grid" style={{ marginTop: 8 }}>
                      {macro.forex.map((item, i) => (
                        <div key={i} className="macro-item">
                          <span className="macro-name">{item.name}</span>
                          <span className="macro-val">{item.status === 'unavailable' ? '不可用' : item.latest != null ? fmtNum(item.latest, 4) : 'N/A'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="macro-unavailable">宏观数据暂不可用</p>
              )}
            </div>
          )}

          {activeSection === 'conditions' && (
            <div className="tab-body">
              <div className="conditions-grid-2">
                <div>
                  <h4 className="cond-title buy">买入/加仓关注条件</h4>
                  <ul className="cond-list">
                    {(analysis.buy_conditions || []).map((c, i) => <li key={i} className="cond-item buy-cond">{c}</li>)}
                  </ul>
                </div>
                <div>
                  <h4 className="cond-title sell">减仓/止损警惕条件</h4>
                  <ul className="cond-list">
                    {(analysis.reduce_conditions || []).map((c, i) => <li key={i} className="cond-item sell-cond">{c}</li>)}
                  </ul>
                </div>
              </div>
              {analysis.watch_points && analysis.watch_points.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <h4 className="cond-title" style={{ color: '#3b82f6' }}>持续观察点</h4>
                  <ul className="cond-list">
                    {analysis.watch_points.map((w, i) => <li key={i} className="cond-item watch-cond">{w}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 数据源状态 */}
        {result.datasource_status && (
          <div className="card ds-card">
            <h4>数据源状态</h4>
            <div className="ds-grid">
              {Object.entries(result.datasource_status).map(([key, val]) => (
                <div key={key} className={`ds-item ${val.available ? 'ds-ok' : 'ds-fail'}`}>
                  <span className="ds-name">{key}</span>
                  <span className="ds-status">{val.available ? '可用' : '不可用'}</span>
                  <span className="ds-detail">{val.detail}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 原始 JSON */}
        <div className="raw-section">
          <button className="raw-toggle" onClick={() => setShowRaw(!showRaw)}>
            {showRaw ? '收起原始数据 ▲' : '展开原始数据 ▼'}
          </button>
          {showRaw && (
            <div className="card raw-card">
              <pre className="raw-json">{JSON.stringify({ fund, fund_profile: profile, metrics, macro, risk, forecast, prediction, analysis, decision_advice, datasource_status: result.datasource_status }, null, 2)}</pre>
            </div>
          )}
        </div>

        {/* 免责声明 */}
        <div className="disclaimer">
          <p><strong>免责声明：</strong>{analysis.disclaimer || '本分析仅用于个人研究参考，不构成任何投资建议。基金投资有风险，过往业绩不预示未来表现。请在投资前充分了解产品风险特征，并根据自身风险承受能力做出决策。'}</p>
        </div>
      </div>
    )}

    {!result && !loading && !error && (
      <div className="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        <p>输入基金代码，获取基于数据的辅助分析</p>
        <p className="empty-hint">支持：短期走势 / 中期趋势 / 风险指标 / 基金画像 / 宏观参考 / 持仓分析</p>
        <p className="empty-hint">测试代码：161725（白酒LOF） 161128（标普科技QDII） 110022（易方达消费） 510300（沪深300ETF） 512800（银行ETF）</p>
      </div>
    )}
    </>
    </div>
  )
}
