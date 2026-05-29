export function fmtVal(v: number | null | undefined, suffix = '%'): string {
  if (v === null || v === undefined) return 'N/A'
  if (suffix === '') return v.toFixed(4)
  return v.toFixed(2) + suffix
}

export function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined) return 'N/A'
  return v.toFixed(decimals)
}

export function conclusionColor(c: string | undefined): string {
  switch (c) {
    case '偏积极': return '#22c55e'
    case '中性': return '#6b7280'
    case '偏谨慎': return '#f59e0b'
    case '风险较高': return '#ef4444'
    case '数据不足': return '#9ca3af'
    default: return '#6b7280'
  }
}

export function riskColor(score: number): string {
  if (score <= 30) return '#22c55e'
  if (score <= 50) return '#eab308'
  if (score <= 70) return '#f97316'
  return '#ef4444'
}

export function profileLabel(key: string): string {
  const map: Record<string, string> = {
    fund_type: '基金类型', fund_company: '基金公司', fund_manager: '基金经理',
    inception_date: '成立日期', fund_size: '基金规模', tracking_index: '跟踪指数',
    purchase_status: '申购状态', redeem_status: '赎回状态', management_fee: '管理费率',
    custody_fee: '托管费率', sales_service_fee: '销售服务费', risk_level: '风险等级',
    return_1y: '近一年收益', peer_ranking: '同类排名',
  }
  return map[key] || key
}

export function riseFallColor(riseFall: string | undefined, direction: string | undefined): string {
  const label = riseFall || direction || ''
  if (label.includes('偏涨') || label.includes('偏上行')) return '#16a34a'
  if (label.includes('偏跌') || label.includes('偏下行')) return '#dc2626'
  if (label.includes('震荡')) return '#6b7280'
  if (label.includes('不确定')) return '#9ca3af'
  return '#6b7280'
}

export function probColor(up: number, down: number, which: 'up' | 'sideways' | 'down'): string {
  if (which === 'up') return '#16a34a'
  if (which === 'down') return '#dc2626'
  return '#6b7280'
}

export function directionLabel(dir: string | undefined): string {
  if (!dir) return '--'
  if (dir.includes('偏上') || dir.includes('偏涨') || dir === 'up') return '↑'
  if (dir.includes('偏下') || dir.includes('偏跌') || dir === 'down') return '↓'
  if (dir.includes('震荡') || dir === 'sideways') return '→'
  if (dir.includes('不确定')) return '不确定'
  return dir
}

export function directionColor(dir: string | undefined): string {
  if (!dir) return '#6b7280'
  if (dir.includes('偏上') || dir.includes('偏涨') || dir === 'up') return '#16a34a'
  if (dir.includes('偏下') || dir.includes('偏跌') || dir === 'down') return '#dc2626'
  return '#6b7280'
}

export function batchActionColor(bias: string | undefined): string {
  switch (bias) {
    case '偏积极': return '#16a34a'
    case '偏谨慎': return '#f59e0b'
    case '降低仓位风险': return '#dc2626'
    default: return '#6b7280'
  }
}
