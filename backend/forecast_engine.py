"""
未来走势情景判断模块
基于历史净值、趋势、回撤、波动率、风险评分和宏观因素
生成概率化情景判断，不代表确定预测，不构成投资建议
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from scoring import score_from_indicators

logger = logging.getLogger(__name__)


def generate_forecast(
    metrics: Dict[str, Any],
    risk: Optional[Dict[str, Any]] = None,
    fund_profile: Optional[Dict[str, Any]] = None,
    macro: Optional[Dict[str, Any]] = None,
    backtest_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    生成未来1天、3天、7天和30天的概率化情景判断
    所有计算由程序规则完成，不依赖LLM
    """
    result: Dict[str, Any] = {
        "forecast_1d": _forecast_period(metrics, risk, fund_profile, macro, period=1, backtest_result=backtest_result),
        "forecast_3d": _forecast_period(metrics, risk, fund_profile, macro, period=3, backtest_result=backtest_result),
        "forecast_7d": _forecast_period(metrics, risk, fund_profile, macro, period=7, backtest_result=backtest_result),
        "forecast_30d": _forecast_period(metrics, risk, fund_profile, macro, period=30, backtest_result=backtest_result),
        "disclaimer": "该判断仅为概率化情景分析，基于历史数据和当前指标计算，不代表未来一定发生。不构成投资建议。",
    }

    # 新增字段
    model_basis = "calibrated_rule_based" if (backtest_result and backtest_result.get("is_calibrated") and (backtest_result.get("probability_quality") or "low") != "low") else "rule_based"
    for key in ["forecast_1d", "forecast_3d", "forecast_7d", "forecast_30d"]:
        result[key]["model_basis"] = model_basis
        result[key]["probability_quality"] = (backtest_result or {}).get("probability_quality", "low") if backtest_result else "low"
        result[key]["main_uncertainties"] = (backtest_result or {}).get("main_uncertainties", []) if backtest_result else []

    # 注入 validation 摘要
    if backtest_result:
        result["validation"] = {
            "sample_size": backtest_result.get("sample_size", 0),
            "probability_quality": backtest_result.get("probability_quality", "low"),
            "is_calibrated": backtest_result.get("is_calibrated", False),
            "periods": {},
        }
        for period_key, period_data in backtest_result.get("periods", {}).items():
            result["validation"]["periods"][period_key] = {
                "sample_size": period_data.get("sample_size"),
                "directional_accuracy": period_data.get("directional_accuracy"),
                "brier_score": period_data.get("brier_score"),
                "threshold_used": period_data.get("threshold_used"),
                "baseline_comparison": period_data.get("baseline_comparison"),
                "actual_distribution": period_data.get("actual_distribution"),
            }
    else:
        result["validation"] = None

    # decision_support 字段
    result["decision_support"] = _build_decision_support(
        result, metrics, risk, fund_profile, backtest_result
    )

    return result


