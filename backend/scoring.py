"""
共享评分模块
从原始净值数组计算技术指标并生成方向评分
供 backtest_engine 和 forecast_engine 共同使用
确保回测验证的模型与用户看到的预测模型完全一致
"""
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

# 回测中无法获取的外部因子（fund_type, macro, risk_score）
# 这些在回测中设为中性值，不影响核心技术因子的验证


def compute_indicators_from_nav(nav_array: np.ndarray) -> Dict[str, Any]:
    """
    从原始净值数组计算所有技术指标。
    输入: 一维 numpy array，按时间升序排列
    输出: 与 metrics.py 兼容的指标字典
    """
    n = len(nav_array)
    if n < 5:
        return {"error": "insufficient_data", "data_days": n}

    returns = np.diff(nav_array) / nav_array[:-1]
    result: Dict[str, Any] = {"data_days": n}

    # --- 收益 (交易日口径) ---
    result["return_1trading"] = _ret(nav_array, 1)
    result["return_5trading"] = _ret(nav_array, 5)
    result["return_10trading"] = _ret(nav_array, 10)
    result["return_20trading"] = _ret(nav_array, 20)
    result["return_60trading"] = _ret(nav_array, 60)

    # --- 自然日口径收益 (用交易日近似) ---
    result["return_7d"] = _ret(nav_array, 5)   # 约5个交易日
    result["return_30d"] = _ret(nav_array, 20)  # 约20个交易日
    result["return_60d"] = _ret(nav_array, 40)
    result["return_90d"] = _ret(nav_array, 60)

    # --- 均线 ---
    result["ma_5"] = _ma(nav_array, 5)
    result["ma_10"] = _ma(nav_array, 10)
    result["ma_20"] = _ma(nav_array, 20)
    result["ma_60"] = _ma(nav_array, 60)
    result["latest_nav"] = float(nav_array[-1])

    # --- 趋势分类 ---
    result["trend"] = _classify_trend_from_array(nav_array)

    # --- 最大回撤 ---
    result["max_drawdown_7d_calendar"] = _max_drawdown(nav_array, min(5, n))
    result["max_drawdown_30d_calendar"] = _max_drawdown(nav_array, min(20, n))
    result["max_drawdown_60d"] = _max_drawdown(nav_array, min(40, n))
    result["max_drawdown_90d_calendar"] = _max_drawdown(nav_array, min(60, n))

    # --- 波动率 (年化) ---
    result["volatility_30d"] = _annualized_vol(returns, min(20, len(returns)))
    result["volatility_60d"] = _annualized_vol(returns, min(40, len(returns)))
    result["volatility_90d"] = _annualized_vol(returns, min(60, len(returns)))
    result["downside_volatility_30d"] = _downside_vol(returns, min(20, len(returns)))
    result["downside_volatility_60d"] = _downside_vol(returns, min(40, len(returns)))

    # --- 夏普比率 ---
    result["sharpe_30d"] = _sharpe(returns, min(20, len(returns)))
    result["sharpe_60d"] = _sharpe(returns, min(40, len(returns)))

    # --- 区间位置 ---
    result["position_in_7d_range"] = _position_in_range(nav_array, min(5, n))
    result["position_in_30d_range"] = _position_in_range(nav_array, min(20, n))
    result["position_in_60d_range"] = _position_in_range(nav_array, min(40, n))
    result["position_in_90d_range"] = _position_in_range(nav_array, min(60, n))

    # --- 反弹/回落 ---
    result["rebound_from_7d_low"] = _rebound(nav_array, min(5, n))
    result["pullback_from_7d_high"] = _pullback(nav_array, min(5, n))
    result["rebound_from_30d_low"] = _rebound(nav_array, min(20, n))
    result["pullback_from_30d_high"] = _pullback(nav_array, min(20, n))

    # --- RSI ---
    result["rsi_6"] = _rsi(nav_array, 6)
    result["rsi_14"] = _rsi(nav_array, 14)
    result["rsi_28"] = _rsi(nav_array, 28)

    # --- MACD ---
    result["macd"] = _macd(nav_array)

    # --- 布林带 ---
    result["bollinger"] = _bollinger(nav_array)

    # --- 偏度 ---
    result["return_skew_60d"] = _skew(returns, min(40, len(returns)))

    # --- 动能加速度 ---
    result["momentum_acceleration_5d"] = _momentum_accel(nav_array)

    # --- EWMA 波动率 ---
    result["ewma_volatility_20d"] = _ewma_vol(returns)

    # --- 波动率分位 ---
    result["volatility_percentile_30d"] = _vol_percentile(returns, min(20, len(returns)))
    result["volatility_regime_30d"] = _vol_regime(result["volatility_percentile_30d"])

    # --- Calmar ---
    result["calmar_60d"] = _calmar(nav_array, returns, min(40, n))
    result["calmar_90d"] = _calmar(nav_array, returns, min(60, n))

    # --- 连续涨跌 ---
    result["consecutive_days"] = _consecutive_days(nav_array)

    # --- 日统计 ---
    result["daily_stats"] = _daily_stats(returns, min(20, len(returns)))

    # --- 胜率 ---
    result["win_rate_30d"] = _win_rate(returns, min(20, len(returns)))
    result["win_rate_60d"] = _win_rate(returns, min(40, len(returns)))

    return result


