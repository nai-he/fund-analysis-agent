"""
风险评分系统
基于多维度指标计算结构化风险评分，由程序计算（非 LLM 胡猜）
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def calculate_risk(
    metrics: Dict[str, Any],
    fund_profile: Optional[Dict[str, Any]] = None,
    position: Optional[Dict[str, Any]] = None,
    macro: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    计算结构化风险评分
    """
    result = {
        "risk_score": 50.0,
        "risk_level": "中",
        "trend_score": 50.0,
        "drawdown_score": 50.0,
        "volatility_score": 50.0,
        "position_score": 50.0,
        "macro_score": 50.0,
        "position_personal_score": None,  # 无持仓时为 None
        "reasons": [],
        "warnings": [],
    }

    if metrics.get("error"):
        result["risk_level"] = "数据不足"
        result["risk_score"] = 50.0
        result["reasons"] = ["净值数据不足，无法评估风险"]
        result["warnings"] = ["数据不完整，风险评分不可靠"]
        return result

    # ---- 1. 趋势评分 (trend_score) ----
    result["trend_score"] = _score_trend(metrics, result)

    # ---- 2. 回撤评分 (drawdown_score) ----
    result["drawdown_score"] = _score_drawdown(metrics, result)

    # ---- 3. 波动率评分 (volatility_score) ----
    result["volatility_score"] = _score_volatility(metrics, result)

    # ---- 4. 位置评分 (position_score) — 追高/左侧风险 ----
    result["position_score"] = _score_market_position(metrics, result)

    # ---- 5. 宏观评分 (macro_score) ----
    result["macro_score"] = _score_macro(macro, result)

    # ---- 6. 个人持仓评分 (position_personal_score) ----
    if position and position.get("cost_nav") is not None:
        result["position_personal_score"] = _score_personal_position(metrics, position, result)
    else:
        result["position_personal_score"] = None

    # ---- 综合评分 ----
    scores = [
        result["trend_score"],
        result["drawdown_score"],
        result["volatility_score"],
        result["position_score"],
        result["macro_score"],
    ]
    if result["position_personal_score"] is not None:
        scores.append(result["position_personal_score"])

    result["risk_score"] = round(sum(scores) / len(scores), 1)

    # 风险等级
    if result["risk_score"] <= 30:
        result["risk_level"] = "低"
    elif result["risk_score"] <= 50:
        result["risk_level"] = "中"
    elif result["risk_score"] <= 70:
        result["risk_level"] = "较高"
    else:
        result["risk_level"] = "高"

    # 去重
    result["reasons"] = list(dict.fromkeys(result["reasons"]))
    result["warnings"] = list(dict.fromkeys(result["warnings"]))

    logger.info(f"风险评估完成: score={result['risk_score']}, level={result['risk_level']}")
    return result


