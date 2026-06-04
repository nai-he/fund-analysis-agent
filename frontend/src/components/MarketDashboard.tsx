import { useState, useEffect } from 'react'
import type { Macro, MacroResponse } from '../types'
import { fmtNum } from '../utils/format'

export function MarketDashboard() {
  const [loading, setLoading] = useState(false)
  const [macro, setMacro] = useState<Macro | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchMacro = async () => {
    setLoading(true)
    setError(null)

    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), 15000)

    try {
      const resp = await fetch('/api/macro', { signal: controller.signal })
      const data: MacroResponse = await resp.json().catch(() => ({
        success: false,
        error: `请求失败 (${resp.status})`,
      }))

      if (!resp.ok || !data.success) {
        setError(data.error || `宏观数据获取失败 (${resp.status})`)
        setMacro(null)
        return
      }

      setMacro(data.macro || null)
      if (!data.macro || data.macro.status === 'unavailable') {
        setError('当前宏观数据源暂不可用')
      }
    } catch (e) {
      setError(
        e instanceof DOMException && e.name === 'AbortError'
          ? '宏观数据请求超时，请稍后重试'
          : `网络请求失败：${e instanceof Error ? e.message : '未知错误'}。请确认后端服务已启动。`
      )
      setMacro(null)
    } finally {
      window.clearTimeout(timer)
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMacro()
  }, [])

  const macroSummary = macro?.macro_summary
  const riskAppetiteLabel: Record<string, string> = { 'risk-on': '风险偏好上升', 'risk-off': '风险偏好下降', 'neutral': '中性' }
  const overseasLabel: Record<string, string> = { 'bullish': '偏强', 'bearish': '偏弱', 'mixed': '震荡' }
  const liquidityLabel: Record<string, string> = { 'tight': '偏紧', 'loose': '宽松', 'neutral': '中性', 'unknown': '未知' }

  return (
    <div className="market-dashboard">
      {/* 控制栏 */}
      <div className="market-controls">
        <div className="market-controls-row">
          <button className="market-refresh-btn" onClick={fetchMacro} disabled={loading}>
            {loading ? '加载中...' : '刷新宏观数据'}
          </button>
        </div>
        <p className="market-hint">点击刷新获取全球市场宏观数据概览（全球指数、汇率、商品、SHIBOR利率），无需指定基金代码</p>
      </div>

      {error && <div className="error-banner"><span className="error-icon">!</span><span>{error}</span></div>}

      {loading && (
        <div className="loading-area">
          <div className="spinner" />
          <p>正在获取宏观数据...</p>
        </div>
      )}

      {!loading && macro && macro.status !== 'unavailable' && (
        <div className="market-content">
          {/* 宏观摘要 */}
          <div className="card market-summary-card">
            <h3 className="market-section-title">宏观环境摘要</h3>
            <p className="market-summary-text">{macro.summary}</p>
            {macroSummary && (
              <div className="market-summary-tags">
                <span className={`market-tag tag-${macroSummary.risk_appetite || 'neutral'}`}>
                  风险偏好：{riskAppetiteLabel[macroSummary.risk_appetite || 'neutral'] || macroSummary.risk_appetite}
                </span>
                <span className={`market-tag tag-${macroSummary.overseas_direction || 'mixed'}`}>
                  海外市场：{overseasLabel[macroSummary.overseas_direction || 'mixed'] || macroSummary.overseas_direction}
                </span>
                <span className="market-tag tag-neutral">
                  汇率压力：{macroSummary.forex_pressure || '稳定'}
                </span>
                {(macroSummary as any).liquidity && (
                  <span className={`market-tag tag-${(macroSummary as any).liquidity || 'neutral'}`}>
                    流动性：{liquidityLabel[(macroSummary as any).liquidity] || (macroSummary as any).liquidity}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* 全球指数 */}
          {macro.global_indices && macro.global_indices.length > 0 && (
            <div className="card">
              <h3 className="market-section-title">全球主要指数</h3>
              <div className="market-index-grid">
                {macro.global_indices.map((item, i) => (
                  <div key={i} className={`market-index-item ${item.status === 'unavailable' ? 'unavailable' : ''}`}>
                    <div className="market-index-header">
                      <span className="market-index-name">{item.name}</span>
                      {item.source && item.source !== 'none' && <span className="market-index-source">{item.source}</span>}
                    </div>
                    {item.status === 'unavailable' ? (
                      <span className="market-index-na">数据不可用</span>
                    ) : (
                      <>
                        <span className="market-index-value">{item.latest != null ? fmtNum(item.latest, 2) : 'N/A'}</span>
                        {item.change_pct != null && (
                          <span className={`market-index-change ${item.change_pct >= 0 ? 'up' : 'down'}`}>
                            {item.change_pct >= 0 ? '+' : ''}{item.change_pct.toFixed(2)}%
                          </span>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 汇率 + 商品 */}
          <div className="market-two-col">
            {macro.forex && macro.forex.length > 0 && (
              <div className="card">
                <h3 className="market-section-title">汇率</h3>
                <div className="market-simple-list">
                  {macro.forex.map((item, i) => (
                    <div key={i} className="market-simple-row">
                      <span className="market-simple-name">{item.name}</span>
                      <span className="market-simple-value">
                        {item.status === 'unavailable' ? '不可用' : item.latest != null ? fmtNum(item.latest, 4) : 'N/A'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {macro.commodities && macro.commodities.length > 0 && (
              <div className="card">
                <h3 className="market-section-title">大宗商品</h3>
                <div className="market-simple-list">
                  {macro.commodities.map((item, i) => (
                    <div key={i} className="market-simple-row">
                      <span className="market-simple-name">{item.name}</span>
                      <span className="market-simple-value">
                        {item.status === 'unavailable' ? '不可用' : item.latest != null ? String(item.latest) : 'N/A'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* SHIBOR银行间利率 */}
          {(macro as any).interbank_rates && (macro as any).interbank_rates.length > 0 && (
            <div className="card">
              <h3 className="market-section-title">银行间利率（SHIBOR）</h3>
              <div className="market-simple-list">
                {(macro as any).interbank_rates.map((item: any, i: number) => (
                  <div key={i} className="market-simple-row">
                    <span className="market-simple-name">{item.name}</span>
                    <span className="market-simple-value">
                      {item.status === 'unavailable' ? '不可用' : item.latest != null ? `${item.latest}%` : 'N/A'}
                    </span>
                    {item.change != null && (
                      <span className={`market-index-change ${item.change >= 0 ? 'up' : 'down'}`}>
                        {item.change >= 0 ? '+' : ''}{item.change}bp
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 风险因素 */}
          {macro.risk_factors && macro.risk_factors.length > 0 && (
            <div className="card">
              <h3 className="market-section-title">当前宏观风险因素</h3>
              <ul className="market-risk-list">
                {macro.risk_factors.map((rf, i) => (
                  <li key={i} className="market-risk-item">{rf}</li>
                ))}
              </ul>
            </div>
          )}

          {macro.as_of && (
            <p className="market-as-of">数据截至：{macro.as_of}</p>
          )}
        </div>
      )}

      {!loading && !error && !macro && (
        <div className="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
          <p>点击"刷新宏观数据"查看全球市场宏观数据概览</p>
          <p className="empty-hint">包括：全球指数、汇率、大宗商品、SHIBOR利率、宏观风险因素</p>
        </div>
      )}
    </div>
  )
}
