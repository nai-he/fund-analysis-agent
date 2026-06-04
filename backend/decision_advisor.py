"""
Rule-based fund buy/sell decision advisor.
Generates conservative decision references — not investment advice.
"""
from typing import Optional


def _is_up_direction(period_forecast: dict) -> bool:
    """Check if the forecast period indicates an upward direction."""
    text = f"{period_forecast.get('direction', '')} {period_forecast.get('rise_fall', '')}"
    return any(token in text for token in ["上行", "偏涨", "上涨", "偏强"])


def _is_down_direction(period_forecast: dict) -> bool:
    """Check if the forecast period indicates a downward direction."""
    text = f"{period_forecast.get('direction', '')} {period_forecast.get('rise_fall', '')}"
    return any(token in text for token in ["下行", "偏跌", "下跌", "偏弱"])


def _apply_backtest_quality(
    confidence: str,
    reasons: list,
    risk_warnings: list,
    invalidation_signals: list,
    backtest_quality: str,
    is_calibrated: bool,
) -> str:
    """Downgrade confidence when backtest quality is poor."""
    if backtest_quality == "low" or is_calibrated is False:
        if "回测未证明模型稳定优于基线，方向判断仅低置信参考。" not in reasons:
            reasons.append("回测未证明模型稳定优于基线，方向判断仅低置信参考。")
        if "模型概率估计尚不稳定，情景判断可能偏差较大。" not in risk_warnings:
            risk_warnings.append("模型概率估计尚不稳定，情景判断可能偏差较大。")
        if "后续需以新的回测结果验证模型是否稳定优于基线。" not in invalidation_signals:
            invalidation_signals.append("后续需以新的回测结果验证模型是否稳定优于基线。")
        return "低"
    return confidence