def _safe_num(value, default=0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _score_trend(metrics: Dict, result: Dict) -> float:
    """趋势评分：0=趋势极好，100=趋势极差"""
    score = 50.0
    return_30d = _safe_num(metrics.get("return_30d"), 0)
    return_60d = _safe_num(metrics.get("return_60d"), 0)
    return_90d = _safe_num(metrics.get("return_90d"), 0)
    trend = metrics.get("trend", "")
    ma20 = metrics.get("ma_20")
    latest_nav = _safe_num(metrics.get("latest_nav"), 0)

    # 近30/60/90日涨跌幅
    if return_30d > 10:
        score -= 10
        result["reasons"].append(f"近30天涨幅较大({return_30d}%)，短期回调风险提高")
    elif return_30d < -10:
        score += 15
        result["reasons"].append(f"近30天跌幅较大({return_30d}%)，下行趋势风险较高")
    elif return_30d < -5:
        score += 8
        result["reasons"].append(f"近30天下跌({return_30d}%)")
    elif return_30d < 0:
        score += 3

    if return_60d < -15:
        score += 12
        result["reasons"].append(f"近60天跌幅较大({return_60d}%)，中期趋势偏弱")
    elif return_60d < -5:
        score += 5

    if return_90d < -20:
        score += 10
        result["reasons"].append(f"近90天跌幅较大({return_90d}%)，长期趋势偏弱")

    # 均线趋势
    if "空头排列" in str(trend) or "下降" in str(trend):
        score += 15
        result["reasons"].append("均线空头排列，下降趋势")
        result["warnings"].append("当前处于下降趋势中，左侧介入风险较高")
    elif "多头排列" in str(trend) or "上升" in str(trend):
        score -= 10
    elif "偏空" in str(trend):
        score += 8

    # 均线位置
    if ma20 is not None and latest_nav > 0:
        if latest_nav < ma20:
            score += 5
            result["reasons"].append("净值低于20日均线")

    return max(0, min(100, score))


def _score_drawdown(metrics: Dict, result: Dict) -> float:
    """回撤评分：0=无回撤，100=极大回撤"""
    score = 50.0
    dd_30d = abs(_safe_num(metrics.get("max_drawdown_30d"), 0))
    dd_60d = abs(_safe_num(metrics.get("max_drawdown_60d"), 0))
    dd_90d = abs(_safe_num(metrics.get("max_drawdown_90d"), 0))

    if dd_30d > 10:
        score += 20
        result["reasons"].append(f"近30天最大回撤{dd_30d}%，短期回撤显著")
        result["warnings"].append("近期回撤较大，关注止损纪律")
    elif dd_30d > 5:
        score += 10
        result["reasons"].append(f"近30天最大回撤{dd_30d}%")
    elif dd_30d > 3:
        score += 5

    if dd_60d > 15:
        score += 15
        result["reasons"].append(f"近60天最大回撤{dd_60d}%，中期回撤较大")
    elif dd_60d > 8:
        score += 8

    if dd_90d > 20:
        score += 12
        result["reasons"].append(f"近90天最大回撤{dd_90d}%，长期回撤较大")
        result["warnings"].append("长期回撤幅度较大，需关注是否进入下跌通道")

    return max(0, min(100, score))


def _score_volatility(metrics: Dict, result: Dict) -> float:
    """波动率评分：0=极低波动，100=极高波动"""
    score = 50.0
    vol_30d = _safe_num(metrics.get("volatility_30d"), 0)
    vol_60d = _safe_num(metrics.get("volatility_60d"), 0)
    ds_vol_30d = _safe_num(metrics.get("downside_volatility_30d"), 0)

    if vol_30d > 40:
        score += 20
        result["reasons"].append(f"近30天年化波动率极高({vol_30d}%)")
        result["warnings"].append("波动率极高，净值波动剧烈，不适合风险承受能力低的投资者")
    elif vol_30d > 25:
        score += 12
        result["reasons"].append(f"近30天波动率较高({vol_30d}%)")
    elif vol_30d > 15:
        score += 5
    elif vol_30d < 10:
        score -= 10
        result["reasons"].append(f"近30天波动率较低({vol_30d}%)，波动风险小")

    if vol_60d > 35:
        score += 10
        result["reasons"].append(f"近60天波动率较高({vol_60d}%)")

    # 下行波动率
    if ds_vol_30d > 25:
        score += 8
        result["reasons"].append("下行波动率较高，下跌时的波动幅度大")

    return max(0, min(100, score))


def _score_market_position(metrics: Dict, result: Dict) -> float:
    """位置评分：评估追高/左侧风险"""
    score = 50.0
    pos_30d = _safe_num(metrics.get("position_in_30d_range"), 50)
    pos_60d = _safe_num(metrics.get("position_in_60d_range"), 50)
    pos_90d = _safe_num(metrics.get("position_in_90d_range"), 50)
    trend = metrics.get("trend", "")
    vol_30d = _safe_num(metrics.get("volatility_30d"), 0)

    # 追高风险：净值在短期高位 + 高波动
    if pos_30d > 80:
        score += 10
        result["reasons"].append("净值处于近30日高位区间")
        if vol_30d > 25:
            score += 8
            result["warnings"].append("净值接近短期高位且波动率高，追高风险较大")
    elif pos_30d > 60:
        score += 3

    # 左侧风险：净值在低位但趋势仍空头
    if pos_30d < 20 and ("空头" in str(trend) or "下降" in str(trend)):
        score += 12
        result["reasons"].append("净值处于近30日低位但趋势仍为空头")
        result["warnings"].append("虽然处于低位但下跌趋势未结束，左侧介入风险较高")
    elif pos_30d < 20:
        score -= 5
        result["reasons"].append("净值处于近30日低位区间，可能存在分批关注机会")

    # 60日和90日位置也考虑
    if pos_60d > 85:
        score += 5
        result["warnings"].append("净值接近60日高位，中期追高风险")
    if pos_90d < 15:
        score += 5
        result["reasons"].append("净值接近90日低位")

    return max(0, min(100, score))


def _score_macro(macro: Optional[Dict], result: Dict) -> float:
    """宏观评分"""
    score = 50.0
    if macro is None or macro.get("status") == "unavailable":
        result["reasons"].append("宏观数据暂不可用，宏观评分保持中性")
        return score

    macro_summary = macro.get("macro_summary", {})
    if not macro_summary:
        return score

    risk_appetite = macro_summary.get("risk_appetite", "")
    overseas_direction = macro_summary.get("overseas_direction", "")
    forex_pressure = macro_summary.get("forex_pressure", "")
    commodity_disturbance = macro_summary.get("commodity_disturbance", "")

    if "risk-off" in str(risk_appetite).lower() or "避险" in str(risk_appetite):
        score += 8
        result["reasons"].append("当前宏观风险偏好偏避险")
    elif "risk-on" in str(risk_appetite).lower() or "积极" in str(risk_appetite):
        score -= 5

    if "bearish" in str(overseas_direction).lower() or "下跌" in str(overseas_direction):
        score += 5
        result["reasons"].append("海外市场偏弱，可能传导至国内")
    elif "bullish" in str(overseas_direction).lower() or "上涨" in str(overseas_direction):
        score -= 3

    if "压力" in str(forex_pressure) or "贬值" in str(forex_pressure):
        score += 5
        result["reasons"].append("汇率存在贬值压力，可能影响QDII基金和外资流向")

    if "扰动" in str(commodity_disturbance):
        score += 3

    return max(0, min(100, score))


def _score_personal_position(metrics: Dict, position: Dict, result: Dict) -> float:
    """个人持仓风险评分"""
    score = 50.0
    latest_nav = _safe_num(metrics.get("latest_nav"), 0)
    cost_nav = _safe_num(position.get("cost_nav"), 0)
    max_loss_pct = _safe_num(position.get("max_loss_percent"), 20)
    risk_preference = position.get("risk_preference", "平衡")
    holding_amount = _safe_num(position.get("holding_amount"), 0)

    if cost_nav <= 0 or latest_nav <= 0:
        result["reasons"].append("持仓成本或净值数据无效，个人持仓评分保持中性")
        return score

    # 当前浮盈浮亏
    profit_pct = (latest_nav - cost_nav) / cost_nav * 100

    # 亏损情况
    if profit_pct < 0:
        loss_severity = abs(profit_pct) / max_loss_pct  # 0-1，1=已达到最大亏损

        if loss_severity >= 0.9:
            score += 25
            result["reasons"].append(f"当前浮亏{abs(profit_pct):.1f}%，已接近最大可承受亏损{max_loss_pct}%")
            result["warnings"].append("持仓亏损已接近个人设定的最大亏损线，需警惕止损")
        elif loss_severity >= 0.5:
            score += 15
            result["reasons"].append(f"当前浮亏{abs(profit_pct):.1f}%，达到最大可承受亏损的{loss_severity*100:.0f}%")
            result["warnings"].append("持仓亏损已过半程，建议关注是否继续恶化")
        elif profit_pct < -5:
            score += 8
            result["reasons"].append(f"当前浮亏{abs(profit_pct):.1f}%")
        else:
            score += 3

        if profit_pct < -3:
            result["warnings"].append(f"当前持仓浮亏{abs(profit_pct):.1f}%（成本{cost_nav}，现价{latest_nav}）")
    else:
        # 盈利状态
        score -= 5
        if profit_pct > 10:
            score -= 5
            result["reasons"].append(f"当前浮盈{profit_pct:.1f}%，已有较好收益")

    # 风险偏好调整
    if risk_preference == "保守":
        score += 10
        result["reasons"].append("用户风险偏好为保守，风险敏感度提高")
    elif risk_preference == "激进":
        score -= 8

    # 持有金额
    if holding_amount > 500000:
        score += 5
        result["reasons"].append("持仓金额较大，需更关注风险")

    # 定投评估
    if position.get("is_dca"):
        result["reasons"].append("用户正在定投中，定投可在下跌中摊薄成本")

    return max(0, min(100, score))


def get_risk_gauge_color(score: float) -> str:
    """返回风险评分对应的颜色"""
    if score <= 30:
        return "#22c55e"
    elif score <= 50:
        return "#eab308"
    elif score <= 70:
        return "#f97316"
    else:
        return "#ef4444"
