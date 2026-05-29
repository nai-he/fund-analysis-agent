"""
技术指标计算模块
基于基金历史净值数据计算各项技术指标

重要说明：
- 自然日口径：从最新净值日期往前推 N 个自然日，查找该日期或之前最近的净值
- 交易日口径：使用最近 N 条净值记录（约 N 个交易日）
- 阶段涨跌默认按单位净值计算，若基金期间分红，可能与部分平台的复权收益口径存在差异
"""
import logging
from typing import Dict, Any, Optional
from datetime import timedelta

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def calculate_metrics(nav_df: pd.DataFrame) -> Dict[str, Any]:
    """
    计算所有技术指标
    输入：标准化的净值 DataFrame（含 净值日期、单位净值、日增长率、累计净值）
    输出：结构化指标 dict
    """
    if nav_df is None or nav_df.empty:
        return {"error": "无净值数据"}

    df = nav_df.sort_values("净值日期", ascending=True).copy()

    if "单位净值" not in df.columns:
        return {"error": "净值数据缺少单位净值列"}

    df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
    df = df.dropna(subset=["单位净值"])

    if len(df) < 5:
        return {"error": f"净值数据不足（仅 {len(df)} 条）"}

    result: Dict[str, Any] = {}

    # 基本信息
    try:
        result["data_days"] = len(df)
        result["data_start"] = df["净值日期"].iloc[0].strftime("%Y-%m-%d") if hasattr(df["净值日期"].iloc[0], "strftime") else str(df["净值日期"].iloc[0])
        result["data_end"] = df["净值日期"].iloc[-1].strftime("%Y-%m-%d") if hasattr(df["净值日期"].iloc[-1], "strftime") else str(df["净值日期"].iloc[-1])
        result["latest_nav"] = round(float(df["单位净值"].iloc[-1]), 4)
    except Exception:
        result["data_days"] = len(df)
        result["latest_nav"] = round(float(df["单位净值"].iloc[-1]), 4)

    # 最新净值日期
    latest_date = df["净值日期"].iloc[-1]
    if hasattr(latest_date, "strftime"):
        latest_date = latest_date
    else:
        latest_date = pd.Timestamp.now()

    # =========================================
    # 自然日口径收益率
    # =========================================
    r7 = _calc_calendar_return(df, latest_date, 7)
    result["return_7d_calendar"] = r7["return"]
    result["period_7d_calendar"] = r7["period"]

    r30 = _calc_calendar_return(df, latest_date, 30)
    result["return_30d_calendar"] = r30["return"]
    result["period_30d_calendar"] = r30["period"]

    r90 = _calc_calendar_return(df, latest_date, 90)
    result["return_90d_calendar"] = r90["return"]
    result["period_90d_calendar"] = r90["period"]

    # 自然日口径最大回撤
    result["max_drawdown_7d_calendar"] = _calc_calendar_max_drawdown(df, latest_date, 7)
    result["max_drawdown_30d_calendar"] = _calc_calendar_max_drawdown(df, latest_date, 30)
    result["max_drawdown_90d_calendar"] = _calc_calendar_max_drawdown(df, latest_date, 90)

    # 累计净值口径（如果有数据）
    has_acc_nav = "累计净值" in df.columns and df["累计净值"].notna().sum() > 5
    if has_acc_nav:
        df["累计净值"] = pd.to_numeric(df["累计净值"], errors="coerce")
        ra30 = _calc_calendar_return(df, latest_date, 30, nav_col="累计净值")
        result["return_30d_acc_nav"] = ra30["return"]
        ra90 = _calc_calendar_return(df, latest_date, 90, nav_col="累计净值")
        result["return_90d_acc_nav"] = ra90["return"]

    # =========================================
    # 交易日口径收益率
    # =========================================
    result["return_1trading"] = _calc_trading_return(df, 2)
    result["return_5trading"] = _calc_trading_return(df, 6)
    result["return_10trading"] = _calc_trading_return(df, 11)
    result["return_20trading"] = _calc_trading_return(df, 21)
    result["return_60trading"] = _calc_trading_return(df, 61)

    # 交易日口径最大回撤
    result["max_drawdown_5trading"] = _calc_trading_max_drawdown(df, 6)
    result["max_drawdown_20trading"] = _calc_trading_max_drawdown(df, 21)
    result["max_drawdown_60trading"] = _calc_trading_max_drawdown(df, 61)

    # =========================================
    # 向后兼容：旧字段名映射到自然日口径
    # =========================================
    result["return_7d"] = result["return_7d_calendar"]
    result["return_30d"] = result["return_30d_calendar"]
    result["return_60d"] = _calc_calendar_return(df, latest_date, 60)["return"]
    result["return_90d"] = result["return_90d_calendar"]
    result["max_drawdown_7d"] = result["max_drawdown_7d_calendar"]
    result["max_drawdown_30d"] = result["max_drawdown_30d_calendar"]
    result["max_drawdown_60d"] = _calc_calendar_max_drawdown(df, latest_date, 60)
    result["max_drawdown_90d"] = result["max_drawdown_90d_calendar"]

    # =========================================
    # 年化波动率（基于日收益率）
    # =========================================
    result["volatility_30d"] = _calc_calendar_volatility(df, latest_date, 30)
    result["volatility_60d"] = _calc_calendar_volatility(df, latest_date, 60)
    result["volatility_90d"] = _calc_calendar_volatility(df, latest_date, 90)

    # =========================================
    # 下行波动率
    # =========================================
    result["downside_volatility_30d"] = _calc_calendar_downside_volatility(df, latest_date, 30)
    result["downside_volatility_60d"] = _calc_calendar_downside_volatility(df, latest_date, 60)

    # =========================================
    # 均线
    # =========================================
    result["ma_5"] = _calc_ma(df, 5)
    result["ma_10"] = _calc_ma(df, 10)
    result["ma_20"] = _calc_ma(df, 20)
    result["ma_60"] = _calc_ma(df, 60)

    # =========================================
    # 均线趋势
    # =========================================
    result["trend"] = _calc_trend(df)

    # =========================================
    # 区间位置（基于自然日）
    # =========================================
    result["position_in_7d_range"] = _calc_calendar_position_in_range(df, latest_date, 7)
    result["position_in_30d_range"] = _calc_calendar_position_in_range(df, latest_date, 30)
    result["position_in_60d_range"] = _calc_calendar_position_in_range(df, latest_date, 60)
    result["position_in_90d_range"] = _calc_calendar_position_in_range(df, latest_date, 90)

    # =========================================
    # 反弹强度 / 回落幅度
    # =========================================
    result["rebound_from_7d_low"] = _calc_calendar_rebound(df, latest_date, 7)
    result["pullback_from_7d_high"] = _calc_calendar_pullback(df, latest_date, 7)
    result["rebound_from_30d_low"] = _calc_calendar_rebound(df, latest_date, 30)
    result["pullback_from_30d_high"] = _calc_calendar_pullback(df, latest_date, 30)

    # =========================================
    # 短线动能与波动状态
    # =========================================
    result["momentum_acceleration_5d"] = _calc_momentum_acceleration(df, 5)
    result["ewma_volatility_20d"] = _calc_ewma_volatility(df, 20)
    result["volatility_percentile_30d"] = _calc_volatility_percentile(df, 30)
    result["volatility_regime_30d"] = _classify_volatility_regime(result["volatility_percentile_30d"])

    # =========================================
    # Calmar 比率（基于自然日收益和回撤）
    # =========================================
    result["calmar_60d"] = _calc_calendar_calmar(df, latest_date, 60)
    result["calmar_90d"] = _calc_calendar_calmar(df, latest_date, 90)

    # =========================================
    # 连续涨跌（基于交易日）
    # =========================================
    result["consecutive_days"] = _calc_consecutive(df)

    # =========================================
    # 近期日收益率统计（近20个交易日）
    # =========================================
    result["daily_stats"] = _calc_daily_stats_trading(df, 20)

    # =========================================
    # 夏普比率
    # =========================================
    result["sharpe_30d"] = _calc_calendar_sharpe(df, latest_date, 30)
    result["sharpe_60d"] = _calc_calendar_sharpe(df, latest_date, 60)

    # =========================================
    # 胜率（交易日口径）
    # =========================================
    result["win_rate_30d"] = _calc_trading_win_rate(df, 20)
    result["win_rate_60d"] = _calc_trading_win_rate(df, 60)

    # QDII 延迟提示
    result["note_nav_delay"] = _check_nav_delay(df)

    # =========================================
    # RSI (相对强弱指标)
    # =========================================
    result["rsi_6"] = _calc_rsi(df, 6)
    result["rsi_14"] = _calc_rsi(df, 14)
    result["rsi_28"] = _calc_rsi(df, 28)

    # =========================================
    # MACD
    # =========================================
    result["macd"] = _calc_macd(df)

    # =========================================
    # 布林带
    # =========================================
    result["bollinger"] = _calc_bollinger(df)

    # =========================================
    # 收益率偏度
    # =========================================
    result["return_skew_60d"] = _calc_return_skew(df, 60)

    logger.info(f"指标计算完成: return_7d_calendar={result.get('return_7d_calendar')}, return_30d_calendar={result.get('return_30d_calendar')}, trend={result.get('trend')}")
    return result