def build_decision_advice(
    fund: Optional[dict],
    metrics: Optional[dict],
    risk: Optional[dict],
    forecast: Optional[dict],
    position: Optional[dict] = None,
) -> dict:
    """Build a conservative decision reference from risk, forecast, and position data."""

    risk_score = _safe_float(risk, "risk_score", 50)
    forecast_7d = (forecast or {}).get("forecast_7d") or {}
    forecast_30d = (forecast or {}).get("forecast_30d") or {}
    validation = (forecast or {}).get("validation") or {}

    backtest_quality = validation.get("probability_quality", "low")
    is_calibrated = validation.get("is_calibrated", False)

    planned_buy_amount = _safe_float(position, "planned_buy_amount", None)
    cost_nav = _safe_float(position, "cost_nav", None)
    max_loss_percent = _safe_float(position, "max_loss_percent", None)
    holding_amount = _safe_float(position, "holding_amount", None)
    holding_units = _safe_float(position, "holding_units", None)
    latest_nav = _safe_float(metrics, "latest_nav", None)
    has_holding = _has_existing_position(cost_nav, holding_amount, holding_units)

    reasons = []
    risk_warnings = []
    buy_conditions = []
    sell_or_reduce_conditions = []
    invalidation_signals = []
    confidence = "中"

    # ---- Rule 1: risk_score >= 75 → reduce or avoid ----
    if risk_score >= 75:
        if has_holding:
            action = "reduce"
            action_label = "降低仓位"
            reasons.append("综合风险评分较高（≥75），当前市场环境不利，可考虑降低仓位风险。")
            risk_warnings.append("风险评分处于高位，继续持有可能面临较大回撤。")
            sell_or_reduce_conditions.append("若跌破个人止损线或关键支撑位，应重新评估是否继续持有。")
        else:
            action = "avoid"
            action_label = "暂缓新增"
            reasons.append("综合风险评分较高（≥75），当前不适合新开仓或大额买入。")
            risk_warnings.append("高风险环境下追高买入不确定性较大，适合等待风险释放后再评估。")
            invalidation_signals.append("若风险评分回落至60以下且走势企稳，可重新评估。")
        confidence = _apply_backtest_quality(
            "高", reasons, risk_warnings, invalidation_signals,
            backtest_quality, is_calibrated,
        )
        return _build_result(
            action=action, action_label=action_label, confidence=confidence,
            reasons=reasons, risk_warnings=risk_warnings,
            buy_conditions=buy_conditions,
            sell_or_reduce_conditions=sell_or_reduce_conditions,
            invalidation_signals=invalidation_signals,
            planned_buy_amount=planned_buy_amount,
            cost_nav=cost_nav, latest_nav=latest_nav,
            max_loss_percent=max_loss_percent, risk_score=risk_score,
            fund=fund,
        )

    # ---- Rule 5: forecast down + risk > 55 → observe/avoid ----
    is_7d_down = _is_down_direction(forecast_7d)
    is_30d_down = _is_down_direction(forecast_30d)
    is_7d_up = _is_up_direction(forecast_7d)
    is_30d_up = _is_up_direction(forecast_30d)

    if (is_7d_down or is_30d_down) and risk_score > 55:
        if has_holding:
            action = "hold"
            action_label = "谨慎持有"
            reasons.append("短期走势偏弱且风险评分偏高（>55），当前不适合追加仓位。")
            risk_warnings.append("走势偏弱叠加风险偏高，若继续下行需关注止损。")
            sell_or_reduce_conditions.append("若连续下破关键支撑或亏损扩大，可考虑降低仓位风险。")
        else:
            action = "observe"
            action_label = "观望"
            reasons.append("短期走势偏弱且风险评分偏高（>55），适合暂时观望，等待方向明朗。")
            risk_warnings.append("走势偏弱环境下买入容易被套，耐心等待企稳信号。")
            buy_conditions.append("等待7日或30日走势企稳（方向转为偏强或震荡），且风险评分回落至55以下。")
        confidence = _apply_backtest_quality(
            "中", reasons, risk_warnings, invalidation_signals,
            backtest_quality, is_calibrated,
        )
        return _build_result(
            action=action, action_label=action_label, confidence=confidence,
            reasons=reasons, risk_warnings=risk_warnings,
            buy_conditions=buy_conditions,
            sell_or_reduce_conditions=sell_or_reduce_conditions,
            invalidation_signals=invalidation_signals,
            planned_buy_amount=planned_buy_amount,
            cost_nav=cost_nav, latest_nav=latest_nav,
            max_loss_percent=max_loss_percent, risk_score=risk_score,
            fund=fund,
        )

    # ---- Rule 2: risk_score >= 60 → observe or small_trial ----
    if risk_score >= 60:
        if has_holding:
            action = "hold"
            action_label = "谨慎持有"
            reasons.append("风险评分偏高（≥60），适合谨慎持有，暂不追加仓位。")
            risk_warnings.append("风险处于偏高水平，需密切关注市场变化和个人止损线。")
        else:
            action = "small_trial"
            action_label = "小额试探"
            reasons.append("风险评分偏高（≥60），若确有意向可小额试探，不宜大额买入。")
            risk_warnings.append("当前风险水平下大额买入需承担较大不确定性。")
            buy_conditions.append("试探仓位参考计划金额的10%-20%，确认走势企稳后再考虑追加。")
        confidence = _apply_backtest_quality(
            "中", reasons, risk_warnings, invalidation_signals,
            backtest_quality, is_calibrated,
        )
        return _build_result(
            action=action, action_label=action_label, confidence=confidence,
            reasons=reasons, risk_warnings=risk_warnings,
            buy_conditions=buy_conditions,
            sell_or_reduce_conditions=sell_or_reduce_conditions,
            invalidation_signals=invalidation_signals,
            planned_buy_amount=planned_buy_amount,
            cost_nav=cost_nav, latest_nav=latest_nav,
            max_loss_percent=max_loss_percent, risk_score=risk_score,
            fund=fund,
        )

    # ---- Rule 4: 7d+30d both up, risk < 55, good backtest → batch_buy ----
    backtest_ok = backtest_quality != "low" and is_calibrated is not False
    if is_7d_up and is_30d_up and risk_score < 55 and backtest_ok:
        action = "batch_buy"
        action_label = "分批关注"
        reasons.append("短期和中期走势均偏强，风险评分较低，回测验证可接受，可考虑分批关注。")
        reasons.append("分多批关注有助于避免一次性满仓，降低择时风险。")
        buy_conditions.append("分2-3批关注，每批间隔至少3-5个交易日，观察走势是否持续偏强。")
        buy_conditions.append("若关注期间走势转弱或风险评分上升至55以上，暂停后续批次。")
        risk_warnings.append("即使信号偏积极，仍需控制总仓位，避免一次性满仓。")
        invalidation_signals.append("若7日方向转弱或风险评分突破55，暂停关注计划。")
        confidence = _apply_backtest_quality(
            "中", reasons, risk_warnings, invalidation_signals,
            backtest_quality, is_calibrated,
        )
        return _build_result(
            action=action, action_label=action_label, confidence=confidence,
            reasons=reasons, risk_warnings=risk_warnings,
            buy_conditions=buy_conditions,
            sell_or_reduce_conditions=sell_or_reduce_conditions,
            invalidation_signals=invalidation_signals,
            planned_buy_amount=planned_buy_amount,
            cost_nav=cost_nav, latest_nav=latest_nav,
            max_loss_percent=max_loss_percent, risk_score=risk_score,
            fund=fund,
        )

    # ---- Default: observe ----
    confidence = _apply_backtest_quality(
        confidence, reasons, risk_warnings, invalidation_signals,
        backtest_quality, is_calibrated,
    )
    action = "observe"
    action_label = "观望"
    reasons.append("当前信号不够明确，适合观望等待更清晰的方向选择。")
    buy_conditions.append("等待7日、30日走势方向一致偏强且风险评分低于55。")

    return _build_result(
        action=action, action_label=action_label, confidence=confidence,
        reasons=reasons, risk_warnings=risk_warnings,
        buy_conditions=buy_conditions,
        sell_or_reduce_conditions=sell_or_reduce_conditions,
        invalidation_signals=invalidation_signals,
        planned_buy_amount=planned_buy_amount,
        cost_nav=cost_nav, latest_nav=latest_nav,
        max_loss_percent=max_loss_percent, risk_score=risk_score,
        fund=fund,
    )


