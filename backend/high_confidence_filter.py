"""
高置信度过滤器 —— "小资金、高胜率优先、少出手"

核心原则：
- 默认动作是 wait（等待），不是 buy
- 只有所有硬条件全部满足才允许 small_buy
- 任何条件不满足都输出 wait，并在 blockers 里说明原因
- 风险过高直接输出 avoid
- 只参考 7d 和 30d 周期的预测信号
"""

from typing import Optional, Dict, Any, List


def build_high_confidence_decision(
    fund: Optional[dict] = None,
    metrics: Optional[dict] = None,
    risk: Optional[dict] = None,
    forecast: Optional[dict] = None,
    prediction: Optional[dict] = None,
    backtest: Optional[dict] = None,
    position: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    构建高置信度决策，返回三类动作之一：wait / avoid / small_buy
    默认永远为 wait，除非所有硬条件同时满足。
    """

    reasons: List[str] = []
    blockers: List[str] = []
    risk_controls: List[str] = [
        "分批买入，不一次性建仓",
        "单只基金总仓位不超过总资金的10%",
        "如果信号失效（7d/30d预测转负），立即停止加仓",
    ]
    disclaimer = "仅供个人研究参考，不构成投资建议。历史表现不代表未来。"

    # ---- 0. 数据存在性检查 ----
    if prediction is None:
        return _result("wait", "low", 0, 0, [], ["缺少预测数据，无法判断"], risk_controls, disclaimer)

    pred_status = prediction.get("status", "")
    if pred_status == "unavailable":
        return _result("avoid", "low", 0, 0, [], ["预测数据不足，不适合参与"], risk_controls, disclaimer)

    pred_periods = prediction.get("periods") or {}
    pred_7d = pred_periods.get("7d") or {}
    pred_30d = pred_periods.get("30d") or {}

    if not pred_7d or not pred_30d:
        return _result("wait", "low", 0, 0, [], ["缺少 7d 或 30d 预测数据"], risk_controls, disclaimer)

    # ---- 1. avoid 优先判断 ----
    avoid_reason = _check_avoid(risk, metrics, pred_7d, pred_30d, pred_status)
    if avoid_reason:
        return _result("avoid", "low", 0, 0, [], [avoid_reason], risk_controls, disclaimer)

    # 专属基金的 30d 样本外强信号允许更低仓位试探，不要求 7d 同时触发。
    swing_result = _try_specific_30d_swing(
        prediction,
        pred_30d,
        risk,
        metrics,
        risk_controls,
        disclaimer,
    )
    if swing_result is not None:
        return swing_result

    # ---- 2. 硬条件逐一检查 ----
    checks = _run_hard_gates(prediction, pred_7d, pred_30d, risk, metrics, backtest)
    passed = [c for c in checks if c["pass"]]
    failed = [c for c in checks if not c["pass"]]

    for c in passed:
        reasons.append(c["reason"])
    for c in failed:
        blockers.append(c["reason"])

    score = _compute_score(passed, failed, risk, metrics)

    # ---- 3. 决定动作 ----
    if len(failed) == 0:
        # 所有硬条件通过
        conf = _overall_confidence(pred_7d, pred_30d)
        max_pct = 10 if conf == "high" else 5
        return _result("small_buy", conf, max_pct, score, reasons, blockers, risk_controls, disclaimer)

    # 有失败项
    return _result("wait", "low", 0, score, reasons, blockers, risk_controls, disclaimer)


def _check_avoid(
    risk: Optional[dict],
    metrics: Optional[dict],
    pred_7d: dict,
    pred_30d: dict,
    pred_status: str,
) -> Optional[str]:
    """检查是否触发 avoid 条件，返回原因字符串或 None"""

    risk_score = _safe_num(risk, "risk_score") if risk else 0
    vol = _safe_num(metrics, "volatility_30d") if metrics else 0
    dd = _safe_num(metrics, "max_drawdown_30d_calendar") if metrics else 0

    if risk_score >= 70:
        return f"风险评分过高（{risk_score}），不适合参与"
    if vol >= 40:
        return f"波动率过高（{vol}%），不适合参与"
    if dd >= 15:
        return f"近30日最大回撤过大（{dd}%），不适合参与"

    dir_7d = pred_7d.get("predicted_direction", "")
    dir_30d = pred_30d.get("predicted_direction", "")
    edge_7d = pred_7d.get("has_positive_edge", False)
    edge_30d = pred_30d.get("has_positive_edge", False)

    if dir_7d == "down_or_flat" and dir_30d == "down_or_flat":
        return "7d 和 30d 均预测偏不涨，不适合参与"
    if (not edge_7d) and (not edge_30d) and risk_score >= 60:
        return "7d/30d 无正边际且风险评分偏高，不适合参与"
    if pred_status == "unavailable":
        return "数据样本不足，不适合参与"

    return None


def _try_specific_30d_swing(
    prediction: dict,
    pred_30d: dict,
    risk: Optional[dict],
    metrics: Optional[dict],
    risk_controls: List[str],
    disclaimer: str,
) -> Optional[Dict[str, Any]]:
    """Allow a tiny 30d trial when a specific-fund signal passes out-of-sample checks."""
    specific = prediction.get("specific_training") or {}
    if not specific.get("enabled"):
        return None

    risk_score = _safe_num(risk, "risk_score") if risk else 50
    vol = _safe_num(metrics, "volatility_30d") if metrics else 0
    dd = _safe_num(metrics, "max_drawdown_30d_calendar") if metrics else 0
    rsi = _safe_num(metrics, "rsi_14") if metrics else 50
    pos_range = _safe_num(metrics, "position_in_30d_range") if metrics else 50

    selective_hit = _safe_num(pred_30d, "selective_hit_rate")
    selective_count = _safe_num(pred_30d, "selective_signal_count")
    validation_hit = _safe_num(pred_30d, "selective_validation_hit_rate")
    validation_count = _safe_num(pred_30d, "selective_validation_signal_count")
    cv_pass_rate = _safe_num(pred_30d, "selective_cv_pass_rate")
    lower_bound = _safe_num(pred_30d, "selective_hit_rate_lower_bound")
    avg_return = _safe_num(pred_30d, "selective_avg_return")
    profit_factor = _safe_num(pred_30d, "selective_profit_factor")

    checks = [
        _gate(prediction.get("status") == "ok", "预测状态正常", "预测状态异常"),
        _gate(pred_30d.get("current_passes_selective_threshold") is True, "30d 专训当前触发", "30d 专训当前未触发"),
        _gate(pred_30d.get("selective_signal_valid") is True, "30d 专训规则有效", "30d 专训规则未通过严格验证"),
        _gate(pred_30d.get("selective_validation_passed") is True, "30d 样本外验证通过", "30d 样本外验证未通过"),
        _gate(pred_30d.get("selective_cv_passed") is True, f"30d 多折验证通过率 {cv_pass_rate}%", "30d 多折验证未通过"),
        _gate(lower_bound >= 55, f"30d 命中率置信下界 {lower_bound}%", "30d 命中率置信下界不足"),
        _gate(selective_hit >= 80 and selective_count >= 10, f"30d 精筛命中率 {selective_hit}%，样本 {selective_count}", "30d 精筛命中率或样本不足"),
        _gate(validation_hit >= 80 and validation_count >= 3, f"30d 样本外命中率 {validation_hit}%，样本 {validation_count}", "30d 样本外样本不足或命中率不足"),
        _gate(avg_return > 0 and profit_factor >= 1.3, f"收益质量达标：均收 {avg_return}%，收益因子 {profit_factor}", "收益质量不足"),
        _gate(risk_score < 60, f"风险评分可控（{risk_score}）", f"风险评分偏高（{risk_score}，需要 < 60）"),
        _gate(vol <= 35, f"波动率可接受（{vol}%）", f"波动率偏高（{vol}%，需要 ≤ 35%）"),
        _gate(dd <= 12, f"近30日回撤可接受（{dd}%）", f"近30日回撤偏大（{dd}%，需要 ≤ 12%）"),
        _gate(pos_range < 85, f"未处于极端高位（{pos_range}%）", f"处于极端高位（{pos_range}%，需要 < 85%）"),
        _gate(rsi < 75, f"RSI 未极端超买（{rsi}）", f"RSI 极端超买（{rsi}，需要 < 75）"),
    ]
    failed = [c for c in checks if not c["pass"]]
    if failed:
        return None

    reasons = [c["reason"] for c in checks if c["pass"]]
    controls = [
        "这是30日专训试探信号，不是短线满仓信号",
        "首次最多投入总资金的3%，不追涨追加",
        "若30d专训不再触发或风险评分升高，停止加仓",
        *risk_controls,
    ]
    return _result("small_buy", "medium", 3, 88, reasons, [], controls, disclaimer)


def _run_hard_gates(
    prediction: dict,
    pred_7d: dict,
    pred_30d: dict,
    risk: Optional[dict],
    metrics: Optional[dict],
    backtest: Optional[dict],
) -> list:
    """运行硬条件检查，返回包含 {pass, reason} 的列表"""

    risk_score = _safe_num(risk, "risk_score") if risk else 50
    vol = _safe_num(metrics, "volatility_30d") if metrics else 0
    dd = _safe_num(metrics, "max_drawdown_30d_calendar") if metrics else 0
    rsi = _safe_num(metrics, "rsi_14") if metrics else 50
    pos_range = _safe_num(metrics, "position_in_30d_range") if metrics else 50

    checks = []

    # 1. prediction.status == "ok"
    checks.append(_gate(
        prediction.get("status") == "ok",
        "预测状态正常",
        f"预测状态异常：{prediction.get('status', 'unknown')}",
    ))

    # 2. prediction.quality != "low"
    pred_quality = prediction.get("quality", "low")
    checks.append(_gate(
        pred_quality != "low",
        f"预测质量可接受（{pred_quality}）",
        f"预测质量为 low，不可靠",
    ))

    # 3. 7d predicted_direction == "up"
    dir_7d = pred_7d.get("predicted_direction", "")
    checks.append(_gate(
        dir_7d == "up",
        f"7d 预测方向：偏上涨",
        f"7d 预测方向：{dir_7d}（需要 up）",
    ))

    # 4. 30d predicted_direction == "up"
    dir_30d = pred_30d.get("predicted_direction", "")
    checks.append(_gate(
        dir_30d == "up",
        f"30d 预测方向：偏上涨",
        f"30d 预测方向：{dir_30d}（需要 up）",
    ))

    # 5. 7d confidence 至少 medium
    conf_7d = pred_7d.get("confidence", "低")
    checks.append(_gate(
        conf_7d in ("高", "中"),
        f"7d 置信度达标（{conf_7d}）",
        f"7d 置信度不足（{conf_7d}，需要 ≥ 中）",
    ))

    # 6. 30d confidence 至少 medium
    conf_30d = pred_30d.get("confidence", "低")
    checks.append(_gate(
        conf_30d in ("高", "中"),
        f"30d 置信度达标（{conf_30d}）",
        f"30d 置信度不足（{conf_30d}，需要 ≥ 中）",
    ))

    # 7. 7d has_positive_edge
    edge_7d = pred_7d.get("has_positive_edge", False)
    checks.append(_gate(
        edge_7d is True,
        "7d 有正边际优势",
        "7d 无正边际优势",
    ))

    # 8. 30d has_positive_edge
    edge_30d = pred_30d.get("has_positive_edge", False)
    checks.append(_gate(
        edge_30d is True,
        "30d 有正边际优势",
        "30d 无正边际优势",
    ))

    # 9. 7d edge_vs_baseline >= 3
    edge_val_7d = _safe_num(pred_7d, "edge_vs_baseline")
    checks.append(_gate(
        edge_val_7d >= 3,
        f"7d 边际优势充足（{edge_val_7d}%）",
        f"7d 边际优势不足（{edge_val_7d}%，需要 ≥ 3%）",
    ))

    # 10. 30d edge_vs_baseline >= 3
    edge_val_30d = _safe_num(pred_30d, "edge_vs_baseline")
    checks.append(_gate(
        edge_val_30d >= 3,
        f"30d 边际优势充足（{edge_val_30d}%）",
        f"30d 边际优势不足（{edge_val_30d}%，需要 ≥ 3%）",
    ))

    # 11. 7d historical_hit_rate >= 55
    hit_7d = _safe_num(pred_7d, "historical_hit_rate")
    checks.append(_gate(
        hit_7d >= 55,
        f"7d 历史命中率达标（{hit_7d}%）",
        f"7d 历史命中率不足（{hit_7d}%，需要 ≥ 55%）",
    ))

    # 12. 30d historical_hit_rate >= 55
    hit_30d = _safe_num(pred_30d, "historical_hit_rate")
    checks.append(_gate(
        hit_30d >= 55,
        f"30d 历史命中率达标（{hit_30d}%）",
        f"30d 历史命中率不足（{hit_30d}%，需要 ≥ 55%）",
    ))

    # 12.5. 高胜率精筛信号必须有效并且当前触发
    selective_hit_7d = _safe_num(pred_7d, "selective_hit_rate")
    selective_hit_30d = _safe_num(pred_30d, "selective_hit_rate")
    selective_count_7d = _safe_num(pred_7d, "selective_signal_count")
    selective_count_30d = _safe_num(pred_30d, "selective_signal_count")
    selective_edge_7d = _safe_num(pred_7d, "selective_edge_vs_baseline")
    selective_edge_30d = _safe_num(pred_30d, "selective_edge_vs_baseline")
    checks.append(_gate(
        pred_7d.get("current_passes_selective_threshold") is True,
        f"7d 当前触发高胜率精筛（命中率 {selective_hit_7d}%，样本 {selective_count_7d}）",
        "7d 当前未触发高胜率精筛信号，等待更强信号",
    ))
    checks.append(_gate(
        pred_30d.get("current_passes_selective_threshold") is True,
        f"30d 当前触发高胜率精筛（命中率 {selective_hit_30d}%，样本 {selective_count_30d}）",
        "30d 当前未触发高胜率精筛信号，等待更强信号",
    ))
    checks.append(_gate(
        selective_hit_7d >= 60 and selective_count_7d >= 20 and selective_edge_7d >= 3,
        f"7d 精筛胜率达标（{selective_hit_7d}%，优势 {selective_edge_7d}%）",
        f"7d 精筛胜率不足（命中率 {selective_hit_7d}%，样本 {selective_count_7d}，优势 {selective_edge_7d}%）",
    ))
    checks.append(_gate(
        selective_hit_30d >= 60 and selective_count_30d >= 20 and selective_edge_30d >= 3,
        f"30d 精筛胜率达标（{selective_hit_30d}%，优势 {selective_edge_30d}%）",
        f"30d 精筛胜率不足（命中率 {selective_hit_30d}%，样本 {selective_count_30d}，优势 {selective_edge_30d}%）",
    ))

    # 13. risk_score < 55
    checks.append(_gate(
        risk_score < 55,
        f"风险评分可控（{risk_score}）",
        f"风险评分偏高（{risk_score}，需要 < 55）",
    ))

    # 14. volatility_30d <= 30
    checks.append(_gate(
        vol <= 30,
        f"波动率可控（{vol}%）",
        f"波动率偏高（{vol}%，需要 ≤ 30%）",
    ))

    # 15. max_drawdown_30d_calendar <= 8
    checks.append(_gate(
        dd <= 8,
        f"近30日最大回撤可控（{dd}%）",
        f"近30日最大回撤偏大（{dd}%，需要 ≤ 8%）",
    ))

    # 16. position_in_30d_range < 80
    checks.append(_gate(
        pos_range < 80,
        f"非近30日高位（区间位置 {pos_range}%）",
        f"处于近30日高位（区间位置 {pos_range}%，需要 < 80%），避免追涨",
    ))

    # 17. rsi_14 < 70
    checks.append(_gate(
        rsi < 70,
        f"RSI 非超买（{rsi}）",
        f"RSI 超买（{rsi}，需要 < 70）",
    ))

    # 回测质量：整体回测必须可接受，精筛信号只作为补充展示，不绕过验证
    if backtest:
        bt_quality = backtest.get("probability_quality", "low")
        checks.append(_gate(
            bt_quality != "low",
            f"回测质量可接受（{bt_quality}）",
            f"回测质量为 low，模型未证明优于基准",
        ))
    else:
        checks.append(_gate(
            False,
            "",
            "缺少回测数据，无法验证模型有效性",
        ))

    return checks


def _compute_score(
    passed: list,
    failed: list,
    risk: Optional[dict],
    metrics: Optional[dict],
) -> float:
    """计算 0-100 综合得分"""
    total = len(passed) + len(failed)
    if total == 0:
        return 0
    base = (len(passed) / total) * 80
    risk_penalty = max(0, (_safe_num(risk, "risk_score") if risk else 50) - 40) * 0.2
    score = max(0, min(100, base - risk_penalty))
    return round(score, 1)


def _overall_confidence(pred_7d: dict, pred_30d: dict) -> str:
    """综合置信度"""
    c7 = pred_7d.get("confidence", "低")
    c30 = pred_30d.get("confidence", "低")
    if c7 == "高" and c30 == "高":
        return "high"
    if c7 in ("高", "中") and c30 in ("高", "中"):
        return "medium"
    return "low"


def _gate(passes: bool, pass_msg: str, fail_msg: str) -> dict:
    return {"pass": passes, "reason": pass_msg if passes else fail_msg}


def _result(
    action: str,
    confidence: str,
    max_pct: float,
    score: float,
    reasons: list,
    blockers: list,
    risk_controls: list,
    disclaimer: str,
) -> dict:
    label_map = {
        "wait": "等待",
        "avoid": "不适合买",
        "small_buy": "小额试探",
    }
    return {
        "action": action,
        "action_label": label_map.get(action, action),
        "confidence": confidence,
        "score": score,
        "max_position_pct": max_pct,
        "reasons": reasons,
        "blockers": blockers,
        "risk_controls": risk_controls,
        "disclaimer": disclaimer,
    }


def _safe_num(d: Optional[dict], key: str, default: float = 0) -> float:
    """安全取数值，支持 None dict 和 None 值"""
    if d is None:
        return default
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default