# ============================================================
# 自然日口径计算 helpers
# ============================================================

def _find_nav_at_or_before(df: pd.DataFrame, target_date: pd.Timestamp, nav_col: str = "单位净值") -> Optional[pd.Series]:
    """查找目标日期或之前最近的一条净值记录"""
    candidates = df[df["净值日期"] <= target_date]
    if candidates.empty:
        return None
    return candidates.iloc[-1]


def _calc_calendar_return(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
    nav_col: str = "单位净值",
) -> Dict[str, Any]:
    """
    自然日口径收益率
    latest_date - days → 查找该日期或之前最近的净值作为起始净值
    """
    try:
        if len(df) < 3:
            return {"return": None, "period": None}

        start_target = latest_date - timedelta(days=days)
        start_row = _find_nav_at_or_before(df, start_target, nav_col)
        end_row = df.iloc[-1]

        if start_row is None:
            return {"return": None, "period": None}

        start_nav = float(start_row[nav_col])
        end_nav = float(end_row[nav_col])
        start_date = start_row["净值日期"]
        end_date = end_row["净值日期"]

        if hasattr(start_date, "strftime"):
            start_date_str = start_date.strftime("%Y-%m-%d")
        else:
            start_date_str = str(start_date)
        if hasattr(end_date, "strftime"):
            end_date_str = end_date.strftime("%Y-%m-%d")
        else:
            end_date_str = str(end_date)

        if start_nav == 0:
            return {"return": None, "period": None}

        ret = round((end_nav - start_nav) / start_nav * 100, 2)

        return {
            "return": ret,
            "period": {
                "start_date": start_date_str,
                "end_date": end_date_str,
                "start_nav": round(start_nav, 4),
                "end_nav": round(end_nav, 4),
                "days": days,
                "nav_col": nav_col,
            },
        }
    except Exception as e:
        logger.warning(f"计算自然日 {days} 天收益率失败: {e}")
        return {"return": None, "period": None}


