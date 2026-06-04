"""
Final decision aggregation layer.
Synthesizes signals from prediction, risk, forecast, and decision_advice
into a single conservative conclusion — not investment advice.
"""
from typing import Optional


def build_final_decision(
    fund: Optional[dict],
    risk: Optional[dict],
    forecast: Optional[dict],
    prediction: Optional[dict],
    decision_advice: Optional[dict],
    position: Optional[dict] = None,
) -> dict:
    """Aggregate multi-source signals into one conservative final conclusion."""

    risk_score = _safe_float(risk, "risk_score", None)
    periods = (prediction or {}).get("periods") or {}
    pred_7d = periods.get("7d") or {}
    pred_30d = periods.get("30d") or {}
    pred_quality = (prediction or {}).get("quality", "low")

    has_position = _has_position(position)

    # Extract key signals
    p7d_up = pred_7d.get("up_probability", 50)
    p30d_up = pred_30d.get("up_probability", 50)
    p7d_edge = pred_7d.get("has_positive_edge", False)
    p30d_edge = pred_30d.get("has_positive_edge", False)
    p7d_conf = pred_7d.get("confidence", "低")
    p30d_conf = pred_30d.get("confidence", "低")
    p7d_dir = pred_7d.get("predicted_direction", "uncertain")
    p30d_dir = pred_30d.get("predicted_direction", "uncertain")

    # Determine if prediction has any useful edge
    both_low_or_no_edge = (
        (not p7d_edge and not p30d_edge)
        or (p7d_conf == "低" and p30d_conf == "低")
        or pred_quality == "low"
    )

    why: list[str] = []
    watch: list[str] = []
    warning: list[str] = []

    # ---- Step 1: determine direction ----
    if both_low_or_no_edge:
        direction = "uncertain"
        direction_label = "不确定"
        confidence = "低"
        why.append("历史验证未显示稳定预测优势，当前方向难以判断。")
    elif (
        p7d_dir == "up"
        and p30d_dir == "up"
        and (p7d_conf in ("中", "高") or p30d_conf in ("中", "高"))
        and (risk_score is not None and risk_score < 60)
    ):
        direction = "up"
        direction_label = "偏涨"
        confidence = p7d_conf if p7d_conf == "高" else (p30d_conf if p30d_conf == "高" else "中")
        why.append("7天和30天预测方向均偏涨，风险评分处于可接受区间。")
    elif (p7d_dir in ("down_or_flat", "uncertain") or p30d_dir in ("down_or_flat", "uncertain")) and (
        risk_score is not None and risk_score >= 60
    ):
        direction = "down"
        direction_label = "偏跌"
        confidence = "中"
        why.append("短期或中期预测偏弱，且风险评分偏高，走势可能承压。")
    elif p7d_dir == "up" or p30d_dir == "up":
        direction = "neutral"
        direction_label = "震荡"
        confidence = "低"
        why.append("部分周期偏涨但信号不够一致，整体偏震荡。")
    else:
        direction = "uncertain"
        direction_label = "不确定"
        confidence = "低"
        why.append("多周期信号不一致，方向不明确。")

    # ---- Step 2: determine action ----
    if has_position and risk_score is not None and risk_score >= 70:
        action = "reduce"
        action_label = "降低仓位"
        warning.append("当前持仓且风险评分较高（≥70），不建议追加仓位。")
    elif has_position and risk_score is not None and risk_score >= 60:
        action = "hold"
        action_label = "继续持有"
        watch.append("关注风险评分变化，若持续上升可考虑降低仓位。")
    elif not has_position and risk_score is not None and risk_score >= 70:
        action = "avoid"
        action_label = "暂不参与"
        warning.append("风险评分较高（≥70），暂不适合新开仓。")
    elif not has_position and both_low_or_no_edge:
        action = "observe"
        action_label = "观察"
        why.append("预测优势不足，建议等待更明确信号。")
    elif direction == "up" and (risk_score is None or risk_score < 55):
        action = "buy_watch"
        action_label = "可小额关注"
    elif direction == "down":
        if has_position:
            action = "reduce"
            action_label = "降低仓位"
        else:
            action = "observe"
            action_label = "观察"
    else:
        action = "observe"
        action_label = "观察"

    # ---- Step 3: add context from risk/warnings ----
    if risk_score is not None:
        if risk_score >= 75:
            warning.append(f"综合风险评分 {risk_score}，处于高位，需警惕回撤风险。")
        elif risk_score >= 60:
            watch.append(f"风险评分 {risk_score} 偏高，需持续关注。")

    if pred_7d.get("warning"):
        warning.append(pred_7d["warning"])
    if pred_30d.get("warning"):
        w = pred_30d["warning"]
        if w not in warning:
            warning.append(w)

    # Borrow key reasons from decision_advice if available
    da = decision_advice or {}
    if da.get("risk_warnings"):
        for w in da["risk_warnings"][:2]:
            if w not in warning:
                warning.append(w)

    # ---- Step 4: build headline (≤25 汉字) ----
    headline = _build_headline(direction, action, risk_score)
    summary = _build_summary(action, direction_label, confidence, risk_score, has_position)

    return {
        "headline": headline,
        "summary": summary,
        "direction": direction,
        "direction_label": direction_label,
        "action": action,
        "action_label": action_label,
        "confidence": confidence,
        "up_probability_7d": p7d_up if isinstance(p7d_up, (int, float)) else None,
        "up_probability_30d": p30d_up if isinstance(p30d_up, (int, float)) else None,
        "risk_score": risk_score,
        "why": why[:5],
        "watch": watch[:4],
        "warning": warning[:4],
        "disclaimer": "仅供个人研究参考，不构成投资建议。",
    }


def _build_headline(direction: str, action: str, risk_score: Optional[float]) -> str:
    """Build a one-sentence headline ≤25 Chinese characters."""
    if direction == "up" and action == "buy_watch":
        return "短期偏涨，可小额关注"
    if direction == "up":
        return "走势偏强，可关注但需控仓"
    if direction == "down" and action == "reduce":
        return "当前偏弱，可考虑降低仓位"
    if direction == "down":
        return "走势偏弱，建议暂观察"
    if direction == "neutral":
        return "当前偏震荡，等待方向明朗"
    if action == "avoid":
        return "风险较高，暂不适合参与"
    if action == "reduce":
        return "风险偏高，可考虑降低仓位"
    if risk_score is not None and risk_score >= 70:
        return "风险评分较高，建议谨慎"
    return "当前偏观察，不适合追买"


def _build_summary(
    action: str,
    direction_label: str,
    confidence: str,
    risk_score: Optional[float],
    has_position: bool,
) -> str:
    """Build a short plain-language readout for the top card."""
    position_text = "已有持仓" if has_position else "未持有"
    risk_text = f"风险分 {risk_score:g}" if risk_score is not None else "风险分未知"

    action_hint = {
        "buy_watch": "可列入小额关注候选，仍需分批和控仓。",
        "hold": "以继续观察和控制仓位为主。",
        "reduce": "优先评估是否降低仓位，避免继续追加。",
        "avoid": "更适合先放入观察名单，暂不新开仓。",
        "observe": "先等待更清晰信号，不急于参与。",
    }.get(action, "先观察，不急于参与。")

    return f"{position_text}，方向{direction_label}，{risk_text}，置信度{confidence}。{action_hint}"


def _safe_float(d: Optional[dict], key: str, default=None):
    if d is None:
        return default
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _has_position(position: Optional[dict]) -> bool:
    if position is None:
        return False
    return any(
        position.get(k) is not None and position.get(k) > 0
        for k in ("cost_nav", "holding_amount", "holding_units")
    )
