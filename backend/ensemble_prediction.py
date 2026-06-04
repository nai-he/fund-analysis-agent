"""
集成学习预测模块
使用多个模型投票，提升预测准确性
"""
import logging
from typing import Dict, Any, List
import numpy as np

logger = logging.getLogger(__name__)


def ensemble_prediction(
    llm_prediction: Dict[str, Any],
    rule_prediction: Dict[str, Any],
    indicators: Dict[str, Any],
) -> Dict[str, Any]:
    """
    集成多个模型的预测结果

    模型权重：
    - LLM预测: 60% (理解复杂模式)
    - 规则模型: 20% (稳定基线)
    - 超买超卖信号: 20% (短线反转)
    """

    ensemble_periods = {}

    for period_key in ["1d", "3d", "7d", "30d"]:
        llm_period = llm_prediction.get("periods", {}).get(period_key, {})
        rule_period = rule_prediction.get("periods", {}).get(period_key, {})

        if not llm_period:
            # LLM失败，使用规则模型
            ensemble_periods[period_key] = rule_period
            continue

        # 获取各模型的预测
        llm_prob = llm_period.get("up_probability", 50)
        rule_prob = rule_period.get("up_probability", 50) if rule_period else 50

        # 超买超卖信号
        oversold_prob = _oversold_signal_probability(indicators, int(period_key[:-1]))

        # 加权融合
        ensemble_prob = (
            0.60 * llm_prob +
            0.20 * rule_prob +
            0.20 * oversold_prob
        )

        # 置信度调整
        confidence = _calculate_ensemble_confidence(
            llm_period.get("confidence", "低"),
            ensemble_prob,
            indicators
        )

        # 方向判断
        if ensemble_prob >= 58:
            direction = "up"
        elif ensemble_prob <= 42:
            direction = "down_or_flat"
        else:
            direction = "uncertain"

        # 综合理由
        reasons = []
        if llm_period.get("main_reasons"):
            reasons.append(f"LLM: {llm_period['main_reasons'][0][:60]}")

        # 添加集成信号
        if abs(ensemble_prob - llm_prob) > 10:
            reasons.append(f"集成修正: 综合多模型后概率调整为{ensemble_prob:.1f}%")

        ensemble_periods[period_key] = {
            "period_days": int(period_key[:-1]),
            "predicted_direction": direction,
            "direction_label": _direction_label(direction),
            "up_probability": round(ensemble_prob, 1),
            "down_or_flat_probability": round(100 - ensemble_prob, 1),
            "confidence": confidence,
            "main_reasons": reasons,
            "method": "ensemble_prediction",
            "model_weights": {
                "llm": 0.60,
                "rule": 0.20,
                "oversold_signal": 0.20,
            },
            "component_probs": {
                "llm": llm_prob,
                "rule": rule_prob,
                "oversold": oversold_prob,
            }
        }

    return {
        "status": "ok",
        "model_basis": "ensemble_learning",
        "quality": "high",
        "periods": ensemble_periods,
        "disclaimer": "集成多模型预测，仅供参考。",
    }


def _oversold_signal_probability(indicators: Dict[str, Any], period_days: int) -> float:
    """
    基于超买超卖信号计算上涨概率
    这是一个纯技术指标的反转策略
    """
    rsi = indicators.get("rsi_6" if period_days <= 3 else "rsi_14", 50)
    bb_pos = indicators.get("bb_position", 50)
    pos_30d = indicators.get("position_in_30d_range", 50) if "position_in_30d_range" in indicators else 50

    prob = 50.0

    # RSI超卖/超买
    if rsi < 25:
        prob += 25  # 强烈超卖
    elif rsi < 30:
        prob += 18
    elif rsi < 35:
        prob += 10
    elif rsi > 75:
        prob -= 25  # 强烈超买
    elif rsi > 70:
        prob -= 18
    elif rsi > 65:
        prob -= 10

    # 布林带位置
    if bb_pos < 5:
        prob += 15
    elif bb_pos < 10:
        prob += 10
    elif bb_pos > 95:
        prob -= 15
    elif bb_pos > 90:
        prob -= 10

    # 区间位置
    if pos_30d < 15:
        prob += 8
    elif pos_30d < 20:
        prob += 5
    elif pos_30d > 85:
        prob -= 8
    elif pos_30d > 80:
        prob -= 5

    return max(10, min(90, prob))


def _calculate_ensemble_confidence(
    llm_confidence: str,
    ensemble_prob: float,
    indicators: Dict[str, Any]
) -> str:
    """
    计算集成模型的置信度
    考虑：LLM置信度、概率偏离程度、技术指标一致性
    """
    # 概率偏离中性的程度
    prob_distance = abs(ensemble_prob - 50)

    # RSI极端程度
    rsi = indicators.get("rsi_14", 50)
    rsi_extreme = max(abs(rsi - 30), abs(rsi - 70)) if rsi < 30 or rsi > 70 else 0

    # 布林带极端程度
    bb_pos = indicators.get("bb_position", 50)
    bb_extreme = max(abs(bb_pos - 10), abs(bb_pos - 90)) if bb_pos < 10 or bb_pos > 90 else 0

    # 综合评分
    confidence_score = 0

    if llm_confidence == "高":
        confidence_score += 3
    elif llm_confidence == "中":
        confidence_score += 2
    else:
        confidence_score += 1

    if prob_distance > 15:
        confidence_score += 2
    elif prob_distance > 10:
        confidence_score += 1

    if rsi_extreme > 0 or bb_extreme > 0:
        confidence_score += 1

    # 判断
    if confidence_score >= 5:
        return "高"
    elif confidence_score >= 3:
        return "中"
    else:
        return "低"


def _direction_label(direction: str) -> str:
    return {
        "up": "偏上涨",
        "down_or_flat": "偏不涨",
        "uncertain": "不确定"
    }.get(direction, "不确定")
