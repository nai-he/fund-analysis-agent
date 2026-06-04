"""Binary up/down-or-flat probability engine with walk-forward validation.

This module is intentionally dependency-light. It does not try to promise high
accuracy. It produces a current "will it go up" probability only after checking
how the same signal behaved on historical walk-forward samples, then compares it
with simple baselines.
"""
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scoring import compute_indicators_from_nav, score_from_indicators

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = [1, 3, 7, 30]
MIN_REQUIRED_DAYS = 55
HIGH_WIN_MIN_SIGNALS = 20
HIGH_WIN_TARGET_HIT_RATE = 60.0
HIGH_WIN_MIN_EDGE = 3.0
HIGH_WIN_DEFAULT_THRESHOLDS = {1: 0.60, 3: 0.59, 7: 0.62, 30: 0.64}
SPECIFIC_TRAINED_FUND_CODES = {
    "015916",  # 永赢医药创新智选混合发起C
    "015790",  # 永赢高端装备智选混合发起C
    "161226",  # 国投瑞银白银期货(LOF)A
    "014331",  # 华泰柏瑞中证稀土产业ETF发起式联接A
    "015566",  # 万家精选混合C
    "012868",  # 易方达标普信息科技指数(QDII-LOF)C
    "161128",  # 易方达标普信息科技指数(QDII-LOF)A
    "020872",  # 华夏创业板指数发起式E
    "017811",  # 东方人工智能主题混合C
    "017516",  # 易方达北证50成份指数C
}
SPECIFIC_TARGET_HIT_RATE = 80.0
SPECIFIC_MIN_EDGE = 5.0
SPECIFIC_MIN_SIGNALS_BY_HORIZON = {1: 24, 3: 20, 7: 16, 30: 10}
SPECIFIC_MIN_VALIDATION_SIGNALS_BY_HORIZON = {1: 6, 3: 5, 7: 4, 30: 3}
SPECIFIC_VALIDATION_FRACTION = 0.30
SPECIFIC_MIN_PROFIT_FACTOR = 1.05
SPECIFIC_CV_FOLDS = 4
SPECIFIC_MIN_CV_EVALUABLE_FOLDS = 2
SPECIFIC_MIN_CV_PASS_RATE = 50.0
SPECIFIC_MIN_HIT_RATE_LOWER_BOUND = 55.0
EXTERNAL_FACTOR_FEATURES = {
    "factor_return_1d",
    "factor_return_5d",
    "factor_return_20d",
    "factor_position_30d",
    "factor_above_ma20",
    "factor_volatility_20d",
}


def is_specific_trained_fund(fund_code: str) -> bool:
    """Return True for the user-provided funds that use the dedicated trainer."""
    return str(fund_code or "").strip() in SPECIFIC_TRAINED_FUND_CODES