def _build_result(
    *,
    action: str,
    action_label: str,
    confidence: str,
    reasons: list,
    risk_warnings: list,
    buy_conditions: list,
    sell_or_reduce_conditions: list,
    invalidation_signals: list,
    planned_buy_amount: Optional[float],
    cost_nav: Optional[float],
    latest_nav: Optional[float],
    max_loss_percent: Optional[float],
    risk_score: float,
    fund: Optional[dict] = None,
) -> dict:
    """Assemble the final result dict with position-aware hints and buy amount suggestions."""

    # --- Position hints ---
    position_hint = ""
    if cost_nav is not None and latest_nav is not None and cost_nav > 0:
        pnl_pct = (latest_nav - cost_nav) / cost_nav * 100
        if pnl_pct < 0 and max_loss_percent is not None:
            if abs(pnl_pct) >= max_loss_percent * 0.8:
                position_hint = (
                    f"当前浮亏 {abs(pnl_pct):.1f}%，已接近最大亏损线 {max_loss_percent}%，"
                    "需关注止损纪律。"
                )
                sell_or_reduce_conditions.append(
                    f"浮亏已逼近最大可承受亏损（{max_loss_percent}%），若继续扩大应重新评估止损或降仓。"
                )
            else:
                position_hint = f"当前浮亏 {abs(pnl_pct):.1f}%，暂在可承受范围内。"
        elif pnl_pct > 0 and risk_score > 55:
            position_hint = (
                f"当前浮盈 {pnl_pct:.1f}%，但短期风险偏高，可考虑降低仓位风险。"
            )
            sell_or_reduce_conditions.append(
                "浮盈状态下若风险评分持续偏高，可考虑适当降低仓位风险。"
            )
        else:
            position_hint = f"当前浮动盈亏约 {pnl_pct:+.1f}%。"

    # --- Suggested buy amount ---
    suggested_buy_amount = None
    suggested_buy_pct = None
    if planned_buy_amount is not None and planned_buy_amount > 0:
        pct_map = {
            "avoid": 0,
            "reduce": 0,
            "observe": 0,
            "hold": 0,
            "small_trial": 15,
            "batch_buy": 33,
        }
        pct = pct_map.get(action, 0)
        suggested_buy_pct = pct
        suggested_buy_amount = round(planned_buy_amount * pct / 100, 2) if pct > 0 else 0

    # --- Summary ---
    fund_name = ""
    if fund and fund.get("name"):
        fund_name = fund["name"]

    summary_map = {
        "avoid": f"{fund_name or '该基金'}当前风险较高，暂不适合新开仓。" if not cost_nav else f"{fund_name or '该基金'}风险较高，可考虑降低仓位风险。",
        "reduce": f"{fund_name or '该基金'}风险评分高，可考虑降低仓位风险。",
        "observe": f"{fund_name or '该基金'}信号不明确，适合观望等待。",
        "small_trial": f"{fund_name or '该基金'}可小额试探，不宜大额买入。",
        "batch_buy": f"{fund_name or '该基金'}信号偏积极，可考虑分批关注。",
        "hold": f"{fund_name or '该基金'}适合谨慎持有，暂不追加。",
    }
    summary = summary_map.get(action, f"{fund_name or '该基金'}适合观望。")

    return {
        "action": action,
        "action_label": action_label,
        "confidence": confidence,
        "suggested_buy_amount": suggested_buy_amount,
        "suggested_buy_pct": suggested_buy_pct,
        "position_hint": position_hint or None,
        "summary": summary,
        "reasons": reasons,
        "risk_warnings": risk_warnings,
        "buy_conditions": buy_conditions,
        "sell_or_reduce_conditions": sell_or_reduce_conditions,
        "invalidation_signals": invalidation_signals,
        "disclaimer": "仅供个人研究参考，不构成投资建议。",
    }


def _safe_float(d: Optional[dict], key: str, default=None):
    """Safely extract a float value from a dict."""
    if d is None:
        return default
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _has_existing_position(
    cost_nav: Optional[float],
    holding_amount: Optional[float],
    holding_units: Optional[float],
) -> bool:
    """Treat any positive holding field as an existing position."""
    return any(
        value is not None and value > 0
        for value in (cost_nav, holding_amount, holding_units)
    )
