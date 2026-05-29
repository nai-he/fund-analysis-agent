"""
回测与评估模块
对基金历史净值做 walk-forward 回测，评估规则模型的预测准确度

关键设计：
- 每个 walk-forward 样本只能用预测点之前的 hist 数据（无数据泄漏）
- 动态阈值在每个样本内部用 hist 计算
- simple_momentum baseline 只用 hist 里的历史收益
- actual label 使用未来 horizon 的净值
- 使用 shared scoring 模块确保回测与 forecast_engine 使用完全相同的评分逻辑
"""
import logging
from typing import Dict, Any, Optional, List, Tuple

import pandas as pd
import numpy as np

from scoring import compute_indicators_from_nav, score_from_indicators

logger = logging.getLogger(__name__)

# 每周期最小阈值（%），防止极低波动下阈值过小
MIN_THRESHOLDS = {1: 0.5, 3: 1.0, 7: 2.0, 30: 3.0}

# 日波动率 fallback：年化 15% 对应的日波动
FALLBACK_DAILY_VOL = 0.15 / np.sqrt(250)

LABELS = ["up", "sideways", "down"]


def run_backtest(
    nav_df: pd.DataFrame,
    horizons: List[int] = [1, 3, 7, 30],
    min_samples: int = 20,
) -> Dict[str, Any]:
    """
    Walk-forward 回测，评估规则模型在各周期的方向预测准确度
    """
    if nav_df is None or len(nav_df) < 60:
        return {"error": "insufficient_data", "sample_size": len(nav_df) if nav_df is not None else 0}

    df = nav_df.sort_values("净值日期", ascending=True).copy()
    df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
    df = df.dropna(subset=["单位净值"])
    if len(df) < 60:
        return {"error": "insufficient_data", "sample_size": len(df)}

    result = {
        "model_basis": "rule_based",
        "sample_size": len(df),
        "periods": {},
        "probability_quality": "low",
        "main_uncertainties": [],
        "is_calibrated": False,
    }

    for horizon in horizons:
        period_result = _backtest_horizon(df, horizon, min_samples)
        result["periods"][f"{horizon}d"] = period_result

    # 汇总 probability_quality
    result["probability_quality"], result["is_calibrated"] = _assess_quality(result["periods"])

    # 汇总不确定因素
    result["main_uncertainties"] = _summarize_uncertainties(result)

    # 计算校准曲线（供 forecast_engine 使用）
    result["calibration_curve"] = _compute_calibration_curve(result["periods"])
    if result["probability_quality"] == "low":
        if not any("回测未证明规则模型优于基准" in u for u in result["main_uncertainties"]):
            result["main_uncertainties"].append("回测未证明规则模型稳定优于基准模型，概率仅作低置信参考")

    return result