def _forecast_period(
    metrics: Dict[str, Any],
    risk: Optional[Dict[str, Any]],
    fund_profile: Optional[Dict[str, Any]],
    macro: Optional[Dict[str, Any]],
    period: int,
    backtest_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """计算单个周期的预测概率"""

    if metrics.get("error"):
        return _uncertain_result(f"净值数据不足：{metrics.get('error')}")

    data_days = metrics.get("data_days", 0)
    if period == 1 and data_days < 8:
        return _uncertain_result(f"历史数据仅{data_days}个交易日，不足以进行1天情景判断")

    if period == 3 and data_days < 12:
        return _uncertain_result(f"历史数据仅{data_days}个交易日，不足以进行3天情景判断")

    if period == 30 and data_days < 60:
        result = _calc_probabilities(metrics, risk, fund_profile, macro, period, backtest_result)
        result["confidence"] = "低"
        result["reasons"].append("历史数据少于60个交易日，中期预测置信度低")
        return result

    if period not in (1, 3) and data_days < 15:
        return _uncertain_result(f"历史数据仅{data_days}个交易日，不足以进行{period}天情景判断")

    return _calc_probabilities(metrics, risk, fund_profile, macro, period, backtest_result)


def _calc_probabilities(
    metrics: Dict[str, Any],
    risk: Optional[Dict[str, Any]],
    fund_profile: Optional[Dict[str, Any]],
    macro: Optional[Dict[str, Any]],
    period: int,
    backtest_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """基于多因子规则计算三向概率，核心评分委托给共享 scoring 模块"""

    # === 基金类型和宏观 ===
    fund_type = fund_profile.get("fund_type", "") if fund_profile else ""
    is_high_volatility = _is_high_volatility_type(fund_type)
    is_qdii = "QDII" in str(fund_type).upper()
    is_defensive_fund = _is_defensive_type(fund_type)
    is_china_equity = _is_china_equity_type(fund_type) and not is_qdii

    macro_available = macro is not None and macro.get("status") != "unavailable"
    macro_summary = macro.get("macro_summary", {}) if macro else {}
    risk_appetite = macro_summary.get("risk_appetite", "neutral") if macro_summary else "neutral"
    overseas = macro_summary.get("overseas_direction", "mixed") if macro_summary else "mixed"
    liquidity = macro_summary.get("liquidity", "unknown") if macro_summary else "unknown"
    forex_pressure = macro_summary.get("forex_pressure", "stable") if macro_summary else "stable"

    # === 核心评分（使用共享 scoring 模块，与 backtest 完全一致） ===
    score, reasons, up_triggers, down_triggers = score_from_indicators(
        metrics, period, fund_type, macro_available, risk_appetite, overseas, liquidity,
        forex_pressure, is_high_volatility, is_qdii, is_defensive_fund, is_china_equity
    )

    # === 风险评分调整（共享模块不包含此项） ===
    risk_score = risk.get("risk_score", 50) if risk else 50
    if risk_score > 70:
        score -= 12
        reasons.append("综合风险评分较高，下行不确定性大")
    elif risk_score > 50:
        score -= 5

    # === 基金类型标注 ===
    if is_high_volatility:
        reasons.append("该基金类型波动性较大，概率判断的不确定性较高")

    # === 估算修正（仅 forecast 可用，backtest 不使用） ===
    ret_1d = _safe(metrics.get("return_1trading"), 0)
    current_estimate = metrics.get("current_estimate", {}) or {}
    estimate_change_pct = _safe(current_estimate.get("estimated_change_pct"), 0)
    estimate_fresh = _is_fresh_estimate(current_estimate, metrics.get("data_end"))
    estimate_used = False
    estimate_note = None
    if estimate_fresh and estimate_change_pct != 0:
        if period == 30:
            score = score * 0.90 + estimate_change_pct * 3
        else:
            estimate_used = True
            if period == 1:
                estimate_note = (
                    f"当日估算修正：涨跌{estimate_change_pct}%，"
                    f"估算时间：{current_estimate.get('estimate_time', '未知')}（非正式净值）"
                )
            elif period == 3:
                estimate_note = (
                    f"短线估算参考：涨跌{estimate_change_pct}%，"
                    f"估算时间：{current_estimate.get('estimate_time', '未知')}（非正式净值）"
                )
            elif period == 7:
                estimate_note = (
                    f"参考估算：涨跌{estimate_change_pct}%（非正式净值，"
                    f"估算时间：{current_estimate.get('estimate_time', '未知')}）"
                )
            reasons.append(f"当日估算涨跌{estimate_change_pct}%（非正式净值）")
            if period == 1:
                score = score * 0.45 + estimate_change_pct * 30
            elif period == 3:
                score = score * 0.60 + estimate_change_pct * 18
            elif period == 7:
                score = score * 0.75 + estimate_change_pct * 8

            if estimate_change_pct > 1:
                up_triggers.append("当日估算继续转强并收复5日均线")
            elif estimate_change_pct < -1:
                down_triggers.append("当日估算继续走弱且跌破前低")

    # === 概率计算 ===
    raw_score = score
    score = _squash_score(score, period)
    up, sideways, down = _probabilities_from_score(score, period, estimate_used)

    # === 回测校准：使用实证准确率调整概率 ===
    calibration_applied = False
    if backtest_result:
        cal_curve = backtest_result.get("calibration_curve", [])
        emp_acc = _lookup_calibration(raw_score, f"{period}d", cal_curve)
        if emp_acc is not None and emp_acc > 0:
            calibration_applied = True
            # 实证准确率作为方向预测的置信度锚点
            if raw_score > 0:
                up = round(emp_acc)
                down = round(100 - emp_acc - sideways)
                if down < 5:
                    down = 5
                    sideways = 100 - up - down
            elif raw_score < 0:
                down = round(emp_acc)
                up = round(100 - emp_acc - sideways)
                if up < 5:
                    up = 5
                    sideways = 100 - up - down
            # near-zero: unchanged
            up = max(5, min(85, up))
            down = max(5, min(85, down))
            sideways = max(8, 100 - up - down)
            # 归一化
            total = up + sideways + down
            up = round(up / total * 100)
            sideways = round(sideways / total * 100)
            down = 100 - up - sideways

    # === 方向判断 ===
    if up >= down + 20:
        direction = "偏上行"
    elif down >= up + 20:
        direction = "偏下行"
    elif abs(up - down) < 8 and sideways > 35:
        direction = "震荡"
    elif abs(up - down) < 15:
        direction = "震荡"
    else:
        direction = "不确定"

    # 指标冲突检测
    conflicts = _check_conflicts(metrics, period)
    if conflicts:
        if period in (7, 30):
            # 中长周期：冲突信号直接降低方向确定性
            direction = "不确定"
            reasons.append("多空信号冲突：" + "；".join(conflicts))
        else:
            # 短线周期：仅追加风险提示并降低置信度，不强制改为不确定
            reasons.append("注意信号冲突：" + "；".join(conflicts))
            # 通过下面 _calc_confidence 的 conflicts 参数自然降低置信度

    # === 置信度 ===
    confidence = _calc_confidence(metrics, macro_available, is_high_volatility, data_days=metrics.get("data_days", 0), period=period, conflicts=conflicts)

    # 高波动基金降置信度
    if is_high_volatility and confidence == "高":
        confidence = "中"
    if estimate_used and period == 1 and confidence == "高":
        confidence = "中"

    # 回测结果降置信度：如果回测准确率低，降低置信度
    if backtest_result and period in (1, 3, 7, 30):
        key = f"{period}d"
        bt = backtest_result.get("periods", {}).get(key, {})
        bt_acc = bt.get("directional_accuracy")
        if bt_acc is not None:
            if bt_acc < 45:
                if confidence == "高":
                    confidence = "低"
                elif confidence == "中":
                    confidence = "低"
            elif bt_acc < 50:
                if confidence == "高":
                    confidence = "中"

    # 整体回测质量上限：低质量回测时置信度不能为"高"
    if backtest_result:
        overall_quality = backtest_result.get("probability_quality", "low")
        if overall_quality == "low" and confidence == "高":
            confidence = "中"
        if not backtest_result.get("is_calibrated") and confidence == "高":
            confidence = "中"

    # 补充默认触发条件
    if not up_triggers:
        up_triggers = [
            "放量站上20日均线且均线开始拐头向上",
            "短期回撤企稳且出现连续阳线",
        ]
    if not down_triggers:
        down_triggers = [
            "跌破近期关键支撑位且放量",
            "均线出现空头排列信号",
        ]

    # 去重
    reasons = list(dict.fromkeys(reasons))
    up_triggers = list(dict.fromkeys(up_triggers))[:4]
    down_triggers = list(dict.fromkeys(down_triggers))[:4]

    expected_range = _estimate_return_range(score, period, metrics, is_high_volatility, is_defensive_fund)

    return {
        "period_days": period,
        "direction": direction,
        "rise_fall": _rise_fall_label(up, down, sideways),
        "up_probability": up,
        "sideways_probability": sideways,
        "down_probability": down,
        "expected_return_range": expected_range,
        "confidence": confidence,
        "score": round(score, 1),
        "raw_score": round(raw_score, 1),
        "estimate_used": estimate_used,
        "estimate_note": estimate_note,
        "calibration_applied": calibration_applied,
        "reasons": reasons[:6],
        "up_triggers": up_triggers,
        "down_triggers": down_triggers,
    }


def _check_conflicts(metrics: Dict[str, Any], period: int) -> List[str]:
    """检测多空信号冲突"""
    conflicts = []
    trend = metrics.get("trend", "")
    ret_30d = _safe(metrics.get("return_30d"), 0)
    pos_30d = _safe(metrics.get("position_in_30d_range"), 50)
    rebound = _safe(metrics.get("rebound_from_30d_low"), 0)

    # 短期反弹 vs 中期空头
    if ret_30d > 3 and ("空头" in str(trend) or "下降" in str(trend)):
        conflicts.append("短期反弹但中期趋势仍为空头")
    # 低位但趋势空头
    if pos_30d < 25 and ("空头" in str(trend) or "下降" in str(trend)):
        conflicts.append("处于低位但下跌趋势未结束")
    # 高位但趋势多头（追高）
    if pos_30d > 75 and "多头" in str(trend) and ret_30d > 10:
        conflicts.append("趋势偏多但处于高位，追高风险")
    # 强反弹但宽幅波动
    if rebound > 10 and _safe(metrics.get("volatility_30d"), 0) > 30:
        conflicts.append("反弹力度强但波动率仍高，方向不确定")

    return conflicts


def _calc_confidence(
    metrics: Dict[str, Any],
    macro_available: bool,
    is_high_volatility: bool,
    data_days: int,
    period: int,
    conflicts: List[str],
) -> str:
    """计算预测置信度"""
    score = 100

    if data_days < 60:
        score -= 30
    elif data_days < 90:
        score -= 15

    if not macro_available:
        score -= 10

    if is_high_volatility:
        score -= 15

    if conflicts:
        score -= 20

    if period == 30:
        score -= 10  # 周期越长，置信度自然更低

    if score >= 70:
        return "高"
    elif score >= 40:
        return "中"
    return "低"


def _rise_fall_label(up: int, down: int, sideways: int) -> str:
    """把三向概率转成更直观的涨跌判断。"""
    if up >= down + 12:
        return "偏涨"
    if down >= up + 12:
        return "偏跌"
    if sideways >= 38:
        return "震荡"
    return "不确定"


def _squash_score(raw_score: float, period: int) -> float:
    """压缩极端分数，避免不同周期都被打到同一概率下限。"""
    scale = {1: 85, 3: 95, 7: 105, 30: 125}.get(period, 105)
    # 三次有理函数比硬截断更平滑，也比tanh更容易保留中段差异。
    return 100 * raw_score / (abs(raw_score) + scale)


def _probabilities_from_score(score: float, period: int, estimate_used: bool) -> tuple[int, int, int]:
    """根据周期生成差异化三向概率。短周期天然更容易震荡。"""
    sideways_base = {1: 36, 3: 34, 7: 30, 30: 24}.get(period, 30)
    if estimate_used and period == 1:
        sideways_base += 4
    elif estimate_used and period == 3:
        sideways_base += 2

    directional_pool = 100 - sideways_base
    tilt = max(-1.0, min(1.0, score / 100))
    edge = directional_pool * 0.42 * abs(tilt)

    up = directional_pool / 2
    down = directional_pool / 2
    if tilt > 0:
        up += edge
        down -= edge
    else:
        down += edge
        up -= edge

    if abs(score) < 18:
        sideways_base += 6
        up -= 3
        down -= 3

    caps = {
        1: (18, 58),
        3: (16, 60),
        7: (14, 64),
        30: (10, 70),
    }
    min_dir, max_dir = caps.get(period, (12, 66))
    up = max(min_dir, min(max_dir, up))
    down = max(min_dir, min(max_dir, down))
    sideways = max(12, min(52, 100 - up - down))

    total = up + sideways + down
    up = round(up / total * 100)
    sideways = round(sideways / total * 100)
    down = 100 - up - sideways
    return up, sideways, down


def _is_fresh_estimate(estimate: Dict[str, Any], data_end: Optional[str]) -> bool:
    """估算日期晚于正式净值日期时，认为可用于当日修正。"""
    estimate_time = str(estimate.get("estimate_time") or "")
    if not estimate_time or not data_end:
        return False
    try:
        est_date = datetime.strptime(estimate_time[:10], "%Y-%m-%d").date()
        nav_date = datetime.strptime(str(data_end)[:10], "%Y-%m-%d").date()
        return est_date > nav_date
    except Exception:
        return False


def _estimate_return_range(
    score: float,
    period: int,
    metrics: Dict[str, Any],
    is_high_volatility: bool,
    is_defensive_fund: bool,
) -> Dict[str, Any]:
    """给出非承诺式的概率区间，方便前端展示涨跌幅预估口径。"""
    vol_30d = _safe(metrics.get("volatility_30d"), 15)
    ewma_vol = _safe(metrics.get("ewma_volatility_20d"), vol_30d)
    daily_vol = max(vol_30d, ewma_vol, 5) / (250 ** 0.5)
    horizon_vol = daily_vol * (period ** 0.5)
    drift = max(-2.5, min(2.5, score / 100)) * horizon_vol * 0.45

    if period == 1:
        width = horizon_vol * 0.75
    elif period == 3:
        width = horizon_vol * 0.80
    elif period == 7:
        width = horizon_vol * 0.85
    else:
        width = horizon_vol

    if is_high_volatility:
        width *= 1.15
    if is_defensive_fund:
        width *= 0.65

    low = round(drift - width, 2)
    high = round(drift + width, 2)
    return {
        "low": low,
        "high": high,
        "unit": "%",
        "note": "概率区间，不是收益承诺",
    }


def _is_high_volatility_type(fund_type: str) -> bool:
    """判断是否为高波动基金类型"""
    high_vol_keywords = ["QDII", "科技", "医药", "医疗", "新能源", "半导体", "芯片", "军工", "传媒"]
    return any(kw in str(fund_type) for kw in high_vol_keywords)


def _is_china_equity_type(fund_type: str) -> bool:
    equity_keywords = ["股票", "指数", "混合", "ETF", "LOF", "增强", "联接"]
    defensive_keywords = ["债券", "货币", "同业存单", "短债", "纯债"]
    text = str(fund_type)
    return any(kw in text for kw in equity_keywords) and not any(kw in text for kw in defensive_keywords)


def _is_defensive_type(fund_type: str) -> bool:
    defensive_keywords = ["债券", "货币", "同业存单", "短债", "纯债"]
    return any(kw in str(fund_type) for kw in defensive_keywords)


def _build_decision_support(
    forecast_result: Dict[str, Any],
    metrics: Dict[str, Any],
    risk: Optional[Dict[str, Any]],
    fund_profile: Optional[Dict[str, Any]],
    backtest_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建决策辅助字段"""
    f7 = forecast_result.get("forecast_7d", {})
    f30 = forecast_result.get("forecast_30d", {})

    # action_bias 判断
    risk_score = risk.get("risk_score", 50) if risk else 50
    up7 = f7.get("up_probability", 33)
    down7 = f7.get("down_probability", 33)
    conf7 = f7.get("confidence", "低")

    # 回测质量低时，避免给出偏积极/偏谨慎等方向性建议
    bt_quality = (backtest_result or {}).get("probability_quality", "low") if backtest_result else "low"
    quality_low = bt_quality == "low"

    if risk_score > 70:
        action_bias = "降低仓位风险"
    elif quality_low:
        action_bias = "观望（回测未验证规则有效性）"
    elif up7 > down7 + 15 and conf7 in ("高", "中"):
        action_bias = "偏积极"
    elif down7 > up7 + 15:
        action_bias = "偏谨慎"
    elif abs(up7 - down7) < 12:
        action_bias = "观望"
    else:
        action_bias = "观望"

    # 买入/减仓观察条件
    buy_watch = []
    reduce_watch = []

    # 从7d和30d触发条件提取
    for fp in [f7, f30]:
        buy_watch.extend(fp.get("up_triggers", [])[:2])
        reduce_watch.extend(fp.get("down_triggers", [])[:2])

    buy_watch = list(dict.fromkeys(buy_watch))[:3]
    reduce_watch = list(dict.fromkeys(reduce_watch))[:3]

    # 判断失效信号
    invalidation = [
        "净值跌破60日均线且放量",
        "波动率突破历史高位（分位>80%）",
        "连续3个交易日下跌且跌幅扩大",
    ]

    # position_hint 基础版本（无持仓时为空）
    position_hint = None

    # 时间周期说明
    time_horizon_note = (
        "1天：盘中估算参考，仅作为当日趋势辅助判断，不适合作为买卖依据。\n"
        "3天：短线参考，波动较大，适合观察短期动能变化。\n"
        "7天：中期参考，可结合趋势判断仓位调整意向。\n"
        "30天：较长周期参考，受宏观和市场风格影响大，不确定性最高。"
    )

    return {
        "action_bias": action_bias,
        "buy_watch_conditions": buy_watch if buy_watch else ["等待更多信号"],
        "reduce_watch_conditions": reduce_watch if reduce_watch else ["关注风险评级"],
        "invalidation_signals": invalidation,
        "position_hint": position_hint,
        "time_horizon_note": time_horizon_note,
        "model_quality_note": (
            "回测未证明规则模型稳定优于基准模型，概率仅作低置信参考，历史回测不代表未来表现。"
            if quality_low
            else "历史回测准确率不代表未来表现，决策应结合多方信息。"
        ),
    }


def _uncertain_result(reason: str) -> Dict[str, Any]:
    return {
        "period_days": None,
        "direction": "不确定",
        "rise_fall": "不确定",
        "up_probability": 33,
        "sideways_probability": 34,
        "down_probability": 33,
        "expected_return_range": {"low": None, "high": None, "unit": "%", "note": "数据不足"},
        "confidence": "低",
        "score": 0,
        "reasons": [reason],
        "up_triggers": ["数据充足后再进行评估"],
        "down_triggers": ["数据充足后再进行评估"],
    }


def _safe(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _lookup_calibration(raw_score: float, period_key: str, calibration_curve: list) -> float | None:
    """从校准曲线查找该分数范围的经验准确率"""
    if not calibration_curve:
        return None
    boundaries = [-200, -60, -40, -20, 0, 20, 40, 60, 200]
    for low, high in zip(boundaries[:-1], boundaries[1:]):
        if low <= raw_score < high:
            range_key = f"{low} to {high}"
            for entry in calibration_curve:
                if entry.get("period") == period_key and entry.get("score_range") == range_key:
                    acc = entry.get("accuracy", 0)
                    cnt = entry.get("count", 0)
                    if cnt >= 5:
                        return acc
            return None
    return None
