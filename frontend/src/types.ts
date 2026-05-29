export interface FundInfo {
  code: string
  name: string
  type: string
  company: string
  source: string
}

export interface FundProfile {
  fund_type?: string
  fund_company?: string
  fund_manager?: string
  inception_date?: string
  fund_size?: string
  tracking_index?: string
  purchase_status?: string
  redeem_status?: string
  management_fee?: string
  custody_fee?: string
  sales_service_fee?: string
  risk_level?: string
  return_1y?: string
  peer_ranking?: string
  data_quality?: string
}

export interface PeriodDetail {
  start_date?: string
  end_date?: string
  start_nav?: number
  end_nav?: number
  days?: number
  nav_col?: string
}

export interface Metrics {
  error?: string
  data_days?: number
  data_start?: string
  data_end?: string
  latest_nav?: number
  // 自然日口径
  return_7d_calendar?: number | null
  return_30d_calendar?: number | null
  return_90d_calendar?: number | null
  period_7d_calendar?: PeriodDetail | null
  period_30d_calendar?: PeriodDetail | null
  period_90d_calendar?: PeriodDetail | null
  max_drawdown_7d_calendar?: number | null
  max_drawdown_30d_calendar?: number | null
  max_drawdown_90d_calendar?: number | null
  return_30d_acc_nav?: number | null
  return_90d_acc_nav?: number | null
  // 交易日口径
  return_1trading?: number | null
  return_5trading?: number | null
  return_10trading?: number | null
  return_20trading?: number | null
  return_60trading?: number | null
  max_drawdown_5trading?: number | null
  max_drawdown_20trading?: number | null
  max_drawdown_60trading?: number | null
  // 向后兼容字段
  return_7d?: number | null
  return_30d?: number | null
  return_60d?: number | null
  return_90d?: number | null
  max_drawdown_7d?: number | null
  max_drawdown_30d?: number | null
  max_drawdown_60d?: number | null
  max_drawdown_90d?: number | null
  volatility_30d?: number | null
  volatility_60d?: number | null
  volatility_90d?: number | null
  downside_volatility_30d?: number | null
  downside_volatility_60d?: number | null
  ma_5?: number | null
  ma_10?: number | null
  ma_20?: number | null
  ma_60?: number | null
  trend?: string | null
  position_in_7d_range?: number | null
  position_in_30d_range?: number | null
  position_in_60d_range?: number | null
  position_in_90d_range?: number | null
  rebound_from_30d_low?: number | null
  pullback_from_30d_high?: number | null
  momentum_acceleration_5d?: number | null
  ewma_volatility_20d?: number | null
  volatility_percentile_30d?: number | null
  volatility_regime_30d?: string | null
  current_estimate?: {
    estimated_nav?: number | null
    estimated_change_pct?: number | null
    estimate_time?: string
    scope?: string
  } | null
  calmar_60d?: number | null
  calmar_90d?: number | null
  consecutive_days?: { direction: string; days: number }
  daily_stats?: { mean: number; max: number; min: number; positive_days: number; negative_days: number }
  sharpe_30d?: number | null
  sharpe_60d?: number | null
  win_rate_30d?: number | null
  win_rate_60d?: number | null
  note_nav_delay?: string | null
}

export interface MacroItem {
  name?: string
  latest?: number | null
  change_pct?: number | null
  status?: string
  source?: string
  as_of?: string
}

export interface MacroSummary {
  risk_appetite?: string
  overseas_direction?: string
  forex_pressure?: string
  commodity_disturbance?: string
  text?: string
}

export interface Macro {
  status?: string
  summary?: string
  macro_summary?: MacroSummary
  risk_factors?: string[]
  global_indices?: MacroItem[]
  forex?: MacroItem[]
  commodities?: MacroItem[]
  interbank_rates?: MacroItem[]
  as_of?: string
}

export interface Risk {
  risk_score?: number
  risk_level?: string
  trend_score?: number
  drawdown_score?: number
  volatility_score?: number
  position_score?: number
  macro_score?: number
  position_personal_score?: number | null
  reasons?: string[]
  warnings?: string[]
}

