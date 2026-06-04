"""
市场环境因子模块
获取A股大盘、行业指数等市场环境数据，用于增强预测
"""
import logging
from typing import Dict, Any, Optional
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_market_context() -> Dict[str, Any]:
    """
    获取市场环境上下文
    包括：A股主要指数、市场情绪、资金流向
    """
    context = {
        "status": "ok",
        "indices": {},
        "market_sentiment": "neutral",
        "money_flow": "neutral",
    }

    try:
        # 获取主要指数实时数据
        indices_data = _get_major_indices()
        context["indices"] = indices_data

        # 判断市场情绪
        context["market_sentiment"] = _analyze_market_sentiment(indices_data)

        # 资金流向
        context["money_flow"] = _analyze_money_flow(indices_data)

    except Exception as e:
        logger.warning(f"获取市场环境失败: {e}")
        context["status"] = "partial"

    return context


def _get_major_indices() -> Dict[str, Any]:
    """获取主要指数数据"""
    indices = {}

    try:
        # 上证指数
        sh_index = ak.stock_zh_index_spot_em(symbol="上证指数")
        if not sh_index.empty:
            row = sh_index.iloc[0]
            indices["sh_index"] = {
                "code": "000001",
                "name": "上证指数",
                "latest": float(row.get("最新价", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
                "change_amount": float(row.get("涨跌额", 0)),
            }

        # 深证成指
        sz_index = ak.stock_zh_index_spot_em(symbol="深证成指")
        if not sz_index.empty:
            row = sz_index.iloc[0]
            indices["sz_index"] = {
                "code": "399001",
                "name": "深证成指",
                "latest": float(row.get("最新价", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
                "change_amount": float(row.get("涨跌额", 0)),
            }

        # 创业板指
        cy_index = ak.stock_zh_index_spot_em(symbol="创业板指")
        if not cy_index.empty:
            row = cy_index.iloc[0]
            indices["cy_index"] = {
                "code": "399006",
                "name": "创业板指",
                "latest": float(row.get("最新价", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
                "change_amount": float(row.get("涨跌额", 0)),
            }

        # 沪深300
        hs300 = ak.stock_zh_index_spot_em(symbol="沪深300")
        if not hs300.empty:
            row = hs300.iloc[0]
            indices["hs300"] = {
                "code": "000300",
                "name": "沪深300",
                "latest": float(row.get("最新价", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
                "change_amount": float(row.get("涨跌额", 0)),
            }

    except Exception as e:
        logger.warning(f"获取指数数据失败: {e}")

    return indices


def _analyze_market_sentiment(indices: Dict[str, Any]) -> str:
    """
    分析市场情绪
    返回: bullish(看涨) / neutral(中性) / bearish(看跌)
    """
    if not indices:
        return "neutral"

    # 计算主要指数平均涨跌幅
    changes = []
    for idx_data in indices.values():
        change_pct = idx_data.get("change_pct", 0)
        changes.append(change_pct)

    if not changes:
        return "neutral"

    avg_change = np.mean(changes)
    positive_count = sum(1 for c in changes if c > 0)
    total_count = len(changes)

    # 判断逻辑
    if avg_change > 1.5 and positive_count >= total_count * 0.75:
        return "very_bullish"
    elif avg_change > 0.5 and positive_count >= total_count * 0.6:
        return "bullish"
    elif avg_change < -1.5 and positive_count <= total_count * 0.25:
        return "very_bearish"
    elif avg_change < -0.5 and positive_count <= total_count * 0.4:
        return "bearish"
    else:
        return "neutral"


def _analyze_money_flow(indices: Dict[str, Any]) -> str:
    """
    分析资金流向
    返回: inflow(流入) / neutral(中性) / outflow(流出)
    """
    # 简化版：基于指数涨跌判断
    # 实际应该用北向资金、两融数据等
    if not indices:
        return "neutral"

    changes = [idx.get("change_pct", 0) for idx in indices.values()]
    avg_change = np.mean(changes) if changes else 0

    if avg_change > 0.8:
        return "strong_inflow"
    elif avg_change > 0.3:
        return "inflow"
    elif avg_change < -0.8:
        return "strong_outflow"
    elif avg_change < -0.3:
        return "outflow"
    else:
        return "neutral"


def get_sector_performance(fund_type: str = "") -> Dict[str, Any]:
    """
    获取行业板块表现
    根据基金类型返回相关行业指数
    """
    sectors = {}

    try:
        # 根据基金类型判断关注的行业
        if "消费" in fund_type or "白酒" in fund_type:
            sectors["consumer"] = _get_sector_index("消费")
        elif "医药" in fund_type or "医疗" in fund_type:
            sectors["healthcare"] = _get_sector_index("医药")
        elif "科技" in fund_type or "TMT" in fund_type:
            sectors["technology"] = _get_sector_index("科技")
        elif "金融" in fund_type or "银行" in fund_type:
            sectors["finance"] = _get_sector_index("金融")
        else:
            # 默认获取主要行业
            sectors["consumer"] = _get_sector_index("消费")
            sectors["technology"] = _get_sector_index("科技")

    except Exception as e:
        logger.warning(f"获取行业数据失败: {e}")

    return sectors


def _get_sector_index(sector_name: str) -> Dict[str, Any]:
    """获取单个行业指数数据"""
    try:
        # 这里简化处理，实际应该用行业指数代码
        # 可以用申万行业指数等
        return {
            "name": sector_name,
            "change_pct": 0.0,
            "status": "unavailable"
        }
    except Exception as e:
        logger.warning(f"获取{sector_name}行业数据失败: {e}")
        return {"name": sector_name, "status": "error"}


def format_market_context_for_llm(context: Dict[str, Any]) -> str:
    """
    将市场环境格式化为LLM可读的文本
    """
    if context.get("status") != "ok":
        return "市场环境数据不可用"

    lines = ["## 市场环境"]

    # 主要指数
    indices = context.get("indices", {})
    if indices:
        lines.append("主要指数:")
        for idx_key, idx_data in indices.items():
            name = idx_data.get("name", "")
            change_pct = idx_data.get("change_pct", 0)
            lines.append(f"  - {name}: {change_pct:+.2f}%")

    # 市场情绪
    sentiment = context.get("market_sentiment", "neutral")
    sentiment_map = {
        "very_bullish": "非常乐观",
        "bullish": "偏乐观",
        "neutral": "中性",
        "bearish": "偏悲观",
        "very_bearish": "非常悲观",
    }
    lines.append(f"市场情绪: {sentiment_map.get(sentiment, '中性')}")

    # 资金流向
    money_flow = context.get("money_flow", "neutral")
    flow_map = {
        "strong_inflow": "大幅流入",
        "inflow": "净流入",
        "neutral": "平衡",
        "outflow": "净流出",
        "strong_outflow": "大幅流出",
    }
    lines.append(f"资金流向: {flow_map.get(money_flow, '平衡')}")

    return "\n".join(lines)