def _backtest_horizon(
    df: pd.DataFrame,
    horizon: int,
    min_samples: int,
) -> Dict[str, Any]:
    """对单个周期做 walk-forward 回测，每个样本只用 hist 数据"""
    lookback = min(90, len(df) // 2)
    if lookback < 40:
        lookback = 40

    predictions: List[str] = []
    raw_scores: List[float] = []
    momentum_predictions: List[str] = []
    actuals: List[str] = []
    realized_returns: List[float] = []
    thresholds_used: List[float] = []

    # 前视范围用最大 horizon 确定
    max_horizon = horizon

    for i in range(lookback, len(df) - max_horizon):
        end_pred_idx = i
        start_pred_idx = i + horizon
        if start_pred_idx >= len(df):
            continue

        # hist: 仅预测点之前的数据，无未来信息泄漏
        hist = df.iloc[end_pred_idx - lookback:end_pred_idx]
        future = df.iloc[start_pred_idx]

        hist_navs = hist["单位净值"].values
        if len(hist_navs) < 5:
            continue

        # === 在 hist 内计算动态阈值（无泄漏） ===
        hist_returns = np.diff(hist_navs) / hist_navs[:-1]
        if len(hist_returns) >= 5:
            hist_daily_vol = float(np.std(hist_returns))
        else:
            hist_daily_vol = FALLBACK_DAILY_VOL
        # 无效、NaN、过小使用保守 fallback
        if np.isnan(hist_daily_vol) or hist_daily_vol <= 0:
            hist_daily_vol = FALLBACK_DAILY_VOL
        threshold = max(
            MIN_THRESHOLDS.get(horizon, 2.0),
            hist_daily_vol * np.sqrt(horizon) * 100,
        )
        # 上限防止极端阈值
        threshold = min(threshold, 20.0)
        thresholds_used.append(threshold)

        # === 规则打分（使用 shared scoring，与 forecast_engine 完全一致） ===
        # 检测市场体制
        regime = _detect_regime(hist_navs)

        # 计算技术指标
        indicators = compute_indicators_from_nav(hist_navs)
        if indicators.get("error"):
            continue

        # 根据体制调整因子权重（通过调节传入参数间接影响评分）
        # 在趋势市：趋势因子主导；在震荡市：RSI/BB 反转信号主导
        score, _reasons, _up, _down = score_from_indicators(indicators, horizon)

        # 体制微调：震荡市中降低趋势信号强度，增加均值回复信号
        if regime == "mean_reverting":
            # RSI 极端值在震荡市中更有效，额外加分
            rsi14 = indicators.get("rsi_14") or 50
            if rsi14 < 30:
                score += 8  # 震荡市超卖反弹更强
            elif rsi14 > 70:
                score -= 8  # 震荡市超买回落更强
        elif regime == "trending":
            # 趋势市中趋势信号更可靠，但不过度调整
            pass
        elif regime == "high_volatility":
            # 高波动市中降低整体信号强度
            score *= 0.75

        # 预测方向（使用与 forecast_engine 相同的阈值逻辑）
        if score >= 12:
            pred = "up"
        elif score <= -12:
            pred = "down"
        else:
            pred = "sideways"
        predictions.append(pred)
        raw_scores.append(score)
        momentum_predictions.append(_momentum_prediction_from_hist(hist_navs, horizon, threshold))

        # === 实际收益（使用未来数据，仅用于 label） ===
        start_nav = float(hist_navs[-1])
        end_nav = float(future["单位净值"])
        ret = (end_nav - start_nav) / start_nav * 100
        realized_returns.append(ret)

        if ret > threshold:
            actual = "up"
        elif ret < -threshold:
            actual = "down"
        else:
            actual = "sideways"
        actuals.append(actual)

    n = len(predictions)
    if n < min_samples:
        return _empty_period_result(
            round(float(np.mean(thresholds_used)), 3) if thresholds_used else MIN_THRESHOLDS.get(horizon, 2.0),
            n,
        )

    # === 方向准确率 ===
    correct = sum(p == a for p, a in zip(predictions, actuals))
    directional_accuracy = round(correct / n * 100, 2)

    # === Confusion matrix: 3x3 ===
    cm = {l: {l2: 0 for l2 in LABELS} for l in LABELS}
    for p, a in zip(predictions, actuals):
        cm[p][a] += 1

    # === Actual distribution ===
    actual_distribution = {
        "up_pct": round(sum(1 for a in actuals if a == "up") / n * 100, 1),
        "sideways_pct": round(sum(1 for a in actuals if a == "sideways") / n * 100, 1),
        "down_pct": round(sum(1 for a in actuals if a == "down") / n * 100, 1),
    }

    # === Brier score (multi-class) ===
    brier = _calc_brier_score(predictions, actuals, raw_scores)

    # === Calibration bins ===
    cal_bins = _compute_calibration_bins(predictions, actuals, raw_scores)

    # === Hit rate by confidence ===
    hit_rate = _calc_hit_by_confidence(predictions, actuals, realized_returns)

    # === 收益统计 ===
    ret_arr = np.array(realized_returns, dtype=float)
    return_stats = {
        "mean": round(float(np.mean(ret_arr)), 2),
        "median": round(float(np.median(ret_arr)), 2),
        "p10": round(float(np.percentile(ret_arr, 10)), 2),
        "p90": round(float(np.percentile(ret_arr, 90)), 2),
    }

    # === Baseline 对比 ===
    always_sideways_acc = sum(1 for a in actuals if a == "sideways") / n * 100
    simple_momentum_acc = _accuracy(momentum_predictions, actuals)
    rule_acc = directional_accuracy

    best_baseline_acc = max(always_sideways_acc, simple_momentum_acc)
    rule_vs_best_baseline_edge = round(rule_acc - best_baseline_acc, 2)

    baseline_comparison = {
        "always_sideways_acc": round(always_sideways_acc, 2),
        "simple_momentum_acc": round(simple_momentum_acc, 2),
        "rule_acc": rule_acc,
        "best_baseline_acc": round(best_baseline_acc, 2),
        "rule_vs_best_baseline_edge": rule_vs_best_baseline_edge,
    }

    avg_threshold = round(float(np.mean(thresholds_used)), 3) if thresholds_used else MIN_THRESHOLDS.get(horizon, 2.0)
    median_threshold = round(float(np.median(thresholds_used)), 3) if thresholds_used else avg_threshold

    return {
        "sample_size": n,
        "directional_accuracy": directional_accuracy,
        "confusion_matrix": cm,
        "brier_score": round(brier, 4),
        "calibration_bins": cal_bins,
        "hit_rate_by_confidence": hit_rate,
        "return_stats": return_stats,
        "threshold_used": avg_threshold,
        "threshold_median": median_threshold,
        "baseline_comparison": baseline_comparison,
        "actual_distribution": actual_distribution,
        "raw_score_stats": _compute_score_stats(raw_scores, predictions, actuals),
    }


def _prediction_probs_from_score(score: float, pred_label: str) -> Dict[str, float]:
    """基于原始评分动态计算三分类概率，替代固定置信度"""
    abs_score = min(abs(score), 80)
    confidence = 0.35 + 0.30 * (abs_score / 80)
    remaining = (1.0 - confidence) / 2.0
    probs = {"up": remaining, "sideways": remaining, "down": remaining}
    probs[pred_label] = confidence
    return probs


def _calc_brier_score(predictions: List[str], actuals: List[str], raw_scores: List[float]) -> float:
    """计算多分类 Brier score，范围 [0, 1]，使用 score-driven 概率"""
    n = len(predictions)
    if n == 0:
        return 1.0
    total = 0.0
    for i, (pred, actual) in enumerate(zip(predictions, actuals)):
        score = raw_scores[i] if i < len(raw_scores) else 0
        probs = _prediction_probs_from_score(score, pred)
        for label in LABELS:
            actual_onehot = 1.0 if label == actual else 0.0
            total += (probs[label] - actual_onehot) ** 2

    raw_brier = total / (2 * n)
    return min(1.0, max(0.0, raw_brier))


def _compute_calibration_bins(predictions: List[str], actuals: List[str], raw_scores: List[float]) -> List[Dict[str, Any]]:
    """计算校准 bins：按分数分桶，对比 expected_freq 与 observed_freq"""
    # 按分数分桶：低分(0-20) / 中低(20-40) / 中(40-60) / 中高(60-80) / 高分(80+)
    bin_edges = [0, 20, 40, 60, 80, 200]
    bin_labels = ["score_0-20", "score_20-40", "score_40-60", "score_60-80", "score_80+"]
    bins = []
    for edge_low, edge_high, bin_name in zip(bin_edges[:-1], bin_edges[1:], bin_labels):
        indices = [i for i, s in enumerate(raw_scores) if edge_low <= abs(s) < edge_high]
        if not indices:
            continue
        subset_preds = [predictions[i] for i in indices]
        subset_actuals = [actuals[i] for i in indices]
        subset_scores = [raw_scores[i] for i in indices]
        count = len(indices)
        if count == 0:
            continue
        expected_sum = 0.0
        observed_sum = 0.0
        for pred, actual, score in zip(subset_preds, subset_actuals, subset_scores):
            probs = _prediction_probs_from_score(score, pred)
            expected_sum += probs[pred]
            observed_sum += 1.0 if pred == actual else 0.0
        expected_freq = expected_sum / count
        observed_freq = observed_sum / count
        bins.append({
            "bin": bin_name,
            "expected_freq": round(expected_freq, 4),
            "observed_freq": round(observed_freq, 4),
            "count": count,
            "abs_gap": round(abs(expected_freq - observed_freq), 4),
        })
    return bins


def _momentum_prediction_from_hist(hist_navs, horizon: int, threshold: float) -> str:
    """Simple momentum baseline：仅使用 hist 内数据，无未来信息泄漏"""
    if len(hist_navs) <= horizon:
        return "sideways"
    prev_return = (hist_navs[-1] / hist_navs[-1 - horizon] - 1) * 100
    if prev_return > threshold:
        return "up"
    elif prev_return < -threshold:
        return "down"
    else:
        return "sideways"


def _accuracy(predictions: List[str], actuals: List[str]) -> float:
    """计算预测方向准确率（%）"""
    n = len(predictions)
    if n == 0:
        return 0.0
    return sum(p == a for p, a in zip(predictions, actuals)) / n * 100


def _calc_hit_by_confidence(
    predictions: List[str],
    actuals: List[str],
    realized_returns: List[float],
) -> Dict[str, Optional[float]]:
    """按置信度分组计算命中率"""
    n = len(predictions)
    if n < 10:
        return {"high": None, "medium": None, "low": None}

    ret_arr = np.abs(np.array(realized_returns, dtype=float))
    high_thresh = float(np.percentile(ret_arr, 75)) if len(ret_arr) > 0 else 0
    low_thresh = float(np.percentile(ret_arr, 25)) if len(ret_arr) > 0 else 0

    high_hits: List[bool] = []
    med_hits: List[bool] = []
    low_hits: List[bool] = []

    for i, (pred, actual) in enumerate(zip(predictions, actuals)):
        if i >= len(realized_returns):
            break
        ret_abs = abs(realized_returns[i]) if realized_returns[i] is not None else 0
        if ret_abs >= high_thresh:
            high_hits.append(pred == actual)
        elif ret_abs <= low_thresh:
            low_hits.append(pred == actual)
        else:
            med_hits.append(pred == actual)

    def hit_rate(hits: List[bool]) -> Optional[float]:
        if not hits:
            return None
        return round(sum(hits) / len(hits) * 100, 2)

    return {
        "high": hit_rate(high_hits),
        "medium": hit_rate(med_hits),
        "low": hit_rate(low_hits),
    }


def _assess_quality(periods: Dict[str, Any]) -> Tuple[str, bool]:
    """
    保守评估概率质量和是否已校准。

    条件：
    - 样本不足 → low / false
    - rule_acc < best_baseline_acc → low / false
    - brier_score 过高（>0.4）→ low / false
    - actual_distribution 极端偏向 sideways（>80%）→ 最多 medium
    - 至少两个周期 rule_vs_best_baseline_edge >= 0 且样本充足 → medium
    - 多数周期 rule_vs_best_baseline_edge > 3 且 brier_score 合理 → high
    - 不允许只因为 sample_size 多就 high
    """
    total_samples = 0
    num_periods = 0
    brier_too_high = False
    sideways_extreme = False
    edges = []
    good_edge_count = 0
    strong_edge_count = 0

    for pr in periods.values():
        n = pr.get("sample_size", 0)
        if n is None or n < 10:
            continue
        total_samples += n
        num_periods += 1

        bs = pr.get("brier_score")
        if bs is not None and bs > 0.4:
            brier_too_high = True

        ad = pr.get("actual_distribution", {})
        if ad and ad.get("sideways_pct", 0) > 80:
            sideways_extreme = True

        bc = pr.get("baseline_comparison", {})
        edge = bc.get("rule_vs_best_baseline_edge")
        if edge is not None:
            edges.append(edge)
            if edge >= 0:
                good_edge_count += 1
            if edge > 3:
                strong_edge_count += 1

    # 样本不足
    if num_periods < 2 or total_samples < 30:
        return "low", False

    # Brier score 过高 → low
    if brier_too_high:
        return "low", False

    # rule_acc < best_baseline_acc 在所有周期 → low
    if good_edge_count == 0:
        return "low", False

    # 极端偏向 sideways → 最多 medium
    if sideways_extreme:
        if strong_edge_count >= num_periods / 2 and total_samples >= 60:
            return "medium", total_samples >= 30
        return "low", total_samples >= 30

    # 至少两个周期 edge >= 0 且样本充足 → medium
    if good_edge_count >= 2 and total_samples >= 60:
        quality = "medium"
        calibrated = total_samples >= 30
    else:
        quality = "low"
        calibrated = False

    # 多数周期 edge > 3 且 brier 合理 → high
    if strong_edge_count > num_periods / 2 and not brier_too_high and total_samples >= 120:
        quality = "high"
        calibrated = True

    return quality, calibrated


def _summarize_uncertainties(result: Dict[str, Any]) -> List[str]:
    """汇总主要不确定因素"""
    unc = []
    periods = result.get("periods", {})

    # 波动率相关（用 threshold 代理判断）
    for key, pr in periods.items():
        thresh = pr.get("threshold_used", 0)
        if thresh and thresh > 5:
            unc.append(f"{key}周期阈值较高（{thresh}%），反映波动较大，方向预测误差可能放大")
            break

    # 样本不足
    if any(pr.get("sample_size", 0) < 30 for pr in periods.values() if pr.get("sample_size") is not None):
        unc.append("部分周期回测样本较少，历史准确率参考价值有限")

    # 低准确率
    low_acc_count = sum(
        1 for pr in periods.values()
        if pr.get("directional_accuracy") is not None and pr.get("directional_accuracy") < 50
    )
    if low_acc_count >= 2:
        unc.append("多个周期方向准确率低于随机猜测，需谨慎参考")

    # 极端 sideways
    for key, pr in periods.items():
        ad = pr.get("actual_distribution", {})
        if ad and ad.get("sideways_pct", 0) > 80:
            unc.append(f"{key}周期实际走势极端偏向震荡，方向预测区分度可能不足")
            break

    if not unc:
        unc.append("回测样本量尚可，但历史表现不代表未来")

    return unc


def _detect_regime(hist_navs: np.ndarray) -> str:
    """检测市场体制：trending / mean_reverting / high_volatility"""
    if len(hist_navs) < 20:
        return "mean_reverting"

    returns = np.diff(hist_navs) / hist_navs[:-1]

    # 波动率分位判断高波动
    daily_vol = float(np.std(returns)) if len(returns) >= 5 else FALLBACK_DAILY_VOL
    if np.isnan(daily_vol) or daily_vol <= 0:
        daily_vol = FALLBACK_DAILY_VOL
    annual_vol = daily_vol * np.sqrt(250) * 100
    if annual_vol > 35:
        return "high_volatility"

    # MA 排列判断趋势 vs 震荡
    ma_short = float(np.mean(hist_navs[-5:]))
    ma_mid = float(np.mean(hist_navs[-10:])) if len(hist_navs) >= 10 else ma_short
    ma_long = float(np.mean(hist_navs[-20:])) if len(hist_navs) >= 20 else ma_mid

    # 趋势强度：短期斜率 vs 长期
    if len(hist_navs) >= 20:
        recent_slope = (hist_navs[-1] - hist_navs[-5]) / hist_navs[-5] * 100
        long_slope = (hist_navs[-10] - hist_navs[-20]) / hist_navs[-20] * 100

        # MA 多头排列 + 趋势斜率同向 → trending
        if ma_short > ma_mid > ma_long:
            if abs(recent_slope) > 0.3:
                if (recent_slope > 0 and long_slope > -0.5) or (recent_slope < 0 and long_slope < 0.5):
                    return "trending"
        elif ma_short < ma_mid < ma_long:
            if abs(recent_slope) > 0.3:
                return "trending"

    # RSI 极端值附近 + MA 缠绕 → mean_reverting
    if len(hist_navs) >= 14:
        deltas = np.diff(hist_navs[-15:])
        gains = np.sum(deltas[deltas > 0]) if np.any(deltas > 0) else 0.0
        losses = -np.sum(deltas[deltas < 0]) if np.any(deltas < 0) else 1e-10
        rsi = 100.0 - (100.0 / (1.0 + gains / losses))
        ma_ratio = abs(ma_short - ma_long) / ma_long * 100 if ma_long > 0 else 0
        if ma_ratio < 1.0:
            return "mean_reverting"
        if rsi < 25 or rsi > 75:
            if ma_ratio < 2.0:
                return "mean_reverting"

    return "trending"


def _compute_score_stats(
    raw_scores: List[float], predictions: List[str], actuals: List[str]
) -> Dict[str, Any]:
    """Compute score distribution stats and per-bucket accuracy"""
    if not raw_scores:
        return {}
    scores_arr = np.array(raw_scores)
    buckets = [(-200, -60), (-60, -40), (-40, -20), (-20, 0), (0, 20), (20, 40), (40, 60), (60, 200)]
    bucket_stats = []
    for low, high in buckets:
        indices = [i for i, s in enumerate(raw_scores) if low <= s < high]
        if not indices:
            continue
        n = len(indices)
        correct = sum(1 for i in indices if predictions[i] == actuals[i])
        acc = round(correct / n * 100, 1) if n > 0 else 0
        bucket_stats.append({
            "range": f"{low} to {high}",
            "count": n,
            "pct": round(n / len(raw_scores) * 100, 1),
            "accuracy": acc,
        })
    return {
        "mean": round(float(scores_arr.mean()), 2),
        "std": round(float(scores_arr.std()), 2),
        "p10": round(float(np.percentile(scores_arr, 10)), 2),
        "p50": round(float(np.percentile(scores_arr, 50)), 2),
        "p90": round(float(np.percentile(scores_arr, 90)), 2),
        "buckets": bucket_stats,
    }


def _compute_calibration_curve(periods: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从回测各周期的 raw_score_stats 中提取校准曲线"""
    curve = []
    for key, pr in periods.items():
        stats = pr.get("raw_score_stats", {})
        for b in stats.get("buckets", []):
            curve.append({
                "period": key,
                "score_range": b["range"],
                "accuracy": b["accuracy"],
                "count": b["count"],
            })
    return curve


def _empty_period_result(threshold: float, sample_size: int) -> Dict[str, Any]:
    return {
        "sample_size": sample_size,
        "directional_accuracy": None,
        "confusion_matrix": {"up": {}, "sideways": {}, "down": {}},
        "brier_score": None,
        "calibration_bins": [],
        "hit_rate_by_confidence": {"high": None, "medium": None, "low": None},
        "return_stats": {"mean": None, "median": None, "p10": None, "p90": None},
        "threshold_used": round(threshold, 3),
        "threshold_median": round(threshold, 3),
        "baseline_comparison": {
            "always_sideways_acc": None,
            "simple_momentum_acc": None,
            "rule_acc": None,
            "best_baseline_acc": None,
            "rule_vs_best_baseline_edge": None,
        },
        "actual_distribution": {"up_pct": 0, "sideways_pct": 0, "down_pct": 0},
    }