export interface Analysis {
  conclusion?: string
  summary_7d?: string
  summary_30d?: string
  summary_90d?: string
  risk_explanation?: string
  position_advice?: string
  main_risks?: string[]
  watch_points?: string[]
  buy_conditions?: string[]
  reduce_conditions?: string[]
  dca_suggestion?: string
  confidence?: string
  data_basis?: string
  disclaimer?: string
  score_details?: string[]
  llm_error?: string
  note?: string
  forecast_summary_1d?: string
  forecast_summary_3d?: string
  forecast_summary_7d?: string
  forecast_summary_30d?: string
  forecast_risks?: string[]
}

export interface Validation {
  sample_size?: number
  probability_quality?: string
  is_calibrated?: boolean
  main_uncertainties?: string[]
  periods?: Record<string, {
    sample_size?: number
    directional_accuracy?: number
    brier_score?: number
    threshold_used?: number
    baseline_comparison?: {
      always_sideways_acc?: number
      simple_momentum_acc?: number
      rule_acc?: number
      best_baseline_acc?: number
      rule_vs_best_baseline_edge?: number
    }
    actual_distribution?: {
      up_pct?: number
      sideways_pct?: number
      down_pct?: number
    }
  }>
}

export interface DecisionSupport {
  action_bias?: string
  buy_watch_conditions?: string[]
  reduce_watch_conditions?: string[]
  invalidation_signals?: string[]
  position_hint?: string | null
  time_horizon_note?: string
  model_quality_note?: string
}

export interface ForecastPeriod {
  period_days?: number | null
  direction?: string
  rise_fall?: string
  up_probability?: number
  sideways_probability?: number
  down_probability?: number
  expected_return_range?: { low?: number | null; high?: number | null; unit?: string; note?: string }
  confidence?: string
  score?: number
  raw_score?: number
  estimate_used?: boolean
  estimate_note?: string | null
  reasons?: string[]
  up_triggers?: string[]
  down_triggers?: string[]
  model_basis?: string
  probability_quality?: string
  main_uncertainties?: string[]
}

export interface Forecast {
  forecast_1d?: ForecastPeriod
  forecast_3d?: ForecastPeriod
  forecast_7d?: ForecastPeriod
  forecast_30d?: ForecastPeriod
  disclaimer?: string
  validation?: Validation | null
  decision_support?: DecisionSupport
}

export interface DatasourceStatus {
  akshare?: { available: boolean; detail: string }
  efinance?: { available: boolean; detail: string }
  tencent?: { available: boolean; detail: string }
}

export interface AnalyzeResult {
  success: boolean
  code: string
  fund?: FundInfo
  fund_profile?: FundProfile
  metrics?: Metrics
  macro?: Macro
  risk?: Risk
  forecast?: Forecast
  analysis?: Analysis
  datasource_status?: DatasourceStatus
  error?: string
}

export interface PositionInput {
  cost_nav: string
  holding_amount: string
  holding_units: string
  is_dca: boolean
  monthly_dca_amount: string
  max_loss_percent: string
  holding_horizon: string
  risk_preference: string
}

export interface UserFundItem {
  code: string
  cost_nav?: number | null
  holding_amount?: number | null
  holding_units?: number | null
  is_dca?: boolean
  monthly_dca_amount?: number | null
  max_loss_percent?: number | null
  holding_horizon?: string
  risk_preference?: string
  note?: string
}

export interface BatchFundResult {
  code: string
  success: boolean
  error?: string | null
  fund?: FundInfo
  fund_profile?: FundProfile
  metrics?: Metrics
  macro?: Macro
  risk?: Risk
  forecast?: Forecast
  analysis?: Analysis
  datasource_status?: DatasourceStatus
}

export type TabKey = '7d' | '30d' | '90d'
export type SectionKey = 'indicators' | 'risk' | 'macro' | 'profile' | 'conditions' | 'raw'
