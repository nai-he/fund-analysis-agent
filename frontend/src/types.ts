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

export interface PredictionPeriod {
  period_days?: number
  predicted_direction?: 'up' | 'down_or_flat' | 'uncertain' | string
  direction_label?: string
  up_probability?: number
  down_or_flat_probability?: number
  confidence?: string
  current_score?: number
  sample_size?: number
  historical_hit_rate?: number | null
  baseline_hit_rate?: number | null
  edge_vs_baseline?: number | null
  has_positive_edge?: boolean
  signal_probability?: number | null
  selective_threshold?: number | null
  selective_hit_rate?: number | null
  selective_signal_count?: number | null
  selective_coverage_pct?: number | null
  selective_edge_vs_baseline?: number | null
  current_passes_selective_threshold?: boolean
  selective_signal_valid?: boolean
  selective_target_hit_rate?: number | null
  selective_min_required_signals?: number | null
  selective_rule_text?: string | null
  selective_rule?: Record<string, number>
  selective_avg_return?: number | null
  selective_median_return?: number | null
  selective_worst_return?: number | null
  selective_profit_factor?: number | null
  selective_hit_rate_lower_bound?: number | null
  selective_train_hit_rate?: number | null
  selective_train_signal_count?: number | null
  selective_train_passed?: boolean
  selective_validation_hit_rate?: number | null
  selective_validation_signal_count?: number | null
  selective_validation_avg_return?: number | null
  selective_validation_passed?: boolean
  selective_cv_evaluable_folds?: number | null
  selective_cv_passed_folds?: number | null
  selective_cv_pass_rate?: number | null
  selective_cv_min_hit_rate?: number | null
  selective_cv_avg_return?: number | null
  selective_cv_passed?: boolean
  selective_training_status?: string | null
  brier_score?: number | null
  actual_up_rate?: number | null
  baseline_detail?: {
    majority_class_hit_rate?: number
    simple_momentum_hit_rate?: number
  }
  calibration_note?: string
  main_reasons?: string[]
  warning?: string | null
}

export interface PredictionResult {
  status?: string
  model_basis?: string
  quality?: string
  sample_size?: number
  usable_period_count?: number
  specific_training?: {
    enabled?: boolean
    fund_code?: string | null
    fund_name?: string | null
    target_hit_rate?: number | null
    min_edge?: number | null
    factor_status?: string
    factor_sources?: Array<{
      type?: string
      name?: string
      quarter?: string
      stock_count?: number
      holdings?: string[]
    }>
    factor_note?: string
    note?: string
  }
  summary?: string
  periods?: Record<string, PredictionPeriod>
  disclaimer?: string
}

export interface DatasourceStatus {
  akshare?: { available: boolean; detail: string }
  efinance?: { available: boolean; detail: string }
  tencent?: { available: boolean; detail: string }
}

export interface FinalDecision {
  headline?: string
  direction?: 'up' | 'down' | 'neutral' | 'uncertain'
  direction_label?: string
  action?: 'buy_watch' | 'hold' | 'reduce' | 'avoid' | 'observe'
  action_label?: string
  confidence?: string
  up_probability_7d?: number | null
  up_probability_30d?: number | null
  risk_score?: number | null
  why?: string[]
  watch?: string[]
  warning?: string[]
  disclaimer?: string
  summary?: string
}

export interface DecisionAdvice {
  action?: string
  action_label?: string
  confidence?: string
  suggested_buy_amount?: number | null
  suggested_buy_pct?: number | null
  position_hint?: string
  summary?: string
  reasons?: string[]
  risk_warnings?: string[]
  buy_conditions?: string[]
  sell_or_reduce_conditions?: string[]
  invalidation_signals?: string[]
  disclaimer?: string
}

export interface HighConfidenceDecision {
  action: 'wait' | 'avoid' | 'small_buy'
  action_label: string
  confidence: 'low' | 'medium' | 'high'
  score: number
  max_position_pct: number
  reasons: string[]
  blockers: string[]
  risk_controls: string[]
  disclaimer: string
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
  prediction?: PredictionResult
  analysis?: Analysis
  datasource_status?: DatasourceStatus
  decision_advice?: DecisionAdvice
  final_decision?: FinalDecision
  high_confidence_decision?: HighConfidenceDecision
  error?: string
}

export interface MacroResponse {
  success: boolean
  macro?: Macro | null
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
  planned_buy_amount: string
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
  prediction?: PredictionResult
  analysis?: Analysis
  datasource_status?: DatasourceStatus
  decision_advice?: DecisionAdvice
  final_decision?: FinalDecision
  high_confidence_decision?: HighConfidenceDecision
}

export type TabKey = '7d' | '30d' | '90d'
export type SectionKey = 'indicators' | 'risk' | 'macro' | 'profile' | 'conditions' | 'raw'