def generate_up_probability_prediction(
    nav_df: pd.DataFrame,
    horizons: Optional[List[int]] = None,
    min_samples: int = 20,
    fund_code: str = "",
    fund_name: str = "",
    external_features: Optional[pd.DataFrame] = None,
    external_factor_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate binary up probability for 1/3/7/30 trading-day horizons."""
    horizons = horizons or DEFAULT_HORIZONS
    specific_training = is_specific_trained_fund(fund_code)
    df = _prepare_nav_df(nav_df)
    if df is None or len(df) < MIN_REQUIRED_DAYS:
        return {
            "status": "unavailable",
            "sample_size": 0 if df is None else len(df),
            "model_basis": "walk_forward_binary_rule_ensemble",
            "specific_training": _specific_training_meta(
                fund_code,
                fund_name,
                specific_training,
                external_factor_meta=external_factor_meta,
                external_features=None,
            ),
            "summary": "历史净值样本不足，暂不能生成可验证的上涨概率。",
            "periods": {},
            "disclaimer": "仅供个人研究参考，不构成投资建议。历史回测不代表未来表现。",
        }

    external_features_df = _prepare_external_features(external_features, df) if specific_training else None

    periods: Dict[str, Any] = {}
    usable_count = 0
    total_samples = 0

    for horizon in horizons:
        period = _predict_horizon(
            df,
            horizon,
            min_samples=min_samples,
            specific_training=specific_training,
            external_features=external_features_df,
        )
        periods[f"{horizon}d"] = period
        total_samples += int(period.get("sample_size") or 0)
        if period.get("current_passes_selective_threshold") and period.get("confidence") != "低":
            usable_count += 1

    if specific_training and usable_count == 0:
        quality = "low"
        summary = "专属基金训练已启用，但当前未触发80%目标胜率强信号，默认等待。"
    elif specific_training and usable_count >= 2:
        quality = "high"
        summary = "专属基金训练触发80%目标胜率强信号，可作为重点辅助信号，但仍需小额分批和风控。"
    elif specific_training:
        quality = "medium"
        summary = "专属基金训练有少数周期触发80%目标胜率强信号，适合谨慎参考。"
    elif usable_count == 0:
        quality = "low"
        summary = "当前没有触发高胜率精筛信号，默认等待，不把弱概率当买入依据。"
    elif usable_count >= 3:
        quality = "high"
        summary = "多个周期触发高胜率精筛信号，可作为更强辅助信号，但仍需仓位控制。"
    else:
        quality = "medium"
        summary = "少数周期触发高胜率精筛信号，可小心参考，未触发周期继续等待。"

    if specific_training and external_features_df is not None and not external_features_df.empty:
        summary += " 已纳入重仓股/行业代理因子做辅助回测。"

    return {
        "status": "ok",
        "model_basis": "specific_fund_walk_forward_80_target" if specific_training else "walk_forward_binary_rule_ensemble",
        "quality": quality,
        "sample_size": total_samples,
        "usable_period_count": usable_count,
        "specific_training": _specific_training_meta(
            fund_code,
            fund_name,
            specific_training,
            external_factor_meta=external_factor_meta,
            external_features=external_features_df,
        ),
        "summary": summary,
        "periods": periods,
        "disclaimer": "仅供个人研究参考，不构成投资建议。历史回测不代表未来表现。",
    }


def _prepare_nav_df(nav_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if nav_df is None or nav_df.empty or "单位净值" not in nav_df.columns:
        return None
    df = nav_df.copy()
    if "净值日期" in df.columns:
        df["净值日期"] = pd.to_datetime(df["净值日期"], errors="coerce")
        df = df.dropna(subset=["净值日期"])
        df = df.sort_values("净值日期", ascending=True)
    df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
    df = df.dropna(subset=["单位净值"])
    df = df[df["单位净值"] > 0]
    return df.reset_index(drop=True)


def _prepare_external_features(
    external_features: Optional[pd.DataFrame],
    nav_df: pd.DataFrame,
) -> Optional[pd.DataFrame]:
    """Align optional stock/sector proxy features to the fund NAV calendar."""
    if external_features is None or external_features.empty or nav_df is None or nav_df.empty:
        return None

    try:
        features = external_features.copy()
        attrs = dict(getattr(external_features, "attrs", {}) or {})
        if "净值日期" in features.columns and "净值日期" in nav_df.columns:
            features["净值日期"] = pd.to_datetime(features["净值日期"], errors="coerce")
            features = features.dropna(subset=["净值日期"]).sort_values("净值日期")
            feature_cols = [c for c in features.columns if c != "净值日期"]
            for col in feature_cols:
                features[col] = pd.to_numeric(features[col], errors="coerce")
            feature_cols = [c for c in feature_cols if features[c].notna().any()]
            if not feature_cols:
                return None

            nav_dates = nav_df[["净值日期"]].copy()
            nav_dates["净值日期"] = pd.to_datetime(nav_dates["净值日期"], errors="coerce")
            aligned = pd.merge_asof(
                nav_dates.sort_values("净值日期"),
                features[["净值日期", *feature_cols]],
                on="净值日期",
                direction="backward",
            )
            aligned = aligned[feature_cols].ffill()
            aligned.attrs.update(attrs)
            return aligned.reset_index(drop=True)

        feature_cols = [c for c in features.columns if c != "净值日期"]
        for col in feature_cols:
            features[col] = pd.to_numeric(features[col], errors="coerce")
        feature_cols = [c for c in feature_cols if features[c].notna().any()]
        if not feature_cols:
            return None
        aligned = features[feature_cols].reset_index(drop=True).reindex(range(len(nav_df))).ffill()
        aligned.attrs.update(attrs)
        return aligned
    except Exception as exc:
        logger.warning(f"外部因子对齐失败: {exc}")
        return None


def _external_feature_at(external_features: Optional[pd.DataFrame], index: int) -> Dict[str, float]:
    if external_features is None or external_features.empty or index < 0 or index >= len(external_features):
        return {}
    row = external_features.iloc[index]
    result: Dict[str, float] = {}
    for key in EXTERNAL_FACTOR_FEATURES:
        if key in row:
            value = _safe_float(row.get(key), math.nan)
            if math.isfinite(value):
                result[key] = value
    return result


def _with_external_features(features: Dict[str, Any], external_row: Dict[str, float]) -> Dict[str, Any]:
    if not external_row:
        return features
    merged = dict(features)
    for key, value in external_row.items():
        if key in EXTERNAL_FACTOR_FEATURES and math.isfinite(float(value)):
            merged[key] = float(value)
    return merged


def _predict_horizon(
    df: pd.DataFrame,
    horizon: int,
    min_samples: int,
    specific_training: bool = False,
    external_features: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    navs = df["单位净值"].astype(float).values
    current_score, current_raw_prob, current_reasons = _score_probability(navs, horizon)
    current_external = _external_feature_at(external_features, len(df) - 1)
    current_features = _with_external_features(
        _current_feature_snapshot(navs, current_score),
        current_external,
    )
    current_training_features = _with_external_features(
        _training_feature_snapshot(
            navs,
            horizon,
            current_score,
            current_raw_prob,
            _period_return(navs, horizon),
        ),
        current_external,
    )

    samples = _walk_forward_samples(df, horizon, external_features=external_features)
    n = len(samples)
    if n < min_samples:
        return _empty_period(horizon, current_raw_prob, current_score, current_features, n)

    probabilities = [s["probability"] for s in samples]
    actuals = [s["actual_up"] for s in samples]
    momentum_preds = [s["momentum_up"] for s in samples]

    calibrated_prob, calibration_note = _calibrate_probability(current_raw_prob, samples)
    selective = _selective_up_signal_stats(
        samples,
        horizon,
        current_raw_prob,
        specific_training=specific_training,
        current_features=current_training_features,
    )
    binary_preds = [p >= 0.5 for p in probabilities]
    model_hit_rate = _hit_rate(binary_preds, actuals)
    majority_up = sum(actuals) >= (len(actuals) / 2)
    majority_hit_rate = _hit_rate([majority_up] * n, actuals)
    momentum_hit_rate = _hit_rate(momentum_preds, actuals)
    baseline_hit_rate = max(majority_hit_rate, momentum_hit_rate)
    edge = round(model_hit_rate - baseline_hit_rate, 2)
    brier = round(float(np.mean([(p - (1.0 if y else 0.0)) ** 2 for p, y in zip(probabilities, actuals)])), 4)

    up_probability = round(calibrated_prob * 100, 1)
    down_or_flat_probability = round(100 - up_probability, 1)
    confidence = _confidence(n, edge, brier, calibrated_prob, selective)
    predicted_direction = _direction_from_probability(calibrated_prob, edge, confidence, selective)
    has_positive_edge = edge > 0 or bool(selective.get("has_positive_edge"))

    return {
        "period_days": horizon,
        "predicted_direction": predicted_direction,
        "direction_label": _direction_label(predicted_direction),
        "up_probability": up_probability,
        "down_or_flat_probability": down_or_flat_probability,
        "confidence": confidence,
        "current_score": round(current_score, 2),
        "sample_size": n,
        "historical_hit_rate": model_hit_rate,
        "baseline_hit_rate": round(baseline_hit_rate, 2),
        "edge_vs_baseline": edge,
        "has_positive_edge": has_positive_edge,
        "signal_probability": round(current_raw_prob * 100, 1),
        "selective_threshold": selective.get("threshold_pct"),
        "selective_hit_rate": selective.get("hit_rate"),
        "selective_signal_count": selective.get("signal_count"),
        "selective_coverage_pct": selective.get("coverage_pct"),
        "selective_edge_vs_baseline": selective.get("edge_vs_baseline"),
        "current_passes_selective_threshold": selective.get("current_passes_threshold"),
        "selective_signal_valid": selective.get("is_valid"),
        "selective_target_hit_rate": selective.get("target_hit_rate"),
        "selective_min_required_signals": selective.get("min_required_signals"),
        "selective_rule_text": selective.get("rule_text"),
        "selective_rule": selective.get("rule"),
        "selective_avg_return": selective.get("avg_return"),
        "selective_median_return": selective.get("median_return"),
        "selective_worst_return": selective.get("worst_return"),
        "selective_profit_factor": selective.get("profit_factor"),
        "selective_hit_rate_lower_bound": selective.get("hit_rate_lower_bound"),
        "selective_train_hit_rate": selective.get("train_hit_rate"),
        "selective_train_signal_count": selective.get("train_signal_count"),
        "selective_train_passed": selective.get("train_passed"),
        "selective_validation_hit_rate": selective.get("validation_hit_rate"),
        "selective_validation_signal_count": selective.get("validation_signal_count"),
        "selective_validation_avg_return": selective.get("validation_avg_return"),
        "selective_validation_passed": selective.get("validation_passed"),
        "selective_cv_evaluable_folds": selective.get("cv_evaluable_folds"),
        "selective_cv_passed_folds": selective.get("cv_passed_folds"),
        "selective_cv_pass_rate": selective.get("cv_pass_rate"),
        "selective_cv_min_hit_rate": selective.get("cv_min_hit_rate"),
        "selective_cv_avg_return": selective.get("cv_avg_return"),
        "selective_cv_passed": selective.get("cv_passed"),
        "selective_training_status": selective.get("training_status"),
        "brier_score": brier,
        "actual_up_rate": round(sum(actuals) / n * 100, 1),
        "baseline_detail": {
            "majority_class_hit_rate": round(majority_hit_rate, 2),
            "simple_momentum_hit_rate": round(momentum_hit_rate, 2),
        },
        "calibration_note": calibration_note,
        "main_reasons": _main_reasons(current_features, current_reasons, edge, confidence, selective),
        "feature_snapshot": current_features,
        "warning": _warning(edge, confidence, selective),
    }


def _walk_forward_samples(
    df: pd.DataFrame,
    horizon: int,
    external_features: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    navs = df["单位净值"].astype(float).values
    lookback = min(90, max(40, len(df) // 2))
    samples: List[Dict[str, Any]] = []
    if len(navs) <= lookback + horizon:
        return samples

    for i in range(lookback, len(navs) - horizon):
        hist = navs[i - lookback:i]
        start_nav = hist[-1]
        future_nav = navs[i + horizon]
        if start_nav <= 0 or future_nav <= 0:
            continue
        score, probability, _reasons = _score_probability(hist, horizon)
        future_return = (future_nav / start_nav - 1.0) * 100
        prev_return = _period_return(hist, horizon)
        features = _with_external_features(
            _training_feature_snapshot(hist, horizon, score, probability, prev_return),
            _external_feature_at(external_features, i - 1),
        )
        samples.append({
            "score": score,
            "probability": probability,
            "actual_up": bool(future_return > 0),
            "future_return": future_return,
            "momentum_up": bool(prev_return > 0),
            "features": features,
        })
    return samples


def _score_probability(navs: np.ndarray, horizon: int) -> Tuple[float, float, List[str]]:
    indicators = compute_indicators_from_nav(navs)
    if indicators.get("error"):
        return 0.0, 0.5, ["数据不足"]

    score, reasons, _up, _down = score_from_indicators(indicators, horizon)
    score = _adjust_score_with_binary_features(score, indicators, horizon)

    rule_prob = _sigmoid(score / 32.0)
    momentum_prob = _momentum_probability(navs, horizon)
    mean_reversion_prob = _mean_reversion_probability(indicators)

    # 调整权重：降低动量，增加均值回归
    # 原权重: 62% 动量 + 28% 动量 + 10% 均值回归 = 90% 动量
    # 新权重: 45% 规则 + 25% 动量 + 30% 均值回归
    probability = 0.45 * rule_prob + 0.25 * momentum_prob + 0.30 * mean_reversion_prob
    probability = _shrink_probability(probability, len(navs))
    return score, min(0.9, max(0.1, probability)), list(reasons or [])[:4]


def _adjust_score_with_binary_features(score: float, indicators: Dict[str, Any], horizon: int) -> float:
    """增强反转信号，防止追高追低"""
    rsi14 = _safe_float(indicators.get("rsi_14"), 50)
    vol = _safe_float(indicators.get("volatility_30d"), 0)
    ret1 = _safe_float(indicators.get("return_1trading"), 0)
    ret5 = _safe_float(indicators.get("return_5trading"), 0)
    ret30 = _safe_float(indicators.get("return_30d"), 0)
    pos30 = _safe_float(indicators.get("position_in_30d_range"), 50)
    pos60 = _safe_float(indicators.get("position_in_60d_range"), 50)
    macd = indicators.get("macd") or {}
    bollinger = indicators.get("bollinger") or {}
    bb_pos = _safe_float(bollinger.get("position_pct"), 50)

    # 短期动量（仅对1-3天预测有效）
    if horizon <= 3:
        if ret1 > 0 and ret5 > 0:
            # 连续上涨但已高位 → 降低加分
            if pos30 > 75 or rsi14 > 65:
                score += 1  # 大幅降低
            else:
                score += 4
        elif ret1 < 0 and ret5 < 0:
            # 连续下跌但已低位 → 降低扣分
            if pos30 < 25 or rsi14 < 35:
                score -= 1  # 反弹机会
            else:
                score -= 4

    # RSI 超买超卖（增强反转信号）
    if rsi14 >= 75:
        score -= 12  # 强烈超买，大幅降低评分
    elif rsi14 >= 65:
        score -= 6   # 超买预警
    elif rsi14 <= 25:
        score += 10  # 强烈超卖，反弹机会
    elif rsi14 <= 35:
        score += 5   # 超卖区域

    # 布林带位置
    if bb_pos >= 95:
        score -= 8  # 触及上轨，回调风险
    elif bb_pos >= 85:
        score -= 4
    elif bb_pos <= 5:
        score += 8  # 触及下轨，反弹机会
    elif bb_pos <= 15:
        score += 4

    # 区间位置 + 波动率（防追高）
    if pos30 >= 85 and ret30 > 10:
        score -= 8  # 高位且已大涨，追高风险
    elif pos30 >= 80 and vol >= 25:
        score -= 5  # 高位高波动
    elif pos30 <= 15 and ret30 < -10:
        score += 6  # 低位且已大跌，反弹机会
    elif pos30 <= 20 and vol < 35:
        score += 3  # 低位低波动

    # MACD 信号
    if macd.get("crossover") == "golden":
        score += 5 if horizon <= 7 else 3
    elif macd.get("crossover") == "dead":
        score -= 5 if horizon <= 7 else 3

    # 高波动惩罚
    if vol >= 40:
        score *= 0.75  # 高波动降低可信度
    elif vol >= 30:
        score *= 0.90

    return float(score)


def _momentum_probability(navs: np.ndarray, horizon: int) -> float:
    ret = _period_return(navs, horizon)
    returns = np.diff(navs) / navs[:-1]
    vol = float(np.std(returns[-30:])) if len(returns) >= 5 else 0.01
    if not math.isfinite(vol) or vol <= 0:
        vol = 0.01
    scaled = ret / max(vol * math.sqrt(max(horizon, 1)) * 100, 0.35)
    return _sigmoid(scaled * 0.9)


def _training_feature_snapshot(
    navs: np.ndarray,
    horizon: int,
    score: float,
    probability: float,
    prev_return: float,
) -> Dict[str, float]:
    indicators = compute_indicators_from_nav(navs)
    bollinger = indicators.get("bollinger") or {}
    return {
        "prob": float(probability),
        "probability": float(probability),
        "score": float(score),
        "rsi_14": _safe_float(indicators.get("rsi_14"), 50),
        "bb_position": _safe_float(bollinger.get("position_pct"), 50),
        "position_30d": _safe_float(indicators.get("position_in_30d_range"), 50),
        "position_60d": _safe_float(indicators.get("position_in_60d_range"), 50),
        "return_1d": _safe_float(indicators.get("return_1trading"), 0),
        "return_5d": _safe_float(indicators.get("return_5trading"), 0),
        "return_20d": _safe_float(indicators.get("return_20trading"), 0),
        "return_30d": _safe_float(indicators.get("return_30d"), 0),
        "prev_return": float(prev_return),
        "horizon": float(horizon),
    }


def _mean_reversion_probability(indicators: Dict[str, Any]) -> float:
    """增强均值回归信号，捕捉超买超卖反转"""
    rsi14 = _safe_float(indicators.get("rsi_14"), 50)
    bollinger = indicators.get("bollinger") or {}
    bb_pos = _safe_float(bollinger.get("position_pct"), 50)
    pos30 = _safe_float(indicators.get("position_in_30d_range"), 50)
    ret30 = _safe_float(indicators.get("return_30d"), 0)

    p = 0.5

    # RSI 超买超卖（增强权重）
    if rsi14 <= 25:
        p += 0.20  # 强烈超卖，大幅提高反弹概率
    elif rsi14 <= 30:
        p += 0.15
    elif rsi14 <= 35:
        p += 0.10
    elif rsi14 >= 75:
        p -= 0.20  # 强烈超买，大幅降低上涨概率
    elif rsi14 >= 70:
        p -= 0.15
    elif rsi14 >= 65:
        p -= 0.10

    # 布林带位置（增强权重）
    if bb_pos <= 5:
        p += 0.12  # 触及下轨
    elif bb_pos <= 10:
        p += 0.08
    elif bb_pos >= 95:
        p -= 0.12  # 触及上轨
    elif bb_pos >= 90:
        p -= 0.08

    # 区间位置 + 收益率（综合判断）
    if pos30 <= 15 and ret30 < -10:
        p += 0.10  # 低位且已大跌，强反弹信号
    elif pos30 <= 20:
        p += 0.05
    elif pos30 >= 85 and ret30 > 10:
        p -= 0.10  # 高位且已大涨，回调风险
    elif pos30 >= 80:
        p -= 0.05

    return min(0.80, max(0.20, p))


def _calibrate_probability(current_prob: float, samples: List[Dict[str, Any]]) -> Tuple[float, str]:
    if not samples:
        return current_prob, "样本不足，使用未校准概率。"

    probs = np.array([s["probability"] for s in samples], dtype=float)
    actuals = np.array([1.0 if s["actual_up"] else 0.0 for s in samples], dtype=float)
    base_rate = float(np.mean(actuals))

    near_mask = np.abs(probs - current_prob) <= 0.08
    near_count = int(np.sum(near_mask))
    if near_count >= 12:
        observed = float(np.mean(actuals[near_mask]))
        calibrated = (observed * near_count + base_rate * 8) / (near_count + 8)
        return float(0.65 * calibrated + 0.35 * current_prob), f"按相近概率区间校准，区间样本 {near_count} 次。"

    # Distance-weighted fallback; still uses only historical samples.
    weights = 1.0 / (np.abs(probs - current_prob) + 0.05)
    observed = float(np.sum(weights * actuals) / np.sum(weights))
    calibrated = 0.50 * observed + 0.30 * current_prob + 0.20 * base_rate
    return float(calibrated), "相近样本偏少，使用距离加权校准。"


def _selective_up_signal_stats(
    samples: List[Dict[str, Any]],
    horizon: int,
    current_prob: float,
    specific_training: bool = False,
    current_features: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Evaluate a sparse, high-hit-rate up-only signal instead of trading every day."""
    if not samples:
        return _empty_selective_stats(current_prob, horizon, "样本不足，无法验证高胜率信号")

    probs = np.array([s["probability"] for s in samples], dtype=float)
    actuals = np.array([1.0 if s["actual_up"] else 0.0 for s in samples], dtype=float)
    momentum = np.array([1.0 if s["momentum_up"] else 0.0 for s in samples], dtype=float)

    overall_up_rate = float(np.mean(actuals) * 100)
    momentum_hit = float(np.mean(momentum == actuals) * 100)
    baseline = max(overall_up_rate, momentum_hit)

    min_signals = SPECIFIC_MIN_SIGNALS_BY_HORIZON.get(horizon, HIGH_WIN_MIN_SIGNALS) if specific_training else HIGH_WIN_MIN_SIGNALS
    target_hit_rate = SPECIFIC_TARGET_HIT_RATE if specific_training else HIGH_WIN_TARGET_HIT_RATE
    min_edge = SPECIFIC_MIN_EDGE if specific_training else HIGH_WIN_MIN_EDGE

    if specific_training:
        best = _search_specific_signal(
            samples,
            actuals,
            baseline,
            horizon,
            min_signals,
            target_hit_rate,
            min_edge,
            current_features or {},
        )
    else:
        best = None
        for threshold in np.arange(0.55, 0.751, 0.01):
            mask = probs >= threshold
            signal_count = int(np.sum(mask))
            if signal_count < min_signals:
                continue
            hit_rate = float(np.mean(actuals[mask]) * 100)
            edge_vs_baseline = hit_rate - baseline
            passes = hit_rate >= target_hit_rate and edge_vs_baseline >= min_edge
            candidate = {
                "threshold": float(threshold),
                "hit_rate": hit_rate,
                "signal_count": signal_count,
                "coverage_pct": signal_count / len(samples) * 100,
                "baseline_hit_rate": baseline,
                "edge_vs_baseline": edge_vs_baseline,
                "is_valid": passes,
                "rule": {"prob_min": float(threshold)},
                "rule_text": f"上涨信号概率 >= {threshold * 100:.0f}%",
                "avg_return": None,
                "median_return": None,
                "worst_return": None,
                "profit_factor": None,
                "hit_rate_lower_bound": None,
                "train_hit_rate": None,
                "train_signal_count": 0,
                "train_passed": False,
                "validation_hit_rate": None,
                "validation_signal_count": 0,
                "validation_avg_return": None,
                "validation_passed": False,
                "cv_evaluable_folds": 0,
                "cv_passed_folds": 0,
                "cv_pass_rate": None,
                "cv_min_hit_rate": None,
                "cv_avg_return": None,
                "cv_passed": False,
                "training_status": "general_threshold",
            }
            if passes:
                if (
                    best is None
                    or candidate["hit_rate"] > best["hit_rate"]
                    or (
                        abs(candidate["hit_rate"] - best["hit_rate"]) < 1e-9
                        and candidate["signal_count"] > best["signal_count"]
                    )
                ):
                    best = candidate

    if best is None:
        threshold = HIGH_WIN_DEFAULT_THRESHOLDS.get(horizon, 0.62)
        mask = probs >= threshold
        signal_count = int(np.sum(mask))
        hit_rate = float(np.mean(actuals[mask]) * 100) if signal_count else None
        edge_vs_baseline = hit_rate - baseline if hit_rate is not None else None
        best = {
            "threshold": threshold,
            "hit_rate": hit_rate,
            "signal_count": signal_count,
            "coverage_pct": signal_count / len(samples) * 100 if samples else 0.0,
            "baseline_hit_rate": baseline,
            "edge_vs_baseline": edge_vs_baseline,
            "is_valid": False,
            "rule": {"prob_min": float(threshold)},
            "rule_text": f"上涨信号概率 >= {threshold * 100:.0f}%",
            "avg_return": None,
            "median_return": None,
            "worst_return": None,
            "profit_factor": None,
            "hit_rate_lower_bound": None,
            "train_hit_rate": None,
            "train_signal_count": 0,
            "train_passed": False,
            "validation_hit_rate": None,
            "validation_signal_count": 0,
            "validation_avg_return": None,
            "validation_passed": False,
            "cv_evaluable_folds": 0,
            "cv_passed_folds": 0,
            "cv_pass_rate": None,
            "cv_min_hit_rate": None,
            "cv_avg_return": None,
            "cv_passed": False,
            "training_status": "fallback_default",
        }

    if specific_training:
        current_passes = bool(best["is_valid"] and _features_pass_rule(current_features or {}, best.get("rule") or {}))
    else:
        current_passes = bool(best["is_valid"] and current_prob >= best["threshold"])
    return {
        "threshold": round(best["threshold"], 4),
        "threshold_pct": round(best["threshold"] * 100, 1),
        "hit_rate": round(best["hit_rate"], 2) if best["hit_rate"] is not None else None,
        "signal_count": int(best["signal_count"]),
        "coverage_pct": round(best["coverage_pct"], 2),
        "baseline_hit_rate": round(best["baseline_hit_rate"], 2),
        "edge_vs_baseline": round(best["edge_vs_baseline"], 2) if best["edge_vs_baseline"] is not None else None,
        "has_positive_edge": bool(best["is_valid"]),
        "is_valid": bool(best["is_valid"]),
        "current_passes_threshold": current_passes,
        "target_hit_rate": target_hit_rate,
        "min_edge": min_edge,
        "min_required_signals": min_signals,
        "rule": best.get("rule") or {},
        "rule_text": best.get("rule_text"),
        "avg_return": round(best["avg_return"], 3) if best.get("avg_return") is not None else None,
        "median_return": round(best["median_return"], 3) if best.get("median_return") is not None else None,
        "worst_return": round(best["worst_return"], 3) if best.get("worst_return") is not None else None,
        "profit_factor": round(best["profit_factor"], 3) if best.get("profit_factor") is not None else None,
        "hit_rate_lower_bound": round(best["hit_rate_lower_bound"], 2) if best.get("hit_rate_lower_bound") is not None else None,
        "train_hit_rate": round(best["train_hit_rate"], 2) if best.get("train_hit_rate") is not None else None,
        "train_signal_count": int(best.get("train_signal_count") or 0),
        "train_passed": bool(best.get("train_passed")),
        "validation_hit_rate": round(best["validation_hit_rate"], 2) if best.get("validation_hit_rate") is not None else None,
        "validation_signal_count": int(best.get("validation_signal_count") or 0),
        "validation_avg_return": round(best["validation_avg_return"], 3) if best.get("validation_avg_return") is not None else None,
        "validation_passed": bool(best.get("validation_passed")),
        "cv_evaluable_folds": int(best.get("cv_evaluable_folds") or 0),
        "cv_passed_folds": int(best.get("cv_passed_folds") or 0),
        "cv_pass_rate": round(best["cv_pass_rate"], 2) if best.get("cv_pass_rate") is not None else None,
        "cv_min_hit_rate": round(best["cv_min_hit_rate"], 2) if best.get("cv_min_hit_rate") is not None else None,
        "cv_avg_return": round(best["cv_avg_return"], 3) if best.get("cv_avg_return") is not None else None,
        "cv_passed": bool(best.get("cv_passed")),
        "training_status": best.get("training_status", "unvalidated"),
        "note": "专属训练" if specific_training else "少出手高胜率精筛：只在强信号区间触发上涨判断",
    }


def _search_specific_signal(
    samples: List[Dict[str, Any]],
    actuals: np.ndarray,
    baseline: float,
    horizon: int,
    min_signals: int,
    target_hit_rate: float,
    min_edge: float,
    current_features: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    """Search interpretable rules, then require out-of-sample validation."""
    best_current_valid = None
    best_any_valid = None
    best_current_full = None
    best_any_full = None
    thresholds = np.arange(0.55, 0.901, 0.005)
    has_external = bool(
        any(key in current_features for key in EXTERNAL_FACTOR_FEATURES)
        or any(
            any(key in (sample.get("features") or {}) for key in EXTERNAL_FACTOR_FEATURES)
            for sample in samples[: min(len(samples), 80)]
        )
    )
    rule_templates = _specific_rule_templates(horizon, has_external=has_external)
    split_index = _specific_validation_split_index(len(samples))
    train_samples = samples[:split_index]
    validation_samples = samples[split_index:]
    min_validation_signals = SPECIFIC_MIN_VALIDATION_SIGNALS_BY_HORIZON.get(horizon, 3)
    min_train_signals = max(min_validation_signals, int(math.ceil(min_signals * 0.65)))

    for threshold in thresholds:
        for template in rule_templates:
            rule = {"prob_min": float(threshold), **template}
            full_metrics = _evaluate_rule_metrics(samples, rule, baseline)
            if not _passes_specific_full_metrics(full_metrics, min_signals, target_hit_rate, min_edge):
                continue

            train_metrics = _evaluate_rule_metrics(train_samples, rule, baseline)
            validation_metrics = _evaluate_rule_metrics(validation_samples, rule, baseline)
            cv_metrics = _time_series_cv_metrics(
                samples,
                rule,
                baseline,
                target_hit_rate,
                min_edge,
                min_validation_signals,
            )
            train_passed = _passes_specific_full_metrics(
                train_metrics,
                min_train_signals,
                target_hit_rate,
                min_edge,
            )
            validation_passed = _passes_specific_validation_metrics(
                validation_metrics,
                min_validation_signals,
                target_hit_rate,
                min_edge,
            )
            cv_passed = bool(cv_metrics.get("cv_passed"))
            is_valid = bool(train_passed and validation_passed and cv_passed)
            candidate = {
                "threshold": float(threshold),
                "hit_rate": full_metrics["hit_rate"],
                "signal_count": full_metrics["signal_count"],
                "coverage_pct": full_metrics["coverage_pct"],
                "baseline_hit_rate": baseline,
                "edge_vs_baseline": full_metrics["edge_vs_baseline"],
                "avg_return": full_metrics["avg_return"],
                "median_return": full_metrics["median_return"],
                "worst_return": full_metrics["worst_return"],
                "profit_factor": full_metrics["profit_factor"],
                "hit_rate_lower_bound": full_metrics["hit_rate_lower_bound"],
                "train_hit_rate": train_metrics["hit_rate"],
                "train_signal_count": train_metrics["signal_count"],
                "train_passed": train_passed,
                "validation_hit_rate": validation_metrics["hit_rate"],
                "validation_signal_count": validation_metrics["signal_count"],
                "validation_avg_return": validation_metrics["avg_return"],
                "validation_passed": validation_passed,
                "cv_evaluable_folds": cv_metrics["cv_evaluable_folds"],
                "cv_passed_folds": cv_metrics["cv_passed_folds"],
                "cv_pass_rate": cv_metrics["cv_pass_rate"],
                "cv_min_hit_rate": cv_metrics["cv_min_hit_rate"],
                "cv_avg_return": cv_metrics["cv_avg_return"],
                "cv_passed": cv_passed,
                "training_status": _specific_training_status(train_passed, validation_passed, cv_passed),
                "is_valid": is_valid,
                "rule": rule,
                "rule_text": _rule_text(rule),
            }

            current_matches = _features_pass_rule(current_features, rule)
            if is_valid:
                if _is_better_specific_candidate(candidate, best_any_valid):
                    best_any_valid = candidate
                if current_matches and _is_better_specific_candidate(candidate, best_current_valid):
                    best_current_valid = candidate
            else:
                if _is_better_specific_candidate(candidate, best_any_full):
                    best_any_full = candidate
                if current_matches and _is_better_specific_candidate(candidate, best_current_full):
                    best_current_full = candidate

    return best_current_valid or best_any_valid or best_current_full or best_any_full


def _specific_validation_split_index(sample_count: int) -> int:
    validation_count = int(math.ceil(sample_count * SPECIFIC_VALIDATION_FRACTION))
    validation_count = max(1, min(validation_count, max(sample_count - 1, 1)))
    return max(1, sample_count - validation_count)


def _evaluate_rule_metrics(
    samples: List[Dict[str, Any]],
    rule: Dict[str, float],
    baseline: float,
) -> Dict[str, Any]:
    if not samples:
        return {
            "hit_rate": None,
            "signal_count": 0,
            "coverage_pct": 0.0,
            "edge_vs_baseline": None,
            "avg_return": None,
            "median_return": None,
            "worst_return": None,
            "profit_factor": None,
            "hit_rate_lower_bound": None,
        }

    mask = np.array([
        _features_pass_rule(sample.get("features") or {}, rule)
        for sample in samples
    ], dtype=bool)
    signal_count = int(np.sum(mask))
    if signal_count <= 0:
        return {
            "hit_rate": None,
            "signal_count": 0,
            "coverage_pct": 0.0,
            "edge_vs_baseline": None,
            "avg_return": None,
            "median_return": None,
            "worst_return": None,
            "profit_factor": None,
            "hit_rate_lower_bound": None,
        }

    actuals = np.array([1.0 if sample["actual_up"] else 0.0 for sample in samples], dtype=float)
    returns = np.array([_safe_float(sample.get("future_return"), 0.0) for sample in samples], dtype=float)
    selected_actuals = actuals[mask]
    selected_returns = returns[mask]
    positive_returns = selected_returns[selected_returns > 0]
    negative_returns = selected_returns[selected_returns < 0]
    gross_profit = float(np.sum(positive_returns))
    gross_loss = abs(float(np.sum(negative_returns)))
    if gross_loss > 1e-9:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = 99.0
    else:
        profit_factor = 0.0

    hit_rate = float(np.mean(selected_actuals) * 100)
    up_count = int(np.sum(selected_actuals))
    return {
        "hit_rate": hit_rate,
        "signal_count": signal_count,
        "coverage_pct": signal_count / len(samples) * 100,
        "edge_vs_baseline": hit_rate - baseline,
        "avg_return": float(np.mean(selected_returns)),
        "median_return": float(np.median(selected_returns)),
        "worst_return": float(np.min(selected_returns)),
        "profit_factor": float(profit_factor),
        "hit_rate_lower_bound": _wilson_lower_bound_pct(up_count, signal_count),
    }


def _passes_specific_full_metrics(
    metrics: Dict[str, Any],
    min_signals: int,
    target_hit_rate: float,
    min_edge: float,
) -> bool:
    hit_rate = metrics.get("hit_rate")
    edge = metrics.get("edge_vs_baseline")
    avg_return = metrics.get("avg_return")
    profit_factor = metrics.get("profit_factor")
    lower_bound = metrics.get("hit_rate_lower_bound")
    return bool(
        hit_rate is not None
        and edge is not None
        and int(metrics.get("signal_count") or 0) >= min_signals
        and float(hit_rate) >= target_hit_rate
        and _safe_float(lower_bound, 0.0) >= SPECIFIC_MIN_HIT_RATE_LOWER_BOUND
        and float(edge) >= min_edge
        and _safe_float(avg_return, -1e9) > 0
        and _safe_float(profit_factor, 0.0) >= SPECIFIC_MIN_PROFIT_FACTOR
    )


def _passes_specific_validation_metrics(
    metrics: Dict[str, Any],
    min_signals: int,
    target_hit_rate: float,
    min_edge: float,
) -> bool:
    hit_rate = metrics.get("hit_rate")
    edge = metrics.get("edge_vs_baseline")
    avg_return = metrics.get("avg_return")
    profit_factor = metrics.get("profit_factor")
    return bool(
        hit_rate is not None
        and edge is not None
        and int(metrics.get("signal_count") or 0) >= min_signals
        and float(hit_rate) >= target_hit_rate
        and float(edge) >= min_edge
        and _safe_float(avg_return, -1e9) > 0
        and _safe_float(profit_factor, 0.0) >= 1.0
    )


def _time_series_cv_metrics(
    samples: List[Dict[str, Any]],
    rule: Dict[str, float],
    baseline: float,
    target_hit_rate: float,
    min_edge: float,
    min_fold_signals: int,
) -> Dict[str, Any]:
    folds = _split_time_series_folds(samples, SPECIFIC_CV_FOLDS)
    evaluable = 0
    passed = 0
    hit_rates: List[float] = []
    avg_returns: List[float] = []
    min_fold_signals = max(2, int(math.ceil(min_fold_signals * 0.60)))

    for fold in folds:
        metrics = _evaluate_rule_metrics(fold, rule, baseline)
        if int(metrics.get("signal_count") or 0) < min_fold_signals:
            continue
        evaluable += 1
        hit_rate = metrics.get("hit_rate")
        avg_return = metrics.get("avg_return")
        if hit_rate is not None:
            hit_rates.append(float(hit_rate))
        if avg_return is not None:
            avg_returns.append(float(avg_return))
        fold_passed = bool(
            hit_rate is not None
            and float(hit_rate) >= max(60.0, target_hit_rate - 15.0)
            and _safe_float(metrics.get("edge_vs_baseline"), -1e9) >= max(0.0, min_edge - 3.0)
            and _safe_float(avg_return, -1e9) > 0
            and _safe_float(metrics.get("profit_factor"), 0.0) >= 1.0
        )
        if fold_passed:
            passed += 1

    pass_rate = passed / evaluable * 100 if evaluable else None
    cv_min_hit_rate = min(hit_rates) if hit_rates else None
    cv_avg_return = float(np.mean(avg_returns)) if avg_returns else None
    cv_passed = bool(
        evaluable >= SPECIFIC_MIN_CV_EVALUABLE_FOLDS
        and pass_rate is not None
        and pass_rate >= SPECIFIC_MIN_CV_PASS_RATE
        and cv_avg_return is not None
        and cv_avg_return > 0
    )
    return {
        "cv_evaluable_folds": evaluable,
        "cv_passed_folds": passed,
        "cv_pass_rate": pass_rate,
        "cv_min_hit_rate": cv_min_hit_rate,
        "cv_avg_return": cv_avg_return,
        "cv_passed": cv_passed,
    }


def _split_time_series_folds(samples: List[Dict[str, Any]], fold_count: int) -> List[List[Dict[str, Any]]]:
    if not samples:
        return []
    indices = np.array_split(np.arange(len(samples)), max(1, fold_count))
    return [[samples[int(i)] for i in fold_indices] for fold_indices in indices if len(fold_indices) > 0]


def _wilson_lower_bound_pct(successes: int, total: int, z: float = 1.96) -> Optional[float]:
    if total <= 0:
        return None
    phat = successes / total
    denominator = 1.0 + z * z / total
    centre = phat + z * z / (2.0 * total)
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - margin) / denominator * 100)