def _calc_calendar_max_drawdown(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径最大回撤"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask].copy()
        if len(period_df) < 3:
            # 扩大范围
            period_df = df.tail(max(3, min(len(df), days // 2)))
        nav_series = period_df["单位净值"].astype(float).values
        peak = nav_series[0]
        max_dd = 0.0
        for v in nav_series:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
        return round(-max_dd * 100, 2)
    except Exception as e:
        logger.warning(f"计算自然日 {days} 天最大回撤失败: {e}")
        return None


def _calc_calendar_volatility(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径年化波动率"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask].copy()
        if len(period_df) < 5:
            period_df = df.tail(max(5, min(len(df), days // 2)))
        returns = _get_returns(period_df)
        if len(returns) < 3:
            return None
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(250)
        return round(annual_vol * 100, 2)
    except Exception as e:
        logger.warning(f"计算自然日 {days} 天波动率失败: {e}")
        return None


def _calc_calendar_downside_volatility(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径下行波动率"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask].copy()
        if len(period_df) < 5:
            period_df = df.tail(max(5, min(len(df), days // 2)))
        returns = _get_returns(period_df)
        if len(returns) < 3:
            return None
        downside = returns[returns < 0]
        if len(downside) < 2:
            return 0.0
        daily_vol = downside.std()
        annual_vol = daily_vol * np.sqrt(250)
        return round(annual_vol * 100, 2)
    except Exception as e:
        logger.warning(f"计算自然日下行波动率失败: {e}")
        return None


def _calc_calendar_position_in_range(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径区间位置"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask]
        if len(period_df) < 5:
            period_df = df.tail(max(5, min(len(df), days // 2)))
        nav = period_df["单位净值"].astype(float)
        high = nav.max()
        low = nav.min()
        current = nav.iloc[-1]
        if high == low:
            return 50.0
        return round((current - low) / (high - low) * 100, 1)
    except Exception as e:
        logger.warning(f"计算自然日 {days} 天区间位置失败: {e}")
        return None


def _calc_calendar_rebound(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径反弹强度"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask]
        if len(period_df) < 5:
            return None
        nav = period_df["单位净值"].astype(float)
        low = nav.min()
        current = nav.iloc[-1]
        if low == 0:
            return None
        return round((current - low) / low * 100, 2)
    except Exception:
        return None


def _calc_calendar_pullback(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径回落幅度"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask]
        if len(period_df) < 5:
            return None
        nav = period_df["单位净值"].astype(float)
        high = nav.max()
        current = nav.iloc[-1]
        if high == 0:
            return None
        return round((high - current) / high * 100, 2)
    except Exception:
        return None


def _calc_calendar_calmar(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径 Calmar 比率"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask].copy()
        if len(period_df) < 5:
            period_df = df.tail(max(5, min(len(df), days // 2)))
        returns = _get_returns(period_df)
        if len(returns) < 3:
            return None
        annual_return = returns.mean() * 250
        dd = _calc_calendar_max_drawdown(df, latest_date, days)
        if dd is None or dd == 0:
            return None
        return round(abs(annual_return / (abs(dd) / 100)), 2)
    except Exception:
        return None


def _calc_calendar_sharpe(
    df: pd.DataFrame,
    latest_date: pd.Timestamp,
    days: int,
) -> Optional[float]:
    """自然日口径夏普比率"""
    try:
        start_target = latest_date - timedelta(days=days)
        mask = df["净值日期"] >= start_target
        period_df = df[mask]
        if len(period_df) < 5:
            period_df = df.tail(max(5, min(len(df), days // 2)))
        returns = _get_returns(period_df)
        if len(returns) < 5:
            return None
        daily_mean = returns.mean()
        daily_std = returns.std()
        if daily_std == 0:
            return 0.0
        return round(float((daily_mean / daily_std) * np.sqrt(250)), 2)
    except Exception:
        return None


# ============================================================
# 交易日口径计算 helpers
# ============================================================

def _calc_trading_return(df: pd.DataFrame, trading_days: int) -> Optional[float]:
    """交易日口径收益率：使用最近 N 条净值记录"""
    try:
        if len(df) < 2:
            return None
        period_df = df.tail(trading_days)
        if len(period_df) < 2:
            period_df = df.tail(len(df))
        start_nav = float(period_df["单位净值"].iloc[0])
        end_nav = float(period_df["单位净值"].iloc[-1])
        return round((end_nav - start_nav) / start_nav * 100, 2)
    except Exception as e:
        logger.warning(f"计算交易日 {trading_days} 收益率失败: {e}")
        return None


def _calc_trading_max_drawdown(df: pd.DataFrame, trading_days: int) -> Optional[float]:
    """交易日口径最大回撤"""
    try:
        period_df = df.tail(trading_days).copy()
        if len(period_df) < 3:
            return None
        nav_series = period_df["单位净值"].astype(float).values
        peak = nav_series[0]
        max_dd = 0.0
        for v in nav_series:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
        return round(-max_dd * 100, 2)
    except Exception as e:
        logger.warning(f"计算交易日 {trading_days} 最大回撤失败: {e}")
        return None


def _calc_trading_win_rate(df: pd.DataFrame, trading_days: int) -> Optional[float]:
    """交易日口径上涨胜率"""
    try:
        period_df = df.tail(trading_days)
        returns = _get_returns(period_df) * 100
        if len(returns) < 3:
            return None
        positive = (returns > 0).sum()
        return round(positive / len(returns) * 100, 1)
    except Exception:
        return None


def _calc_daily_stats_trading(df: pd.DataFrame, trading_days: int) -> Dict[str, Any]:
    """近 N 个交易日收益率统计"""
    try:
        period_df = df.tail(trading_days)
        returns = _get_returns(period_df) * 100
        if len(returns) < 3:
            return {}
        return {
            "mean": round(float(returns.mean()), 2),
            "max": round(float(returns.max()), 2),
            "min": round(float(returns.min()), 2),
            "positive_days": int((returns > 0).sum()),
            "negative_days": int((returns < 0).sum()),
        }
    except Exception:
        return {}


def _calc_momentum_acceleration(df: pd.DataFrame, window: int = 5) -> Optional[float]:
    """短线动能加速度：最近N日收益 - 前一段N日收益。"""
    try:
        if len(df) < window * 2 + 1:
            return None
        nav = df["单位净值"].astype(float)
        current = nav.iloc[-1] / nav.iloc[-window - 1] - 1
        previous = nav.iloc[-window - 1] / nav.iloc[-window * 2 - 1] - 1
        return round(float((current - previous) * 100), 2)
    except Exception as e:
        logger.warning(f"计算{window}日动能加速度失败: {e}")
        return None


def _calc_ewma_volatility(df: pd.DataFrame, trading_days: int = 20, lam: float = 0.94) -> Optional[float]:
    """EWMA年化波动率，对最近波动变化更敏感。"""
    try:
        period_df = df.tail(max(trading_days + 1, 6))
        returns = _get_returns(period_df)
        if len(returns) < 5:
            return None
        variance = float(returns.iloc[0] ** 2)
        for r in returns.iloc[1:]:
            variance = lam * variance + (1 - lam) * float(r ** 2)
        return round(float(np.sqrt(variance) * np.sqrt(250) * 100), 2)
    except Exception as e:
        logger.warning(f"计算EWMA波动率失败: {e}")
        return None


def _calc_volatility_percentile(df: pd.DataFrame, window: int = 30) -> Optional[float]:
    """当前波动率在近一年滚动波动率中的分位，用于识别波动压缩/扩张。"""
    try:
        returns = _get_returns(df)
        if len(returns) < window + 10:
            return None
        rolling_vol = returns.rolling(window).std().dropna() * np.sqrt(250) * 100
        if rolling_vol.empty:
            return None
        current = rolling_vol.iloc[-1]
        percentile = (rolling_vol <= current).sum() / len(rolling_vol) * 100
        return round(float(percentile), 1)
    except Exception as e:
        logger.warning(f"计算波动率分位失败: {e}")
        return None


def _classify_volatility_regime(percentile: Optional[float]) -> str:
    if percentile is None:
        return "未知"
    if percentile >= 75:
        return "高波动"
    if percentile <= 25:
        return "低波动"
    return "常态波动"


# ============================================================
# 通用 helpers（均线、趋势、连续涨跌等）
# ============================================================

def _calc_ma(df: pd.DataFrame, window: int) -> Optional[float]:
    try:
        if len(df) < window:
            return None
        ma = df["单位净值"].astype(float).rolling(window=window).mean().iloc[-1]
        return round(float(ma), 4) if not pd.isna(ma) else None
    except Exception:
        return None


def _calc_trend(df: pd.DataFrame) -> Optional[str]:
    try:
        if len(df) < 60:
            if len(df) < 30:
                return "数据不足，无法判断趋势"
            nav = df["单位净值"].astype(float)
            ma5 = nav.rolling(window=5).mean().iloc[-1]
            ma10 = nav.rolling(window=10).mean().iloc[-1]
            ma20 = nav.rolling(window=20).mean().iloc[-1]
            current = nav.iloc[-1]
        else:
            nav = df["单位净值"].astype(float)
            ma5 = nav.rolling(window=5).mean().iloc[-1]
            ma10 = nav.rolling(window=10).mean().iloc[-1]
            ma20 = nav.rolling(window=20).mean().iloc[-1]
            ma60 = nav.rolling(window=60).mean().iloc[-1]
            current = nav.iloc[-1]

            if current > ma5 > ma10 > ma20 > ma60:
                return "多头排列（上升趋势）"
            if current < ma5 < ma10 < ma20 < ma60:
                return "空头排列（下降趋势）"

        if current > ma20 and ma5 > ma20:
            return "偏多震荡"
        elif current < ma20 and ma5 < ma20:
            return "偏空震荡"
        else:
            return "横盘整理"
    except Exception as e:
        logger.warning(f"计算趋势失败: {e}")
        return None


def _calc_consecutive(df: pd.DataFrame) -> Dict[str, Any]:
    try:
        if "日增长率" not in df.columns:
            return {"direction": "未知", "days": 0}
        recent_returns = df["日增长率"].dropna().tail(30)
        if len(recent_returns) < 2:
            return {"direction": "未知", "days": 0}
        days = 0
        direction = "平盘"
        for i in range(len(recent_returns) - 1, -1, -1):
            val = float(recent_returns.iloc[i])
            if val > 0.01:
                if direction == "平盘":
                    direction = "上涨"
                    days = 1
                elif direction == "上涨":
                    days += 1
                else:
                    break
            elif val < -0.01:
                if direction == "平盘":
                    direction = "下跌"
                    days = 1
                elif direction == "下跌":
                    days += 1
                else:
                    break
            else:
                if days > 0:
                    break
                days = 0
        return {"direction": direction, "days": days}
    except Exception:
        return {"direction": "未知", "days": 0}


def _get_returns(df: pd.DataFrame):
    """从 DataFrame 获取日收益率序列（小数形式）"""
    if "日增长率" in df.columns:
        returns = pd.to_numeric(df["日增长率"], errors="coerce").dropna() / 100
    else:
        returns = df["单位净值"].astype(float).pct_change().dropna()
    return returns


def _check_nav_delay(df: pd.DataFrame) -> Optional[str]:
    """检查净值延迟"""
    try:
        latest = df["净值日期"].iloc[-1]
        if hasattr(latest, "strftime"):
            latest_date = latest
        else:
            latest_date = pd.Timestamp(latest)
        days_behind = (pd.Timestamp.now() - latest_date).days
        if days_behind >= 2:
            return f"最新净值日期为{latest_date.strftime('%Y-%m-%d')}，延迟约{days_behind}天"
        return None
    except Exception:
        return None


def _calc_rsi(df: pd.DataFrame, window: int = 14) -> Optional[float]:
    """计算 RSI 相对强弱指标"""
    try:
        returns = _get_returns(df) * 100
        if len(returns) < window + 1:
            return None
        gains = returns.clip(lower=0)
        losses = (-returns).clip(lower=0)
        avg_gain = gains.ewm(alpha=1/window, adjust=False).mean()
        avg_loss = losses.ewm(alpha=1/window, adjust=False).mean()
        avg_loss_safe = avg_loss.replace(0, np.nan)
        rs = avg_gain / avg_loss_safe
        rsi = 100 - (100 / (1 + rs))
        val = float(rsi.iloc[-1])
        return round(val, 1) if not pd.isna(rsi.iloc[-1]) else None
    except Exception as e:
        logger.warning(f"计算RSI失败: {e}")
        return None


def _calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict[str, Any]]:
    """计算 MACD 指标"""
    try:
        nav = df["单位净值"].astype(float)
        if len(nav) < slow + signal + 2:
            return None
        ema_fast = nav.ewm(span=fast, adjust=False).mean()
        ema_slow = nav.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        macd_curr = float(macd_line.iloc[-1])
        macd_prev2 = float(macd_line.iloc[-3]) if len(macd_line) >= 3 else macd_curr
        signal_curr = float(signal_line.iloc[-1])
        signal_prev2 = float(signal_line.iloc[-3]) if len(signal_line) >= 3 else signal_curr
        hist_curr = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2]) if len(histogram) >= 2 else hist_curr

        if macd_prev2 < signal_prev2 and macd_curr > signal_curr:
            crossover = "golden"
        elif macd_prev2 > signal_prev2 and macd_curr < signal_curr:
            crossover = "dead"
        else:
            crossover = "none"

        return {
            "macd_line": round(macd_curr, 6),
            "signal_line": round(signal_curr, 6),
            "histogram": round(hist_curr, 6),
            "histogram_prev": round(hist_prev, 6),
            "crossover": crossover,
            "histogram_direction": "rising" if hist_curr > hist_prev else "falling" if hist_curr < hist_prev else "flat",
        }
    except Exception as e:
        logger.warning(f"计算MACD失败: {e}")
        return None


def _calc_bollinger(df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> Optional[Dict[str, Any]]:
    """计算布林带位置"""
    try:
        nav = df["单位净值"].astype(float)
        if len(nav) < window:
            return None
        ma = nav.rolling(window=window).mean()
        std = nav.rolling(window=window).std()
        upper = ma + num_std * std
        lower = ma - num_std * std
        curr = float(nav.iloc[-1])
        upper_val = float(upper.iloc[-1])
        lower_val = float(lower.iloc[-1])
        ma_val = float(ma.iloc[-1])
        band_range = upper_val - lower_val
        if band_range == 0:
            position_pct = 50.0
        else:
            position_pct = round((curr - lower_val) / band_range * 100, 1)
        width_pct = round(band_range / ma_val * 100, 2) if ma_val > 0 else 0
        return {
            "position_pct": position_pct,
            "width_pct": width_pct,
            "upper": round(upper_val, 4),
            "lower": round(lower_val, 4),
            "middle": round(ma_val, 4),
        }
    except Exception as e:
        logger.warning(f"计算布林带失败: {e}")
        return None


def _calc_return_skew(df: pd.DataFrame, days: int = 60) -> Optional[float]:
    """计算近N自然日收益率偏度"""
    try:
        returns = _get_returns(df)
        if len(returns) < days // 2:
            return None
        recent = returns.tail(min(days, len(returns)))
        if len(recent) < 10:
            return None
        return round(float(recent.skew()), 2)
    except Exception as e:
        logger.warning(f"计算收益率偏度失败: {e}")
        return None
