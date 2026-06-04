"""External factor builders for user-specified funds.

The 80% trainer must be backtestable, so this module turns disclosed holdings
into a time-series proxy instead of injecting one-off narrative/policy text.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MAX_STOCKS_IN_BASKET = 8
MIN_STOCKS_IN_BASKET = 2
_HOLDINGS_CACHE: Dict[str, Tuple[pd.DataFrame, str]] = {}
_STOCK_HISTORY_CACHE: Dict[Tuple[str, str, str], Optional[pd.DataFrame]] = {}


def build_specific_external_features(
    fund_code: str,
    nav_df: pd.DataFrame,
    fund_name: str = "",
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """Build a stock-basket proxy from the latest disclosed fund holdings."""
    code = str(fund_code or "").strip()
    meta: Dict[str, Any] = {
        "status": "unavailable",
        "sources": [],
        "note": "未取得可回测的重仓股代理因子，当前仅使用基金净值训练。",
    }
    if not code or nav_df is None or nav_df.empty:
        return None, meta

    try:
        holdings, quarter = _get_latest_stock_holdings(code)
        if holdings.empty:
            meta["note"] = "基金重仓股披露数据暂不可用，当前仅使用基金净值训练。"
            return None, meta

        basket_df, used_holdings = _build_stock_basket_series(holdings, nav_df)
        if basket_df is None or basket_df.empty or len(used_holdings) < MIN_STOCKS_IN_BASKET:
            meta["note"] = "已读取重仓股，但股票历史行情不足，当前仅使用基金净值训练。"
            return None, meta

        factor_df = _calculate_basket_features(basket_df)
        if factor_df is None or factor_df.empty:
            return None, meta

        source = {
            "type": "latest_holding_stock_basket",
            "name": f"{fund_name or code}重仓股篮子",
            "quarter": quarter,
            "stock_count": len(used_holdings),
            "holdings": [f"{item['name']}({item['code']})" for item in used_holdings],
        }
        meta = {
            "status": "available",
            "sources": [source],
            "note": "已用最新披露重仓股构建股票篮子代理因子；历史持仓可能变化，因此该因子只作为辅助回测，不等同于基金真实历史持仓。",
        }
        factor_df.attrs["factor_meta"] = meta
        return factor_df, meta
    except Exception as exc:
        logger.warning(f"构建专属基金外部因子失败: {code}, error={exc}")
        meta["note"] = "构建重仓股代理因子失败，当前仅使用基金净值训练。"
        return None, meta


def _get_latest_stock_holdings(fund_code: str) -> Tuple[pd.DataFrame, str]:
    import akshare as ak

    cache_key = str(fund_code or "").strip()
    if cache_key in _HOLDINGS_CACHE:
        cached_df, cached_quarter = _HOLDINGS_CACHE[cache_key]
        return cached_df.copy(), cached_quarter

    frames: List[pd.DataFrame] = []
    current_year = datetime.now().year
    for year in range(current_year, current_year - 4, -1):
        try:
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(year))
            if df is not None and not df.empty:
                frames.append(df.copy())
        except Exception as exc:
            logger.info(f"读取基金持仓失败: {fund_code}, year={year}, error={exc}")

    if not frames:
        result = (pd.DataFrame(), "")
        _HOLDINGS_CACHE[cache_key] = result
        return result

    all_holdings = pd.concat(frames, ignore_index=True)
    required_cols = {"股票代码", "股票名称", "季度"}
    if not required_cols.issubset(set(all_holdings.columns)):
        result = (pd.DataFrame(), "")
        _HOLDINGS_CACHE[cache_key] = result
        return result

    all_holdings["_quarter_key"] = all_holdings["季度"].map(_quarter_key)
    all_holdings = all_holdings[all_holdings["_quarter_key"] > 0]
    if all_holdings.empty:
        result = (pd.DataFrame(), "")
        _HOLDINGS_CACHE[cache_key] = result
        return result

    latest_key = int(all_holdings["_quarter_key"].max())
    latest = all_holdings[all_holdings["_quarter_key"] == latest_key].copy()
    latest["股票代码"] = latest["股票代码"].astype(str).str.extract(r"(\d+)", expand=False).fillna("")
    latest["股票代码"] = latest["股票代码"].str.zfill(6)
    latest["股票名称"] = latest["股票名称"].astype(str)
    latest["占净值比例"] = pd.to_numeric(latest.get("占净值比例"), errors="coerce").fillna(0.0)
    latest = latest[latest["股票代码"].str.len() == 6]
    latest = latest.drop_duplicates(subset=["股票代码"], keep="first")
    latest = latest.sort_values("占净值比例", ascending=False).head(MAX_STOCKS_IN_BASKET)
    quarter = str(latest["季度"].iloc[0]) if not latest.empty else ""
    _HOLDINGS_CACHE[cache_key] = (latest.copy(), quarter)
    return latest, quarter


def _quarter_key(text: Any) -> int:
    match = re.search(r"(\d{4})年(\d+)季度", str(text or ""))
    if not match:
        return 0
    return int(match.group(1)) * 10 + int(match.group(2))


def _build_stock_basket_series(
    holdings: pd.DataFrame,
    nav_df: pd.DataFrame,
) -> Tuple[Optional[pd.DataFrame], List[Dict[str, Any]]]:
    if holdings.empty:
        return None, []

    start_date, end_date = _history_date_range(nav_df)
    price_frames: List[pd.DataFrame] = []
    used_holdings: List[Dict[str, Any]] = []

    total_weight = float(holdings["占净值比例"].sum())
    for _, row in holdings.iterrows():
        stock_code = str(row.get("股票代码", "")).strip()
        stock_name = str(row.get("股票名称", stock_code)).strip() or stock_code
        if not stock_code:
            continue

        hist = _fetch_stock_history(stock_code, start_date, end_date)
        if hist is None or hist.empty:
            continue

        weight = float(row.get("占净值比例") or 0.0)
        if total_weight <= 0:
            weight = 1.0
        price_frames.append(hist.rename(columns={"收盘": stock_code})[["净值日期", stock_code]])
        used_holdings.append({"code": stock_code, "name": stock_name, "weight": weight})

    if len(price_frames) < MIN_STOCKS_IN_BASKET:
        return None, used_holdings

    prices = price_frames[0]
    for frame in price_frames[1:]:
        prices = prices.merge(frame, on="净值日期", how="outer")
    prices = prices.sort_values("净值日期").ffill()

    stock_codes = [item["code"] for item in used_holdings if item["code"] in prices.columns]
    weights = np.array([item["weight"] for item in used_holdings if item["code"] in prices.columns], dtype=float)
    if len(stock_codes) < MIN_STOCKS_IN_BASKET:
        return None, used_holdings
    if not np.isfinite(weights).all() or float(weights.sum()) <= 0:
        weights = np.ones(len(stock_codes), dtype=float)
    weights = weights / float(weights.sum())

    normalized = prices[stock_codes].astype(float).apply(_normalize_price_series)
    basket_nav = normalized.mul(weights, axis=1).sum(axis=1, min_count=1)
    basket = pd.DataFrame({
        "净值日期": prices["净值日期"],
        "factor_nav": basket_nav,
    }).dropna(subset=["factor_nav"])
    return basket, used_holdings


def _history_date_range(nav_df: pd.DataFrame) -> Tuple[str, str]:
    if "净值日期" in nav_df.columns:
        start = pd.to_datetime(nav_df["净值日期"], errors="coerce").min()
        if pd.isna(start):
            start = pd.Timestamp.today() - pd.Timedelta(days=3650)
    else:
        start = pd.Timestamp.today() - pd.Timedelta(days=3650)
    start = start - pd.Timedelta(days=10)
    end = pd.Timestamp.today() + pd.Timedelta(days=1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _fetch_stock_history(stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    import akshare as ak

    cache_key = (str(stock_code or "").strip(), start_date, end_date)
    if cache_key in _STOCK_HISTORY_CACHE:
        cached = _STOCK_HISTORY_CACHE[cache_key]
        return None if cached is None else cached.copy()

    for adjust in ("qfq", ""):
        try:
            hist = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                timeout=10,
            )
            normalized = _normalize_stock_history(hist)
            if normalized is not None and not normalized.empty:
                _STOCK_HISTORY_CACHE[cache_key] = normalized.copy()
                return normalized
        except Exception as exc:
            logger.info(f"读取股票历史失败: {stock_code}, adjust={adjust}, error={exc}")

    tx_symbol = _stock_code_to_tx_symbol(stock_code)
    if tx_symbol:
        for adjust in ("qfq", ""):
            try:
                hist = ak.stock_zh_a_hist_tx(
                    symbol=tx_symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                    timeout=10,
                )
                normalized = _normalize_stock_history(hist)
                if normalized is not None and not normalized.empty:
                    _STOCK_HISTORY_CACHE[cache_key] = normalized.copy()
                    return normalized
            except Exception as exc:
                logger.info(f"读取腾讯股票历史失败: {tx_symbol}, adjust={adjust}, error={exc}")
    _STOCK_HISTORY_CACHE[cache_key] = None
    return None


def _stock_code_to_tx_symbol(stock_code: str) -> Optional[str]:
    code = str(stock_code or "").strip().zfill(6)
    if not code or len(code) != 6:
        return None
    if code.startswith(("60", "68", "90")):
        return f"sh{code}"
    if code.startswith(("00", "30", "20")):
        return f"sz{code}"
    if code.startswith(("43", "83", "87", "92")):
        return f"bj{code}"
    return None


def _normalize_stock_history(hist: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if hist is None or hist.empty:
        return None
    df = hist.copy()
    date_col = _find_column(df, ["日期", "date", "交易日期", "Date"])
    close_col = _find_column(df, ["收盘", "close", "收盘价", "Close"])
    if not date_col or not close_col:
        return None
    df["净值日期"] = pd.to_datetime(df[date_col], errors="coerce")
    df["收盘"] = pd.to_numeric(df[close_col], errors="coerce")
    df = df.dropna(subset=["净值日期", "收盘"])
    df = df[df["收盘"] > 0]
    return df[["净值日期", "收盘"]].sort_values("净值日期").drop_duplicates("净值日期")


def _find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower_map = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    for col in df.columns:
        col_text = str(col).lower()
        if any(candidate.lower() in col_text for candidate in candidates):
            return str(col)
    return None


def _normalize_price_series(series: pd.Series) -> pd.Series:
    first_valid = series.dropna()
    if first_valid.empty or float(first_valid.iloc[0]) <= 0:
        return series * np.nan
    return series / float(first_valid.iloc[0])


def _calculate_basket_features(basket_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if basket_df is None or basket_df.empty or "factor_nav" not in basket_df.columns:
        return None
    df = basket_df.copy().sort_values("净值日期")
    nav = pd.to_numeric(df["factor_nav"], errors="coerce")
    low30 = nav.rolling(30, min_periods=5).min()
    high30 = nav.rolling(30, min_periods=5).max()
    spread30 = high30 - low30
    ma20 = nav.rolling(20, min_periods=5).mean()
    daily_ret = nav.pct_change()

    features = pd.DataFrame({
        "净值日期": df["净值日期"],
        "factor_return_1d": nav.pct_change(1) * 100,
        "factor_return_5d": nav.pct_change(5) * 100,
        "factor_return_20d": nav.pct_change(20) * 100,
        "factor_position_30d": np.where(spread30 > 0, (nav - low30) / spread30 * 100, 50.0),
        "factor_above_ma20": np.where(nav >= ma20, 1.0, 0.0),
        "factor_volatility_20d": daily_ret.rolling(20, min_periods=5).std() * np.sqrt(252) * 100,
    })
    return features.replace([np.inf, -np.inf], np.nan)