def _specific_training_status(train_passed: bool, validation_passed: bool, cv_passed: bool) -> str:
    if train_passed and validation_passed and cv_passed:
        return "样本外与多折验证通过"
    if train_passed and not validation_passed:
        return "训练段达标但样本外未确认"
    if validation_passed and not train_passed:
        return "样本外达标但训练段不稳定"
    if train_passed and validation_passed and not cv_passed:
        return "单次样本外通过但多折不稳定"
    return "全样本达标但分段验证未确认"


def _specific_rule_templates(horizon: int, has_external: bool = False) -> List[Dict[str, float]]:
    templates: List[Dict[str, float]] = [{}]
    for pos_max in (95, 90, 85, 80, 75, 70):
        templates.append({"position_30d_max": float(pos_max)})
    for pos60_max in (95, 85, 75):
        templates.append({"position_60d_max": float(pos60_max)})
    for rsi_max in (80, 75, 70, 65):
        templates.append({"rsi_14_max": float(rsi_max)})
    for bb_max in (98, 95, 90, 85):
        templates.append({"bb_position_max": float(bb_max)})
    for ret5_min in (-5, -3, -1, 0, 1):
        templates.append({"return_5d_min": float(ret5_min)})
    for prev_min in (-5, -2, 0):
        templates.append({"prev_return_min": float(prev_min)})
    for score_min in (-15, -5, 0, 5):
        templates.append({"score_min": float(score_min)})

    combined = [
        {"position_30d_max": 80.0, "rsi_14_max": 75.0},
        {"position_30d_max": 80.0, "bb_position_max": 90.0},
        {"rsi_14_max": 70.0, "bb_position_max": 90.0},
        {"position_30d_max": 80.0, "rsi_14_max": 75.0, "return_5d_min": -1.0},
        {"position_30d_max": 70.0, "rsi_14_max": 70.0, "prev_return_min": 0.0},
        {"return_5d_min": 0.0, "prev_return_min": 0.0},
    ]
    pair_groups = [
        [{"position_30d_max": v} for v in (90.0, 80.0, 70.0)],
        [{"rsi_14_max": v} for v in (80.0, 75.0, 70.0)],
        [{"bb_position_max": v} for v in (95.0, 90.0, 85.0)],
        [{"return_5d_min": v} for v in (-3.0, -1.0, 0.0, 1.0)],
        [{"return_20d_min": v} for v in (-8.0, -5.0, 0.0)],
        [{"score_min": v} for v in (-5.0, 0.0, 5.0)],
    ]
    combined.extend(_combine_rule_groups(pair_groups, max_parts=2))
    combined.extend(_combine_rule_groups(pair_groups[:4], max_parts=3, cap=80))
    if horizon >= 7:
        combined.extend([
            {"return_20d_min": -5.0, "position_30d_max": 85.0},
            {"return_20d_min": 0.0, "rsi_14_max": 75.0},
        ])
    if has_external:
        templates.extend([
            {"factor_return_1d_min": -3.0},
            {"factor_return_5d_min": -5.0},
            {"factor_return_5d_min": -2.0},
            {"factor_return_5d_min": 0.0},
            {"factor_position_30d_max": 95.0},
            {"factor_position_30d_max": 85.0},
            {"factor_position_30d_max": 75.0},
            {"factor_above_ma20_min": 1.0},
            {"factor_volatility_20d_max": 45.0},
        ])
        factor_groups = [
            [{"factor_return_5d_min": v} for v in (-5.0, -2.0, 0.0, 1.0)],
            [{"factor_return_20d_min": v} for v in (-10.0, -5.0, 0.0)],
            [{"factor_position_30d_max": v} for v in (95.0, 85.0, 75.0)],
            [{"factor_above_ma20_min": 1.0}],
            [{"factor_volatility_20d_max": v} for v in (35.0, 45.0, 60.0)],
        ]
        combined.extend([
            {"factor_return_5d_min": -2.0, "position_30d_max": 85.0},
            {"factor_return_5d_min": 0.0, "rsi_14_max": 75.0},
            {"factor_position_30d_max": 85.0, "bb_position_max": 90.0},
            {"factor_above_ma20_min": 1.0, "return_5d_min": -1.0},
        ])
        combined.extend(_combine_rule_groups([pair_groups[0], pair_groups[1], factor_groups[0], factor_groups[2]], max_parts=2, cap=120))
        combined.extend(_combine_rule_groups([pair_groups[0], pair_groups[1], factor_groups[0], factor_groups[2]], max_parts=3, cap=120))
        if horizon >= 7:
            combined.extend([
                {"factor_return_20d_min": -8.0, "position_30d_max": 85.0},
                {"factor_return_20d_min": 0.0, "rsi_14_max": 75.0},
                {"factor_return_5d_min": 0.0, "factor_position_30d_max": 90.0},
            ])
    return _dedupe_rule_templates(templates + combined)