def score_from_indicators(
    indicators: Dict[str, Any],
    period: int,
    fund_type: str = "",
    macro_available: bool = False,
    risk_appetite: str = "neutral",
    overseas: str = "mixed",
    liquidity: str = "unknown",
    forex_pressure: str = "stable",
    is_high_volatility: bool = False,
    is_qdii: bool = False,
    is_defensive_fund: bool = False,
    is_china_equity: bool = False,
) -> Tuple[float, List[str], List[str], List[str]]:
    """
    基于指标字典计算方向评分。
    与 forecast_engine._calc_probabilities 完全相同的逻辑。

    返回: (score, reasons, up_triggers, down_triggers)
    """
    if indicators.get("error"):
        return 0.0, [f"数据不足：{indicators.get('error')}"], [], []

    # === 提取指标 ===
    ret_1d = _safe(indicators.get("return_1trading"), 0)
    ret_5trading = _safe(indicators.get("return_5trading"), 0)
    ret_10trading = _safe(indicators.get("return_10trading"), 0)
    ret_7d = _safe(indicators.get("return_7d"), 0)
    ret_30d = _safe(indicators.get("return_30d"), 0)
    ret_60d = _safe(indicators.get("return_60d"), 0)
    ret_90d = _safe(indicators.get("return_90d"), 0)

    dd_30d = abs(_safe(indicators.get("max_drawdown_30d_calendar"), 0))
    dd_60d = abs(_safe(indicators.get("max_drawdown_60d"), 0))
    dd_90d = abs(_safe(indicators.get("max_drawdown_90d_calendar"), 0))

    vol_30d = _safe(indicators.get("volatility_30d"), 0)
    vol_60d = _safe(indicators.get("volatility_60d"), 0)

    sharpe_30d = _safe(indicators.get("sharpe_30d"), 0)
    sharpe_60d = _safe(indicators.get("sharpe_60d"), 0)

    win_rate_30d = _safe(indicators.get("win_rate_30d"), 50)
    ma_5 = indicators.get("ma_5")
    ma_10 = indicators.get("ma_10")
    ma_20 = indicators.get("ma_20")
    latest_nav = _safe(indicators.get("latest_nav"), 0)

    trend = indicators.get("trend", "")
    pos_7d = _safe(indicators.get("position_in_7d_range"), 50)
    pos_30d = _safe(indicators.get("position_in_30d_range"), 50)
    pos_60d = _safe(indicators.get("position_in_60d_range"), 50)
    pos_90d = _safe(indicators.get("position_in_90d_range"), 50)

    rebound_7d = _safe(indicators.get("rebound_from_7d_low"), 0)
    pullback_7d = _safe(indicators.get("pullback_from_7d_high"), 0)
    rebound = _safe(indicators.get("rebound_from_30d_low"), 0)
    pullback = _safe(indicators.get("pullback_from_30d_high"), 0)

    momentum_accel = _safe(indicators.get("momentum_acceleration_5d"), 0)
    ewma_vol_20d = _safe(indicators.get("ewma_volatility_20d"), 0)
    volatility_regime = indicators.get("volatility_regime_30d", "未知")
    daily_stats = indicators.get("daily_stats", {}) or {}
    daily_mean = _safe(daily_stats.get("mean"), 0)
    consecutive = indicators.get("consecutive_days", {}) or {}
    consecutive_direction = str(consecutive.get("direction", ""))
    consecutive_days = int(_safe(consecutive.get("days"), 0))

    calmar_60d = _safe(indicators.get("calmar_60d"), 0)
    calmar_90d = _safe(indicators.get("calmar_90d"), 0)

    rsi_6 = _safe(indicators.get("rsi_6"), 50)
    rsi_14 = _safe(indicators.get("rsi_14"), 50)
    rsi_28 = _safe(indicators.get("rsi_28"), 50)

    macd_data = indicators.get("macd") or {}
    macd_hist = _safe(macd_data.get("histogram"), 0)
    macd_crossover = macd_data.get("crossover", "none")
    macd_hist_dir = macd_data.get("histogram_direction", "flat")

    bb_data = indicators.get("bollinger") or {}
    bb_position = _safe(bb_data.get("position_pct"), 50)
    bb_width = _safe(bb_data.get("width_pct"), 10)

    return_skew = _safe(indicators.get("return_skew_60d"), 0)

    # === 因子评分 (与 forecast_engine._calc_probabilities 完全一致) ===
    score = 0.0
    reasons: List[str] = []
    up_triggers: List[str] = []
    down_triggers: List[str] = []

    # 1. 趋势因子
    if period == 1:
        trend_weight = 0.55
    elif period == 3:
        trend_weight = 0.75
    else:
        trend_weight = 1.0

    if "多头排列" in str(trend) or "上升" in str(trend):
        score += 30 * trend_weight
        reasons.append("均线多头排列，趋势偏强")
        up_triggers.append("均线多头排列持续，且未出现高位放量滞涨")
        down_triggers.append("均线出现死叉，或跌破60日均线支撑")
    elif "空头排列" in str(trend) or "下降" in str(trend):
        score -= 35 * trend_weight
        reasons.append("均线空头排列，趋势偏弱")
        up_triggers.append("出现放量反弹且站上20日均线，均线开始走平")
        down_triggers.append("空头排列延续，继续创新低")
    elif "偏多" in str(trend):
        score += 15 * trend_weight
        reasons.append("均线偏多震荡")
    elif "偏空" in str(trend):
        score -= 20 * trend_weight
        reasons.append("均线偏空震荡")
    else:
        reasons.append("均线横盘整理，缺乏明确方向")

    # 2. 近期收益因子
    if period == 1:
        period_returns = [(1, ret_1d), (5, ret_5trading), (7, ret_7d)]
    elif period == 3:
        period_returns = [(1, ret_1d), (5, ret_5trading), (7, ret_7d)]
    elif period == 7:
        period_returns = [(5, ret_5trading), (7, ret_7d), (30, ret_30d)]
    else:
        period_returns = [(30, ret_30d), (60, ret_60d), (90, ret_90d)]

    for days, ret_val in period_returns:
        if days <= 5:
            if ret_val > 2.5:
                score += 12
                reasons.append(f"近{days}个交易日涨幅较强({ret_val}%)，短线动能偏强")
                up_triggers.append(f"近{days}个交易日动能延续且回撤不扩大")
                down_triggers.append("短线快速上涨后出现回吐，需防止冲高回落")
            elif ret_val > 1:
                score += 7
            elif ret_val > 0:
                score += 3
            elif ret_val > -1:
                score -= 3
            elif ret_val > -2.5:
                score -= 8
                reasons.append(f"近{days}个交易日下跌({ret_val}%)")
            else:
                score -= 14
                reasons.append(f"近{days}个交易日跌幅较大({ret_val}%)，短线承压")
                down_triggers.append("短线跌势未止，继续跌破前低")
        elif ret_val > 10:
            score += 12
            reasons.append(f"近{days}天涨幅较大({ret_val}%)，短期动能强")
            up_triggers.append(f"近{days}天涨幅延续且成交量配合")
            down_triggers.append(f"近{days}天涨幅过快后出现高位放量回落")
        elif ret_val > 5:
            score += 8
        elif ret_val > 0:
            score += 3
        elif ret_val > -3:
            score -= 3
        elif ret_val > -7:
            score -= 10
            reasons.append(f"近{days}天下跌({ret_val}%)")
        elif ret_val > -15:
            score -= 18
            reasons.append(f"近{days}天跌幅较大({ret_val}%)")
        else:
            score -= 25
            reasons.append(f"近{days}天跌幅显著({ret_val}%)，下行压力大")
            down_triggers.append("下跌趋势未止住，继续新低")

    # 3. 回撤因子
    if period in (3, 7):
        dd_thresholds = [(30, dd_30d), (60, dd_60d)]
    else:
        dd_thresholds = [(30, dd_30d), (60, dd_60d), (90, dd_90d)]

    for days, dd_val in dd_thresholds:
        if dd_val > 15:
            score -= 15
            reasons.append(f"近{days}天最大回撤较大({dd_val}%)")
        elif dd_val > 8:
            score -= 8
        elif dd_val > 5:
            score -= 4

    # 4. 波动率因子
    if is_high_volatility and vol_30d > 35:
        score -= 8
        reasons.append(f"高波动基金，近30天波动率{vol_30d}%，不确定性高")
    elif vol_30d > 35:
        score -= 10
        reasons.append(f"近30天波动率极高({vol_30d}%)，方向不确定性强")
    elif vol_30d > 25:
        score -= 5
        reasons.append(f"近30天波动率较高({vol_30d}%)")
    elif vol_30d < 10:
        score += 5
        reasons.append(f"波动率较低({vol_30d}%)，走势相对平稳")

    # 5. 夏普比率
    if period in (3, 7):
        if sharpe_30d > 1:
            score += 8
        elif sharpe_30d < -1:
            score -= 12
            reasons.append("夏普比率为负，风险调整后收益不佳")
        elif sharpe_30d < 0:
            score -= 6
    else:
        if sharpe_60d > 1:
            score += 10
        elif sharpe_60d < -1:
            score -= 12
        elif sharpe_60d < 0:
            score -= 6

    # 6. 位置因子
    if pos_30d > 80 and vol_30d > 25:
        score -= 10
        reasons.append("净值在近30日高位且波动高，追高风险")
        down_triggers.append("高位放量回落，跌破短期均线")
    elif pos_30d > 80:
        score -= 3
    elif pos_30d < 20:
        if "空头" in str(trend) or "下降" in str(trend):
            score -= 8
            reasons.append("净值在近30日低位但趋势仍空头，左侧风险")
            down_triggers.append("继续创新低，下跌趋势未结束")
        else:
            score += 5
            reasons.append("净值在近30日低位，可能接近阶段性底部")
            up_triggers.append("低位企稳，出现连续放量阳线")

    if pos_60d > 85:
        score -= 5
        reasons.append("净值在近60日高位区间")
    if pos_90d < 15:
        score += 3
        reasons.append("净值在近90日低位区间")

    # 7. 反弹/回落
    if rebound > 8:
        score += 5
        reasons.append(f"近期反弹强度{rebound}%")
        up_triggers.append("反弹持续且放量站上关键均线")
        down_triggers.append("反弹遇阻回落，跌破反弹起点")
    if pullback > 8:
        score -= 8
        reasons.append(f"近期从高点回落{pullback}%")
        down_triggers.append("回落幅度扩大，形成下降通道")

    # 8. 胜率
    if win_rate_30d > 60:
        score += 5
    elif win_rate_30d < 40:
        score -= 5
        reasons.append(f"近30天上涨胜率仅{win_rate_30d}%")

    # 9. Calmar
    if period == 30:
        if calmar_90d > 1:
            score += 5
        elif calmar_90d < -1:
            score -= 8
    if calmar_60d > 1:
        score += 3
    elif calmar_60d < -1:
        score -= 5

    # 10. 宏观调整 (回测中为中性)
    if macro_available:
        if risk_appetite == "risk-on":
            score += 5
        elif risk_appetite == "risk-off":
            score -= 8
            reasons.append("宏观风险偏好偏避险")
        if liquidity == "tight":
            score -= 5
            reasons.append("银行间资金面偏紧，流动性收缩不利于风险资产")
        elif liquidity == "loose" and risk_appetite != "risk-off":
            score += 3
            reasons.append("银行间资金面宽松，流动性充裕支持风险资产")

    # 11. 均线与净值关系
    if ma_20 is not None and latest_nav > 0:
        if latest_nav > ma_20:
            score += 3
        else:
            score -= 3
            reasons.append("净值低于20日均线")

    # 12. 1日/3日专用短线信号
    if period == 1:
        if ma_5 is not None and ma_10 is not None and latest_nav > 0:
            if latest_nav > ma_5 > ma_10:
                score += 10
                reasons.append("净值站上5日、10日均线，短线结构偏强")
                up_triggers.append("继续站稳5日均线且单日回撤收窄")
            elif latest_nav < ma_5 < ma_10:
                score -= 12
                reasons.append("净值低于5日、10日均线，短线结构偏弱")
                down_triggers.append("跌破5日均线后继续低于10日均线")

        if consecutive_days >= 3:
            if consecutive_direction == "上涨":
                score += 6
                reasons.append(f"已连续上涨{consecutive_days}天，短线惯性偏强但需防回吐")
                down_triggers.append("连续上涨后单日转跌且跌幅扩大")
            elif consecutive_direction == "下跌":
                score -= 7
                reasons.append(f"已连续下跌{consecutive_days}天，短线仍承压")
                up_triggers.append("连续下跌后出现止跌阳线并收复5日均线")

        if momentum_accel > 1:
            score += 7
            reasons.append(f"5日动能加速度为{momentum_accel}%，短线动能改善")
        elif momentum_accel < -1:
            score -= 7
            reasons.append(f"5日动能加速度为{momentum_accel}%，短线动能转弱")

        if pos_7d > 85 and ret_1d > 0:
            score -= 5
            reasons.append("净值接近7日高位，次日追高回撤风险上升")
        elif pos_7d < 15 and ret_1d < 0 and "空头" not in str(trend):
            score += 4
            reasons.append("净值接近7日低位，存在短线修复可能")

        if pullback_7d > 3:
            score -= 5
            reasons.append(f"近7日从高点回落{pullback_7d}%")
        if rebound_7d > 3:
            score += 4

    elif period == 3:
        if ma_5 is not None and ma_10 is not None and latest_nav > 0:
            if latest_nav > ma_5 > ma_10:
                score += 7
                reasons.append("净值站上5日、10日均线，短线结构偏强")
                up_triggers.append("继续站稳5日均线且3日回撤收窄")
            elif latest_nav < ma_5 < ma_10:
                score -= 8
                reasons.append("净值低于5日、10日均线，短线结构偏弱")
                down_triggers.append("跌破5日均线后继续低于10日均线")

        if consecutive_days >= 3:
            if consecutive_direction == "上涨":
                score += 4
                reasons.append(f"已连续上涨{consecutive_days}天，短线惯性偏强")
                down_triggers.append("连续上涨后单日转跌且跌幅扩大")
            elif consecutive_direction == "下跌":
                score -= 5
                reasons.append(f"已连续下跌{consecutive_days}天，短线仍承压")
                up_triggers.append("连续下跌后出现止跌阳线并收复5日均线")

        if momentum_accel > 1:
            score += 5
            reasons.append(f"5日动能加速度为{momentum_accel}%，动能改善")
        elif momentum_accel < -1:
            score -= 5
            reasons.append(f"5日动能加速度为{momentum_accel}%，动能转弱")

        if pos_7d > 85 and ret_1d > 0:
            score -= 4
            reasons.append("净值接近7日高位，3日追高回撤风险上升")
        elif pos_7d < 15 and ret_1d < 0 and "空头" not in str(trend):
            score += 3
            reasons.append("净值接近7日低位，存在3日修复可能")

        if pullback_7d > 3:
            score -= 3
            reasons.append(f"近7日从高点回落{pullback_7d}%")
        if rebound_7d > 3:
            score += 3

        if ret_5trading > 0 and ret_1d > 0:
            score += 3

    elif period == 7:
        if ret_1d > 0 and ret_5trading > 0 and momentum_accel > 0:
            score += 7
            reasons.append("1日、5日动能同步为正，7日方向偏强")
        elif ret_1d < 0 and ret_5trading < 0 and momentum_accel < 0:
            score -= 8
            reasons.append("1日、5日动能同步为负，7日方向承压")

        if ewma_vol_20d > 0 and vol_30d > 0 and ewma_vol_20d > vol_30d * 1.15:
            score -= 5
            reasons.append("EWMA短线波动高于30日波动，近期不确定性上升")
        elif ewma_vol_20d > 0 and vol_30d > 0 and ewma_vol_20d < vol_30d * 0.85:
            score += 3
            reasons.append("短线波动有所收敛，7日判断稳定性略有改善")

    # 13. QDII 调整 (回测中通常为 False)
    if is_qdii and macro_available:
        if overseas == "bearish":
            score -= 10
            reasons.append("海外市场偏弱，QDII基金可能承压")
        elif overseas == "bullish":
            score += 8
            reasons.append("海外市场偏强，有利于QDII基金")

    # 14. 中国权益调整
    if is_china_equity and macro_available:
        if risk_appetite == "risk-on":
            score += 4
            reasons.append("国内权益类基金受风险偏好改善支撑")
        elif risk_appetite == "risk-off":
            score -= 6
            reasons.append("国内权益类基金受风险偏好走弱压制")

    # 15. 防御型基金降权
    if is_defensive_fund:
        score *= 0.75
        reasons.append("债券/货币等低波动品类，涨跌弹性相对有限")

    # 16. 波动率体制
    if volatility_regime == "高波动":
        score -= 3
        reasons.append("当前波动率处于较高分位，预测误差可能放大")
    elif volatility_regime == "低波动" and period in (1, 3, 7):
        score += 2

    # 17. RSI 因子
    if rsi_14 and rsi_14 > 0:
        if rsi_14 > 75:
            score -= 10
            reasons.append(f"RSI(14)={rsi_14}，处于超买区间，短期回调风险累积")
            down_triggers.append("RSI从超买区间回落，配合量能放大")
        elif rsi_14 > 65:
            score -= 4
            reasons.append(f"RSI(14)={rsi_14}，偏强但接近超买")
        elif rsi_14 < 25:
            score += 10
            reasons.append(f"RSI(14)={rsi_14}，处于超卖区间，技术性反弹概率上升")
            up_triggers.append("RSI从超卖区间回升，配合量能放大")
        elif rsi_14 < 35:
            score += 4
            reasons.append(f"RSI(14)={rsi_14}，偏弱但接近超卖，关注企稳信号")
        if rsi_6 and rsi_6 > 0 and rsi_6 > rsi_14 + 5:
            score += 4
            reasons.append("短期RSI上穿长期RSI，短线动能改善")
        elif rsi_6 and rsi_6 > 0 and rsi_6 < rsi_14 - 5:
            score -= 4
            reasons.append("短期RSI下穿长期RSI，短线动能转弱")

    # 18. MACD 因子
    if macd_data:
        if macd_crossover == "golden":
            if period <= 7:
                score += 12
                reasons.append("MACD金叉，技术面发出看多信号")
                up_triggers.append("金叉后DIF继续上行且柱状线扩大")
                down_triggers.append("金叉失败，DIF重新下穿DEA")
            else:
                score += 6
                reasons.append("MACD金叉，中期趋势可能转好")
        elif macd_crossover == "dead":
            if period <= 7:
                score -= 12
                reasons.append("MACD死叉，技术面发出看空信号")
                down_triggers.append("死叉后DIF继续下行且柱状线扩大")
                up_triggers.append("死叉失效，DIF重新上穿DEA")
            else:
                score -= 6
                reasons.append("MACD死叉，中期趋势可能转弱")
        if macd_hist_dir == "rising" and macd_hist < 0:
            score += 3
            reasons.append("MACD绿柱收窄，空方动能减弱")
        elif macd_hist_dir == "falling" and macd_hist > 0:
            score -= 3
            reasons.append("MACD红柱收窄，多方动能减弱")
        elif macd_hist_dir == "falling" and macd_hist < 0:
            score -= 5
            reasons.append("MACD绿柱扩大，空方动能增强")
        elif macd_hist_dir == "rising" and macd_hist > 0:
            score += 5
            reasons.append("MACD红柱扩大，多方动能增强")

    # 19. 布林带因子
    if bb_data:
        if bb_position >= 95:
            score -= 6
            reasons.append("净值触及布林带上轨，短期超买，回档压力增大")
            down_triggers.append("从布林带上轨回落且跌破中轨")
        elif bb_position >= 80:
            score -= 2
        elif bb_position <= 5:
            score += 6
            reasons.append("净值触及布林带下轨，短期超卖，技术反弹概率上升")
            up_triggers.append("从布林带下轨反弹且站上中轨")
        elif bb_position <= 20:
            score += 2
        if bb_width > 20 and period >= 7:
            score -= 3
            reasons.append(f"布林带宽度{bb_width}%，波动较大，方向不确定性高")
        elif bb_width < 5 and period >= 3:
            score += 2
            reasons.append("布林带收窄，可能酝酿方向性突破")

    # 20. 偏度因子
    if period >= 7:
        if return_skew < -0.8:
            score -= 5
            reasons.append(f"近期收益率左偏（skew={return_skew}），极端负收益出现概率偏高")
        elif return_skew > 0.8:
            score += 3
            reasons.append(f"近期收益率右偏（skew={return_skew}），正收益分布占优")

    # 去重
    reasons = list(dict.fromkeys(reasons))
    up_triggers = list(dict.fromkeys(up_triggers))[:4]
    down_triggers = list(dict.fromkeys(down_triggers))[:4]

    return score, reasons, up_triggers, down_triggers


