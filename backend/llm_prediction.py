"""
LLM增强预测引擎
核心思路：让LLM看历史数据直接预测，而不是依赖规则评分
"""
import os
import json
import logging
import requests
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def llm_enhanced_prediction(
    nav_df: pd.DataFrame,
    fund_code: str = "",
    fund_name: str = "",
    fund_type: str = "",
) -> Dict[str, Any]:
    """
    使用LLM直接预测未来走势
    输入：历史净值数据
    输出：7天和30天的预测结果
    """
    if nav_df is None or len(nav_df) < 30:
        return {
            "status": "unavailable",
            "error": "数据不足",
            "periods": {}
        }

    # 准备数据摘要
    recent_60 = nav_df.tail(60)
    navs = recent_60["单位净值"].values

    latest_nav = float(navs[-1])
    ret_1d = ((navs[-1] / navs[-2]) - 1) * 100 if len(navs) >= 2 else 0
    ret_7d = ((navs[-1] / navs[-5]) - 1) * 100 if len(navs) >= 5 else 0
    ret_30d = ((navs[-1] / navs[-20]) - 1) * 100 if len(navs) >= 20 else 0
    ret_60d = ((navs[-1] / navs[0]) - 1) * 100 if len(navs) >= 60 else 0

    # 计算技术指标
    ma5 = float(np.mean(navs[-5:])) if len(navs) >= 5 else latest_nav
    ma20 = float(np.mean(navs[-20:])) if len(navs) >= 20 else latest_nav
    max_60d = float(np.max(navs))
    min_60d = float(np.min(navs))
    position_pct = ((latest_nav - min_60d) / (max_60d - min_60d) * 100) if max_60d > min_60d else 50

    # RSI
    rsi = _calculate_rsi(navs, 14)

    # 波动率
    returns = np.diff(navs) / navs[:-1]
    volatility = float(np.std(returns[-20:]) * np.sqrt(252) * 100) if len(returns) >= 20 else 0

    # 构建prompt
    prompt = f"""你是一个专业的基金预测分析师。请根据以下数据，预测该基金未来7天和30天的涨跌方向。

## 基金信息
- 代码: {fund_code}
- 名称: {fund_name}
- 类型: {fund_type}

## 当前状态
- 最新净值: {latest_nav:.4f}
- 5日均线: {ma5:.4f} (净值{'高于' if latest_nav > ma5 else '低于'}均线)
- 20日均线: {ma20:.4f} (净值{'高于' if latest_nav > ma20 else '低于'}均线)
- 60日区间位置: {position_pct:.1f}% (0%=最低点, 100%=最高点)
- RSI(14): {rsi:.1f} ({'超买' if rsi > 70 else '超卖' if rsi < 30 else '中性'})
- 30日波动率: {volatility:.1f}%

## 近期表现
- 近1日: {ret_1d:+.2f}%
- 近7日: {ret_7d:+.2f}%
- 近30日: {ret_30d:+.2f}%
- 近60日: {ret_60d:+.2f}%

## 最近20天净值走势（从旧到新）
{[round(float(x), 4) for x in navs[-20:]]}

## 预测要求
1. 综合考虑趋势、位置、RSI、波动率等因素
2. 如果已经大涨且高位，应预测回调风险
3. 如果已经大跌且低位，应预测反弹机会
4. 给出明确的方向判断和置信度

请严格按以下JSON格式输出：
{{
  "7d": {{
    "direction": "up" 或 "down_or_flat",
    "confidence": "高" 或 "中" 或 "低",
    "probability": 0-100的数字,
    "reason": "判断理由，80字以内"
  }},
  "30d": {{
    "direction": "up" 或 "down_or_flat",
    "confidence": "高" 或 "中" 或 "低",
    "probability": 0-100的数字,
    "reason": "判断理由，80字以内"
  }},
  "key_factors": ["影响判断的3-5个关键因素"],
  "risk_warning": "主要风险提示，50字以内"
}}"""

    # 调用LLM
    llm_result = _call_llm_api(prompt)

    if llm_result is None:
        return {
            "status": "error",
            "error": "LLM调用失败",
            "periods": {}
        }

    # 转换为标准格式
    periods = {}

    for period_key in ["7d", "30d"]:
        period_data = llm_result.get(period_key, {})
        periods[period_key] = {
            "period_days": int(period_key[:-1]),
            "predicted_direction": period_data.get("direction", "uncertain"),
            "direction_label": _direction_label(period_data.get("direction", "uncertain")),
            "up_probability": float(period_data.get("probability", 50)),
            "down_or_flat_probability": 100 - float(period_data.get("probability", 50)),
            "confidence": period_data.get("confidence", "低"),
            "main_reasons": [period_data.get("reason", "")],
            "method": "llm_direct_prediction",
        }

    return {
        "status": "ok",
        "model_basis": "llm_enhanced_prediction",
        "quality": "high" if llm_result.get("7d", {}).get("confidence") == "高" else "medium",
        "periods": periods,
        "key_factors": llm_result.get("key_factors", []),
        "risk_warning": llm_result.get("risk_warning", ""),
        "disclaimer": "LLM预测仅供参考，不构成投资建议。",
    }


def _call_llm_api(prompt: str) -> Optional[Dict[str, Any]]:
    """调用LLM API"""
    try:
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")

        url = f"{base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 800,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code != 200:
            logger.error(f"LLM API error: {response.status_code}")
            return None

        result = response.json()
        content = result["content"][0]["text"].strip()

        # 提取JSON
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
            if content.endswith("```"):
                content = content[:-3]

        return json.loads(content)
    except Exception as e:
        logger.error(f"LLM prediction failed: {e}")
        return None


def _calculate_rsi(navs: np.ndarray, period: int = 14) -> float:
    """计算RSI"""
    if len(navs) < period + 1:
        return 50.0

    deltas = np.diff(navs)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi)


def _direction_label(direction: str) -> str:
    labels = {
        "up": "偏上涨",
        "down_or_flat": "偏不涨",
        "uncertain": "不确定",
    }
    return labels.get(direction, "不确定")