def _combine_rule_groups(
    groups: List[List[Dict[str, float]]],
    max_parts: int,
    cap: int = 200,
) -> List[Dict[str, float]]:
    results: List[Dict[str, float]] = []

    def visit(start: int, remaining: int, current: Dict[str, float]) -> None:
        if len(results) >= cap:
            return
        if remaining == 0:
            if current:
                results.append(dict(current))
            return
        for group_index in range(start, len(groups)):
            for item in groups[group_index]:
                next_rule = dict(current)
                next_rule.update(item)
                visit(group_index + 1, remaining - 1, next_rule)
                if len(results) >= cap:
                    return

    visit(0, max_parts, {})
    return results


def _dedupe_rule_templates(templates: List[Dict[str, float]]) -> List[Dict[str, float]]:
    seen = set()
    deduped: List[Dict[str, float]] = []
    for template in templates:
        key = tuple(sorted(template.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(template)
    return deduped


def _features_pass_rule(features: Dict[str, float], rule: Dict[str, float]) -> bool:
    if not features:
        return False
    for key, expected in rule.items():
        if key.endswith("_min"):
            feature_key = key[:-4]
            if _safe_float(features.get(feature_key), -1e9) < float(expected):
                return False
        elif key.endswith("_max"):
            feature_key = key[:-4]
            if _safe_float(features.get(feature_key), 1e9) > float(expected):
                return False
        else:
            if _safe_float(features.get(key), -1e9) < float(expected):
                return False
    return True


def _is_better_specific_candidate(candidate: Dict[str, Any], current: Optional[Dict[str, Any]]) -> bool:
    if current is None:
        return True
    if candidate["hit_rate"] > current["hit_rate"] + 1e-9:
        return True
    if abs(candidate["hit_rate"] - current["hit_rate"]) <= 1e-9:
        if candidate["signal_count"] > current["signal_count"]:
            return True
        if candidate["coverage_pct"] > current["coverage_pct"] and candidate["signal_count"] == current["signal_count"]:
            return True
    return False


def _rule_text(rule: Dict[str, float]) -> str:
    labels = {
        "prob_min": "上涨信号概率",
        "score_min": "模型分数",
        "rsi_14_max": "RSI不高于",
        "bb_position_max": "布林带位置不高于",
        "position_30d_max": "30日位置不高于",
        "position_60d_max": "60日位置不高于",
        "return_5d_min": "近5日收益不低于",
        "return_20d_min": "近20日收益不低于",
        "prev_return_min": "上一周期收益不低于",
        "factor_return_1d_min": "股票篮子近1日收益不低于",
        "factor_return_5d_min": "股票篮子近5日收益不低于",
        "factor_return_20d_min": "股票篮子近20日收益不低于",
        "factor_position_30d_max": "股票篮子30日位置不高于",
        "factor_above_ma20_min": "股票篮子站上20日线",
        "factor_volatility_20d_max": "股票篮子20日波动率不高于",
    }
    parts = []
    for key, value in rule.items():
        label = labels.get(key, key)
        if key == "prob_min":
            parts.append(f"{label}>={value * 100:.0f}%")
        elif key == "factor_above_ma20_min":
            parts.append(label)
        elif key.endswith("_max"):
            parts.append(f"{label}{value:g}")
        elif key.endswith("_min"):
            parts.append(f"{label}{value:g}%")
        else:
            parts.append(f"{label}>={value:g}")
    return "，".join(parts)


def _empty_selective_stats(current_prob: float, horizon: int, note: str) -> Dict[str, Any]:
    threshold = HIGH_WIN_DEFAULT_THRESHOLDS.get(horizon, 0.62)
    return {
        "threshold": threshold,
        "threshold_pct": round(threshold * 100, 1),
        "hit_rate": None,
        "signal_count": 0,
        "coverage_pct": 0.0,
        "baseline_hit_rate": None,
        "edge_vs_baseline": None,
        "has_positive_edge": False,
        "is_valid": False,
        "current_passes_threshold": False,
        "avg_return": None,
        "median_return": None,
        "worst_return": None,
        "profit_factor": None,
        "hit_rate_lower_bound": None,
        "train_hit_rate": None,
        "train_signal_count": 0,
        "train_passed": False,
        "validation_hit_rate": None,
        "validation_signal_count": 0,
        "validation_avg_return": None,
        "validation_passed": False,
        "cv_evaluable_folds": 0,
        "cv_passed_folds": 0,
        "cv_pass_rate": None,
        "cv_min_hit_rate": None,
        "cv_avg_return": None,
        "cv_passed": False,
        "training_status": "empty",
        "note": note,
    }


def _specific_training_meta(
    fund_code: str,
    fund_name: str,
    enabled: bool,
    external_factor_meta: Optional[Dict[str, Any]] = None,
    external_features: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    meta = {
        "enabled": enabled,
        "fund_code": str(fund_code or "").strip() or None,
        "fund_name": fund_name or None,
        "target_hit_rate": SPECIFIC_TARGET_HIT_RATE if enabled else None,
        "min_edge": SPECIFIC_MIN_EDGE if enabled else None,
        "note": "仅对用户指定基金启用专属长历史训练" if enabled else "通用模式",
    }
    if enabled:
        factor_meta = external_factor_meta or {}
        factor_available = external_features is not None and not external_features.empty
        meta.update({
            "factor_status": "available" if factor_available else factor_meta.get("status", "unavailable"),
            "factor_sources": factor_meta.get("sources", []),
            "factor_note": factor_meta.get(
                "note",
                "未取得可回测的重仓股或行业代理因子，当前仅使用基金净值训练。",
            ),
        })
    return meta


def _confidence(
    sample_size: int,
    edge: float,
    brier: float,
    probability: float,
    selective: Optional[Dict[str, Any]] = None,
) -> str:
    """提高置信度门槛，更严格的标准"""
    selective = selective or {}
    if selective.get("current_passes_threshold"):
        signal_count = int(selective.get("signal_count") or 0)
        hit_rate = _safe_float(selective.get("hit_rate"), 0)
        selective_edge = _safe_float(selective.get("edge_vs_baseline"), 0)
        target_hit = _safe_float(selective.get("target_hit_rate"), HIGH_WIN_TARGET_HIT_RATE)
        min_edge = _safe_float(selective.get("min_edge"), HIGH_WIN_MIN_EDGE)
        min_signals = int(selective.get("min_required_signals") or HIGH_WIN_MIN_SIGNALS)
        if hit_rate >= target_hit and signal_count >= min_signals and selective_edge >= min_edge:
            return "高" if signal_count >= max(30, min_signals) else "中"
        if signal_count >= 30 and hit_rate >= 65 and selective_edge >= 8:
            return "高"
        if signal_count >= HIGH_WIN_MIN_SIGNALS and hit_rate >= HIGH_WIN_TARGET_HIT_RATE and selective_edge >= HIGH_WIN_MIN_EDGE:
            return "中"

    distance = abs(probability - 0.5)
    # 高置信度：样本充足 + 边际优势显著 + 概率明确
    if sample_size >= 100 and edge >= 8 and brier <= 0.22 and distance >= 0.15:
        return "高"
    # 中置信度：样本足够 + 有正向优势 + 概率偏离中性
    if sample_size >= 50 and edge >= 4 and brier <= 0.25 and distance >= 0.10:
        return "中"
    return "低"


def _direction_from_probability(
    probability: float,
    edge: float,
    confidence: str,
    selective: Optional[Dict[str, Any]] = None,
) -> str:
    """更严格的方向判断：必须有正向优势且置信度至少中等"""
    selective = selective or {}
    if selective.get("current_passes_threshold") and confidence != "低":
        return "up"

    # 边际优势不足或置信度低 → uncertain
    if edge < 3 or confidence == "低":
        return "uncertain"
    # 概率明确偏向上涨
    if probability >= 0.58:
        return "up"
    if probability <= 0.45:
        return "down_or_flat"
    return "uncertain"


def _direction_label(direction: str) -> str:
    return {
        "up": "偏上涨",
        "down_or_flat": "偏不涨",
        "uncertain": "不确定",
    }.get(direction, "不确定")


def _current_feature_snapshot(navs: np.ndarray, score: float) -> Dict[str, Any]:
    indicators = compute_indicators_from_nav(navs)
    return {
        "score": round(float(score), 2),
        "return_1d": indicators.get("return_1trading"),
        "return_5d": indicators.get("return_5trading"),
        "return_20d": indicators.get("return_20trading"),
        "trend": indicators.get("trend"),
        "rsi_14": indicators.get("rsi_14"),
        "volatility_30d": indicators.get("volatility_30d"),
        "position_in_30d_range": indicators.get("position_in_30d_range"),
        "macd": indicators.get("macd"),
        "bollinger": indicators.get("bollinger"),
    }


def _main_reasons(
    features: Dict[str, Any],
    scoring_reasons: List[str],
    edge: float,
    confidence: str,
    selective: Optional[Dict[str, Any]] = None,
) -> List[str]:
    reasons: List[str] = []
    selective = selective or {}
    ret5 = _safe_float(features.get("return_5d"), 0)
    ret20 = _safe_float(features.get("return_20d"), 0)
    rsi14 = _safe_float(features.get("rsi_14"), 50)
    pos30 = _safe_float(features.get("position_in_30d_range"), 50)
    vol30 = _safe_float(features.get("volatility_30d"), 0)
    factor_ret5 = _safe_float(features.get("factor_return_5d"), math.nan)
    factor_pos30 = _safe_float(features.get("factor_position_30d"), math.nan)

    if ret5 > 0 and ret20 > 0:
        reasons.append("近5日和近20日动能为正")
    elif ret5 < 0 and ret20 < 0:
        reasons.append("近5日和近20日动能为负")

    if math.isfinite(factor_ret5):
        if factor_ret5 > 0:
            reasons.append("重仓股/代理股票篮子近5日动能为正")
        elif factor_ret5 < 0:
            reasons.append("重仓股/代理股票篮子近5日动能为负")

    if math.isfinite(factor_pos30):
        if factor_pos30 >= 80:
            reasons.append("重仓股/代理股票篮子处于近30日较高位置")
        elif factor_pos30 <= 20:
            reasons.append("重仓股/代理股票篮子处于近30日较低位置")

    if rsi14 >= 70:
        reasons.append("RSI偏高，短线回落风险上升")
    elif rsi14 <= 30:
        reasons.append("RSI偏低，存在技术修复可能")

    if pos30 >= 80:
        reasons.append("净值处于近30日较高位置")
    elif pos30 <= 20:
        reasons.append("净值处于近30日较低位置")

    if vol30 >= 30:
        reasons.append("近期波动率偏高，预测误差可能放大")

    if edge > 0:
        reasons.append(f"历史回测较简单基线高 {round(edge, 2)} 个百分点")
    else:
        reasons.append("历史回测未跑赢简单基线")

    selective_hit = selective.get("hit_rate")
    selective_count = selective.get("signal_count")
    selective_threshold = selective.get("threshold_pct")
    if selective_hit is not None and selective_count:
        reasons.append(
            f"高胜率精筛阈值{selective_threshold}%，历史强信号{selective_count}次，命中率{selective_hit}%"
        )
    validation_hit = selective.get("validation_hit_rate")
    validation_count = selective.get("validation_signal_count")
    if validation_hit is not None and validation_count:
        reasons.append(f"样本外验证信号{validation_count}次，命中率{validation_hit}%")
    cv_pass_rate = selective.get("cv_pass_rate")
    cv_evaluable = selective.get("cv_evaluable_folds")
    if cv_pass_rate is not None and cv_evaluable:
        reasons.append(f"多折验证{cv_evaluable}折可评估，通过率{cv_pass_rate}%")
    lower_bound = selective.get("hit_rate_lower_bound")
    if lower_bound is not None:
        reasons.append(f"命中率置信下界{lower_bound}%")
    profit_factor = selective.get("profit_factor")
    avg_return = selective.get("avg_return")
    if profit_factor is not None and avg_return is not None:
        reasons.append(f"精筛平均收益{avg_return}%，收益因子{profit_factor}")

    if confidence == "低":
        reasons.append("置信度低，结果只适合作为弱参考")

    for reason in scoring_reasons:
        if reason and reason not in reasons:
            reasons.append(reason)
        if len(reasons) >= 6:
            break

    return reasons[:6]


def _warning(edge: float, confidence: str, selective: Optional[Dict[str, Any]] = None) -> Optional[str]:
    selective = selective or {}
    training_status = str(selective.get("training_status") or "")
    if training_status and training_status != "样本外与多折验证通过" and selective.get("hit_rate") is not None:
        return "全历史样本曾达到高胜率，但训练/验证拆分后稳定性不足，暂不触发。"
    if selective.get("is_valid") and not selective.get("current_passes_threshold"):
        return "历史上存在高胜率强信号区间，但当前概率未达到触发阈值，建议等待。"
    if edge <= 0:
        return "该周期历史验证未显示模型优于简单基线，不应据此单独决策。"
    if confidence == "低":
        return "该周期虽然有信号，但置信度不足，应结合风险评分和仓位控制。"
    return None


def _empty_period(
    horizon: int,
    current_raw_prob: float,
    current_score: float,
    features: Dict[str, Any],
    sample_size: int,
) -> Dict[str, Any]:
    up_probability = round(current_raw_prob * 100, 1)
    return {
        "period_days": horizon,
        "predicted_direction": "uncertain",
        "direction_label": "不确定",
        "up_probability": up_probability,
        "down_or_flat_probability": round(100 - up_probability, 1),
        "confidence": "低",
        "current_score": round(current_score, 2),
        "sample_size": sample_size,
        "historical_hit_rate": None,
        "baseline_hit_rate": None,
        "edge_vs_baseline": None,
        "has_positive_edge": False,
        "signal_probability": round(current_raw_prob * 100, 1),
        "selective_threshold": HIGH_WIN_DEFAULT_THRESHOLDS.get(horizon, 0.62) * 100,
        "selective_hit_rate": None,
        "selective_signal_count": 0,
        "selective_coverage_pct": 0.0,
        "selective_edge_vs_baseline": None,
        "current_passes_selective_threshold": False,
        "selective_signal_valid": False,
        "selective_target_hit_rate": None,
        "selective_min_required_signals": 0,
        "selective_rule_text": None,
        "selective_rule": {},
        "selective_avg_return": None,
        "selective_median_return": None,
        "selective_worst_return": None,
        "selective_profit_factor": None,
        "selective_hit_rate_lower_bound": None,
        "selective_train_hit_rate": None,
        "selective_train_signal_count": 0,
        "selective_train_passed": False,
        "selective_validation_hit_rate": None,
        "selective_validation_signal_count": 0,
        "selective_validation_avg_return": None,
        "selective_validation_passed": False,
        "selective_cv_evaluable_folds": 0,
        "selective_cv_passed_folds": 0,
        "selective_cv_pass_rate": None,
        "selective_cv_min_hit_rate": None,
        "selective_cv_avg_return": None,
        "selective_cv_passed": False,
        "selective_training_status": "empty",
        "brier_score": None,
        "actual_up_rate": None,
        "baseline_detail": {},
        "calibration_note": "walk-forward 样本不足，未做可靠校准。",
        "main_reasons": ["历史样本不足，不能验证预测优势"],
        "feature_snapshot": features,
        "warning": "样本不足，不应把该概率当作可靠预测。",
    }


def _period_return(navs: np.ndarray, horizon: int) -> float:
    if len(navs) <= horizon:
        return 0.0
    return float((navs[-1] / navs[-1 - horizon] - 1.0) * 100)


def _hit_rate(predictions: List[bool], actuals: List[bool]) -> float:
    if not predictions:
        return 0.0
    return round(sum(p == a for p, a in zip(predictions, actuals)) / len(predictions) * 100, 2)


def _sigmoid(value: float) -> float:
    value = max(-20.0, min(20.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _shrink_probability(probability: float, sample_days: int) -> float:
    # Short histories should stay close to 50%.
    strength = min(1.0, max(0.25, (sample_days - 30) / 90))
    return 0.5 + (probability - 0.5) * strength


def _safe_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        value = float(value)
        if not math.isfinite(value):
            return default
        return value
    except (TypeError, ValueError):
        return default