# ============================================================
# 辅助计算函数
# ============================================================

def _safe(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _ret(nav: np.ndarray, lookback: int) -> float:
    """计算最近 lookback 个交易日的收益率 (%)"""
    if len(nav) <= lookback:
        return 0.0
    return round((nav[-1] / nav[-1 - lookback] - 1) * 100, 2)


def _ma(nav: np.ndarray, window: int) -> Optional[float]:
    if len(nav) < window:
        return None
    return round(float(np.mean(nav[-window:])), 4)


def _classify_trend_from_array(nav: np.ndarray) -> str:
    """从净值数组判断均线趋势"""
    ma5 = _ma(nav, 5)
    ma10 = _ma(nav, 10)
    ma20 = _ma(nav, 20)
    ma60 = _ma(nav, 60)
    latest = nav[-1]

    if ma5 and ma10 and ma20 and ma60:
        if ma5 > ma10 > ma20 > ma60 and latest > ma5:
            return "多头排列"
        elif ma5 < ma10 < ma20 < ma60 and latest < ma5:
            return "空头排列"
        elif ma5 > ma10 and ma20 > ma60:
            return "偏多震荡"
        elif ma5 < ma10 and ma20 < ma60:
            return "偏空震荡"

    if ma5 and ma10:
        if ma5 > ma10 and latest > ma5:
            return "偏多震荡"
        elif ma5 < ma10 and latest < ma5:
            return "偏空震荡"

    return "横盘整理"


def _max_drawdown(nav: np.ndarray, window: int) -> float:
    """计算窗口期内最大回撤 (%)"""
    if len(nav) < 2:
        return 0.0
    segment = nav[-window:]
    peak = segment[0]
    max_dd = 0.0
    for val in segment:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _annualized_vol(returns: np.ndarray, window: int) -> float:
    if len(returns) < 2:
        return 0.0
    r = returns[-window:]
    if len(r) < 2:
        return 0.0
    return round(float(np.std(r, ddof=1) * np.sqrt(250) * 100), 2)


def _downside_vol(returns: np.ndarray, window: int) -> float:
    if len(returns) < 2:
        return 0.0
    r = returns[-window:]
    neg = r[r < 0]
    if len(neg) < 2:
        return 0.0
    return round(float(np.std(neg, ddof=1) * np.sqrt(250) * 100), 2)


def _sharpe(returns: np.ndarray, window: int) -> float:
    if len(returns) < 2:
        return 0.0
    r = returns[-window:]
    mu = np.mean(r)
    sigma = np.std(r, ddof=1)
    if sigma == 0:
        return 0.0
    return round(float(mu / sigma * np.sqrt(250)), 2)


def _position_in_range(nav: np.ndarray, window: int) -> float:
    if len(nav) < 2:
        return 50.0
    segment = nav[-window:]
    low, high = np.min(segment), np.max(segment)
    if high == low:
        return 50.0
    return round(float((nav[-1] - low) / (high - low) * 100), 1)


def _rebound(nav: np.ndarray, window: int) -> float:
    """从窗口期最低点反弹幅度 (%)"""
    if len(nav) < 2:
        return 0.0
    segment = nav[-window:]
    low = np.min(segment)
    if low == 0:
        return 0.0
    return round(float((nav[-1] - low) / low * 100), 2)


def _pullback(nav: np.ndarray, window: int) -> float:
    """从窗口期最高点回落幅度 (%)"""
    if len(nav) < 2:
        return 0.0
    segment = nav[-window:]
    high = np.max(segment)
    if high == 0:
        return 0.0
    return round(float((high - nav[-1]) / high * 100), 2)


def _rsi(nav: np.ndarray, window: int) -> Optional[float]:
    """计算 RSI"""
    if len(nav) < window + 1:
        return None
    diffs = np.diff(nav[-window - 1:])
    gains = np.sum(diffs[diffs > 0]) if np.any(diffs > 0) else 0
    losses = -np.sum(diffs[diffs < 0]) if np.any(diffs < 0) else 0
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return round(float(100 - 100 / (1 + rs)), 1)


def _macd(nav: np.ndarray) -> Dict[str, Any]:
    """计算 MACD 指标"""
    if len(nav) < 35:
        return {"histogram": 0, "crossover": "none", "histogram_direction": "flat"}

    def ema(data, span):
        alpha = 2 / (span + 1)
        result = [data[0]]
        for x in data[1:]:
            result.append(alpha * x + (1 - alpha) * result[-1])
        return np.array(result)

    ema12 = ema(nav, 12)
    ema26 = ema(nav, 26)
    dif = ema12 - ema26
    dea = ema(dif, 9)
    histogram = 2 * (dif - dea)

    current_hist = float(histogram[-1])
    prev_hist = float(histogram[-2]) if len(histogram) >= 2 else 0

    # 金叉/死叉检测
    crossover = "none"
    if len(dif) >= 3 and len(dea) >= 3:
        if dif[-2] <= dea[-2] and dif[-1] > dea[-1]:
            crossover = "golden"
        elif dif[-2] >= dea[-2] and dif[-1] < dea[-1]:
            crossover = "dead"

    hist_dir = "flat"
    if len(histogram) >= 3:
        if histogram[-1] > histogram[-2] > histogram[-3]:
            hist_dir = "rising"
        elif histogram[-1] < histogram[-2] < histogram[-3]:
            hist_dir = "falling"

    return {
        "histogram": round(current_hist, 6),
        "crossover": crossover,
        "histogram_direction": hist_dir,
    }


def _bollinger(nav: np.ndarray) -> Dict[str, Any]:
    """计算布林带"""
    if len(nav) < 20:
        return {"position_pct": 50, "width_pct": 10}
    segment = nav[-20:]
    middle = float(np.mean(segment))
    std = float(np.std(segment, ddof=1))
    upper = middle + 2 * std
    lower = middle - 2 * std
    width_pct = (upper - lower) / middle * 100 if middle > 0 else 10
    if upper == lower:
        position_pct = 50.0
    else:
        position_pct = (nav[-1] - lower) / (upper - lower) * 100
    return {
        "position_pct": round(max(0, min(100, position_pct)), 1),
        "width_pct": round(width_pct, 2),
    }


def _skew(returns: np.ndarray, window: int) -> float:
    if len(returns) < 3:
        return 0.0
    r = returns[-window:]
    mu = np.mean(r)
    sigma = np.std(r, ddof=1)
    if sigma == 0:
        return 0.0
    n = len(r)
    return round(float(np.sum((r - mu) ** 3) / (n * sigma ** 3)), 2)


def _momentum_accel(nav: np.ndarray) -> float:
    """5日动能加速度"""
    if len(nav) < 6:
        return 0.0
    ret_recent = (nav[-1] / nav[-3] - 1) * 100 if len(nav) >= 3 else 0
    ret_prior = (nav[-4] / nav[-6] - 1) * 100 if len(nav) >= 6 else 0
    return round(ret_recent - ret_prior, 2)


def _ewma_vol(returns: np.ndarray) -> float:
    """EWMA 年化波动率"""
    if len(returns) < 2:
        return 0.0
    lb = min(20, len(returns))
    r = returns[-lb:]
    ewma_var = r[0] ** 2
    decay = 0.94
    for i in range(1, len(r)):
        ewma_var = decay * ewma_var + (1 - decay) * r[i] ** 2
    return round(float(np.sqrt(ewma_var) * np.sqrt(250) * 100), 2)


def _vol_percentile(returns: np.ndarray, window: int) -> float:
    """波动率在窗口内的分位"""
    if len(returns) < 10:
        return 50.0
    w = min(window, len(returns))
    vols = []
    for i in range(w, len(returns) + 1):
        seg = returns[i - w:i]
        if len(seg) >= 5:
            vols.append(float(np.std(seg, ddof=1)))
    if not vols:
        return 50.0
    current_vol = float(np.std(returns[-w:], ddof=1))
    return round(float(np.sum(np.array(vols) < current_vol) / len(vols) * 100), 1)


def _vol_regime(percentile: float) -> str:
    if percentile > 75:
        return "高波动"
    elif percentile < 25:
        return "低波动"
    return "正常"


def _calmar(nav: np.ndarray, returns: np.ndarray, window: int) -> float:
    """Calmar 比率"""
    if len(returns) < 2:
        return 0.0
    r = returns[-window:]
    ann_ret = float(np.mean(r) * 250 * 100)
    dd = _max_drawdown(nav, window)
    if dd == 0:
        return 0.0
    return round(ann_ret / dd, 2)


def _consecutive_days(nav: np.ndarray) -> Dict[str, Any]:
    """连续涨跌天数"""
    if len(nav) < 2:
        return {"days": 0, "direction": ""}
    diffs = np.diff(nav)
    if len(diffs) == 0:
        return {"days": 0, "direction": ""}

    direction = "上涨" if diffs[-1] > 0 else ("下跌" if diffs[-1] < 0 else "平")
    count = 0
    for d in reversed(diffs):
        if (direction == "上涨" and d > 0) or (direction == "下跌" and d < 0):
            count += 1
        else:
            break
    return {"days": count, "direction": direction}


def _daily_stats(returns: np.ndarray, window: int) -> Dict[str, float]:
    if len(returns) < 2:
        return {"mean": 0.0, "max": 0.0, "min": 0.0}
    r = returns[-window:] * 100
    return {
        "mean": round(float(np.mean(r)), 2),
        "max": round(float(np.max(r)), 2),
        "min": round(float(np.min(r)), 2),
    }


def _win_rate(returns: np.ndarray, window: int) -> float:
    if len(returns) < 2:
        return 50.0
    r = returns[-window:]
    return round(float(np.sum(r > 0) / len(r) * 100), 1)
