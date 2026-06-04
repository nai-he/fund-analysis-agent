"""
短线预测专用引擎
专注1天、3天、7天的预测，使用LLM + 短线技术指标
"""
import os
import json
import logging
import requests
from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def short_term_prediction(
    nav_df: pd.DataFrame,
    fund_code: str = "",
    fund_name: str = "",
    fund_type: str = "",
) -> Dict[str, Any]:
    """
    短线预测引擎：专注1天、3天、7天
    核心策略：
    1. 超买超卖反转
    2. 短期动量延续
    3. 支撑阻力位
    4. 市场环境因子
    5. LLM综合判断
    """
    if nav_df is None or len(nav_df) < 30:
        return {"status": "unavailable", "error": "数据不足", "periods": {}}

    # 用户指定基金走专属长历史训练层，不再让LLM短线判断覆盖实证筛选结果。
    try:
        from prediction_engine import generate_up_probability_prediction, is_specific_trained_fund

        if is_specific_trained_fund(fund_code):
            external_features = None
            external_factor_meta = None
            try:
                from specific_fund_factors import build_specific_external_features

                external_features, external_factor_meta = build_specific_external_features(
                    fund_code,
                    nav_df,
                    fund_name=fund_name,
                )
            except Exception as factor_error:
                logger.warning(f"专属基金外部因子构建失败，继续使用净值训练: {fund_code}, error={factor_error}")

            return generate_up_probability_prediction(
                nav_df,
                horizons=[1, 3, 7, 30],
                min_samples=20,
                fund_code=fund_code,
                fund_name=fund_name,
                external_features=external_features,
                external_factor_meta=external_factor_meta,
            )
    except Exception as e:
        logger.warning(f"专属基金训练预测失败，回退短线预测: {fund_code}, error={e}")

    # 准备数据
    navs = nav_df["单位净值"].values
    latest_nav = float(navs[-1])

    # 计算短线指标
    indicators = _calculate_short_term_indicators(navs)

    # 获取市场环境
    from market_context import get_market_context, format_market_context_for_llm
    market_ctx = get_market_context()
    market_text = format_market_context_for_llm(market_ctx)

    # 构建短线专用prompt（包含市场环境）
    prompt = _build_short_term_prompt(
        fund_code, fund_name, fund_type,
        latest_nav, navs, indicators, market_text
    )

    # 调用LLM
    llm_result = _call_llm_api(prompt)

    if llm_result is None:
        # LLM失败，使用规则fallback
        return _rule_based_short_term(navs, indicators)

    # 转换LLM结果为标准格式
    llm_periods = {}
    for period_key in ["1d", "3d", "7d", "30d"]:
        if period_key not in llm_result:
            continue

        period_data = llm_result[period_key]
        llm_periods[period_key] = {
            "period_days": int(period_key[:-1]),
            "predicted_direction": period_data.get("direction", "uncertain"),
            "direction_label": _direction_label(period_data.get("direction")),
            "up_probability": float(period_data.get("probability", 50)),
            "down_or_flat_probability": 100 - float(period_data.get("probability", 50)),
            "confidence": period_data.get("confidence", "低"),
            "main_reasons": [period_data.get("reason", "")],
            "entry_price": period_data.get("entry_price"),
            "stop_loss": period_data.get("stop_loss"),
            "take_profit": period_data.get("take_profit"),
            "method": "llm_short_term_prediction",
        }

    llm_prediction = {
        "status": "ok",
        "periods": llm_periods,
    }

    # 获取规则模型预测（用于集成）
    rule_prediction = _rule_based_short_term(navs, indicators)

    # 集成学习：融合LLM + 规则 + 超买超卖信号
    from ensemble_prediction import ensemble_prediction
    ensemble_result = ensemble_prediction(llm_prediction, rule_prediction, indicators)

    # 使用集成结果
    periods = ensemble_result.get("periods", {})

    return {
        "status": "ok",
        "model_basis": "ensemble_short_term_prediction",
        "quality": "high",
        "periods": periods,
        "trading_signals": llm_result.get("trading_signals", {}),
        "key_levels": llm_result.get("key_levels", {}),
        "market_context": market_ctx,
        "ensemble_info": {
            "llm_weight": 0.60,
            "rule_weight": 0.20,
            "signal_weight": 0.20,
        },
        "disclaimer": "短线预测风险极高，仅供参考。",
    }


def _calculate_short_term_indicators(navs: np.ndarray) -> Dict[str, Any]:
    """计算短线专用指标"""
    latest = float(navs[-1])

    # 收益率
    ret_1d = ((navs[-1] / navs[-2]) - 1) * 100 if len(navs) >= 2 else 0
    ret_3d = ((navs[-1] / navs[-4]) - 1) * 100 if len(navs) >= 4 else 0
    ret_5d = ((navs[-1] / navs[-6]) - 1) * 100 if len(navs) >= 6 else 0
    ret_10d = ((navs[-1] / navs[-11]) - 1) * 100 if len(navs) >= 11 else 0

    # 均线
    ma3 = float(np.mean(navs[-3:])) if len(navs) >= 3 else latest
    ma5 = float(np.mean(navs[-5:])) if len(navs) >= 5 else latest
    ma10 = float(np.mean(navs[-10:])) if len(navs) >= 10 else latest
    ma20 = float(np.mean(navs[-20:])) if len(navs) >= 20 else latest

    # RSI
    rsi_6 = _calculate_rsi(navs, 6)
    rsi_14 = _calculate_rsi(navs, 14)

    # 布林带
    bb = _calculate_bollinger(navs, 20, 2)

    # 支撑阻力位
    support_resistance = _find_support_resistance(navs)

    # 连续涨跌天数
    consecutive = _count_consecutive_days(navs)

    # 短期波动率
    if len(navs) >= 11:
        returns = np.diff(navs[-11:]) / navs[-11:-1]
        volatility_10d = float(np.std(returns) * 100)
    else:
        volatility_10d = 0.0

    # 动量加速度
    momentum_accel = _calculate_momentum_acceleration(navs)

    return {
        "latest_nav": latest,
        "ret_1d": float(ret_1d),
        "ret_3d": float(ret_3d),
        "ret_5d": float(ret_5d),
        "ret_10d": float(ret_10d),
        "ma3": ma3,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "rsi_6": rsi_6,
        "rsi_14": rsi_14,
        "bb_upper": bb["upper"],
        "bb_middle": bb["middle"],
        "bb_lower": bb["lower"],
        "bb_position": bb["position_pct"],
        "support": support_resistance["support"],
        "resistance": support_resistance["resistance"],
        "consecutive_days": consecutive["days"],
        "consecutive_direction": consecutive["direction"],
        "volatility_10d": volatility_10d,
        "momentum_accel": momentum_accel,
    }


def _build_short_term_prompt(
    fund_code: str,
    fund_name: str,
    fund_type: str,
    latest_nav: float,
    navs: np.ndarray,
    indicators: Dict[str, Any],
    market_text: str = ""
) -> str:
    """构建短线预测专用prompt（包含市场环境）"""

    # 判断当前状态
    status_desc = []

    # RSI状态
    rsi6 = indicators["rsi_6"]
    rsi14 = indicators["rsi_14"]
    if rsi6 < 25 or rsi14 < 30:
        status_desc.append(f"RSI严重超卖(RSI6={rsi6:.1f}, RSI14={rsi14:.1f})，短线反弹概率大")
    elif rsi6 > 75 or rsi14 > 70:
        status_desc.append(f"RSI严重超买(RSI6={rsi6:.1f}, RSI14={rsi14:.1f})，短线回调风险高")

    # 布林带位置
    bb_pos = indicators["bb_position"]
    if bb_pos < 10:
        status_desc.append(f"触及布林带下轨({bb_pos:.1f}%)，超卖反弹信号")
    elif bb_pos > 90:
        status_desc.append(f"触及布林带上轨({bb_pos:.1f}%)，超买回调信号")

    # 连续涨跌
    consec = indicators["consecutive_days"]
    consec_dir = indicators["consecutive_direction"]
    if consec >= 3:
        status_desc.append(f"连续{consec}天{consec_dir}，注意反转风险")

    # 均线位置
    ma_status = []
    if latest_nav > indicators["ma3"]:
        ma_status.append("站上3日线")
    if latest_nav > indicators["ma5"]:
        ma_status.append("站上5日线")
    if latest_nav > indicators["ma10"]:
        ma_status.append("站上10日线")

    if ma_status:
        status_desc.append("、".join(ma_status))

    prompt = f"""你是一个专业的短线交易员，专注基金的1-7天短线预测。

## 基金信息
- 代码: {fund_code}
- 名称: {fund_name}
- 类型: {fund_type}

{market_text}

## 当前技术状态
{chr(10).join(f"- {s}" for s in status_desc)}

## 详细指标
- 最新净值: {latest_nav:.4f}
- 近1日: {indicators['ret_1d']:+.2f}%
- 近3日: {indicators['ret_3d']:+.2f}%
- 近5日: {indicators['ret_5d']:+.2f}%
- 近10日: {indicators['ret_10d']:+.2f}%

均线系统:
- MA3: {indicators['ma3']:.4f} (当前{'上方' if latest_nav > indicators['ma3'] else '下方'})
- MA5: {indicators['ma5']:.4f} (当前{'上方' if latest_nav > indicators['ma5'] else '下方'})
- MA10: {indicators['ma10']:.4f} (当前{'上方' if latest_nav > indicators['ma10'] else '下方'})

技术指标:
- RSI(6): {indicators['rsi_6']:.1f}
- RSI(14): {indicators['rsi_14']:.1f}
- 布林带位置: {indicators['bb_position']:.1f}% (上轨{indicators['bb_upper']:.4f}, 下轨{indicators['bb_lower']:.4f})
- 支撑位: {indicators['support']:.4f}
- 阻力位: {indicators['resistance']:.4f}
- 10日波动率: {indicators['volatility_10d']:.2f}%
- 动量加速度: {indicators['momentum_accel']:+.2f}

## 最近10天净值
{[round(float(x), 4) for x in navs[-10:]]}

## 短线预测要求（重要！）
1. **市场环境优先**: 如果大盘大跌，基金很难独立上涨；大盘大涨，基金跟涨概率高
2. **超买超卖优先**: RSI<30或布林带下轨 → 看涨反弹；RSI>70或布林带上轨 → 看跌回调
3. **动量延续**: 连续上涨且未超买 → 继续看涨；连续下跌且未超卖 → 继续看跌
4. **支撑阻力**: 接近支撑位 → 反弹机会；接近阻力位 → 回调风险
5. **给出具体建议**: 包括入场价、止损价、止盈价
6. **概率要合理**: 不要轻易给出>75%或<25%的极端概率，除非有非常强的信号

请严格按JSON格式输出：
{{
  "1d": {{
    "direction": "up" 或 "down_or_flat",
    "confidence": "高" 或 "中" 或 "低",
    "probability": 0-100,
    "reason": "判断理由，必须提到市场环境影响",
    "entry_price": 建议入场价,
    "stop_loss": 止损价,
    "take_profit": 止盈价
  }},
  "3d": {{ 同上 }},
  "7d": {{ 同上 }},
  "30d": {{ 同上 }},
  "trading_signals": {{
    "action": "buy" 或 "sell" 或 "hold",
    "urgency": "high" 或 "medium" 或 "low",
    "reason": "操作理由"
  }},
  "key_levels": {{
    "strong_support": 强支撑位,
    "weak_support": 弱支撑位,
    "weak_resistance": 弱阻力位,
    "strong_resistance": 强阻力位
  }}
}}"""

    return prompt


def _rule_based_short_term(navs: np.ndarray, indicators: Dict[str, Any]) -> Dict[str, Any]:
    """规则fallback：LLM失败时使用"""
    periods = {}

    for period_key, period_days in [("1d", 1), ("3d", 3), ("7d", 7), ("30d", 30)]:
        # 简单规则：超买看跌，超卖看涨
        rsi = indicators["rsi_6"] if period_days <= 3 else indicators["rsi_14"]
        bb_pos = indicators["bb_position"]

        if rsi < 30 or bb_pos < 15:
            direction = "up"
            probability = 60
            confidence = "中"
            reason = "超卖反弹"
        elif rsi > 70 or bb_pos > 85:
            direction = "down_or_flat"
            probability = 40
            confidence = "中"
            reason = "超买回调"
        else:
            direction = "uncertain"
            probability = 50
            confidence = "低"
            reason = "震荡整理"

        periods[period_key] = {
            "period_days": period_days,
            "predicted_direction": direction,
            "direction_label": _direction_label(direction),
            "up_probability": probability,
            "down_or_flat_probability": 100 - probability,
            "confidence": confidence,
            "main_reasons": [reason],
            "method": "rule_based_fallback",
        }

    return {
        "status": "ok",
        "model_basis": "rule_based_short_term",
        "quality": "low",
        "periods": periods,
    }


def _calculate_rsi(navs: np.ndarray, period: int) -> float:
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
    return float(100 - (100 / (1 + rs)))


def _calculate_bollinger(navs: np.ndarray, period: int, std_dev: float) -> Dict[str, float]:
    if len(navs) < period:
        latest = float(navs[-1])
        return {"upper": latest, "middle": latest, "lower": latest, "position_pct": 50.0}

    middle = float(np.mean(navs[-period:]))
    std = float(np.std(navs[-period:]))
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    latest = float(navs[-1])

    if upper > lower:
        position_pct = ((latest - lower) / (upper - lower)) * 100
    else:
        position_pct = 50.0

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "position_pct": float(position_pct)
    }


def _find_support_resistance(navs: np.ndarray, lookback: int = 30) -> Dict[str, float]:
    recent = navs[-lookback:] if len(navs) >= lookback else navs
    support = float(np.min(recent))
    resistance = float(np.max(recent))
    return {"support": support, "resistance": resistance}


def _count_consecutive_days(navs: np.ndarray) -> Dict[str, Any]:
    if len(navs) < 2:
        return {"days": 0, "direction": "flat"}

    count = 1
    direction = "up" if navs[-1] > navs[-2] else "down" if navs[-1] < navs[-2] else "flat"

    for i in range(len(navs) - 2, 0, -1):
        if direction == "up" and navs[i] > navs[i-1]:
            count += 1
        elif direction == "down" and navs[i] < navs[i-1]:
            count += 1
        else:
            break

    return {"days": count, "direction": direction}


def _calculate_momentum_acceleration(navs: np.ndarray) -> float:
    if len(navs) < 6:
        return 0.0
    ret_recent = ((navs[-1] / navs[-4]) - 1) * 100
    ret_prev = ((navs[-4] / navs[-7]) - 1) * 100
    return float(ret_recent - ret_prev)


def _call_llm_api(prompt: str) -> Optional[Dict[str, Any]]:
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
            "max_tokens": 1500,
            "temperature": 0.2,  # 降低温度，更确定性
            "messages": [{"role": "user", "content": prompt}]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=90)

        if response.status_code != 200:
            logger.error(f"LLM API error: {response.status_code}")
            return None

        result = response.json()
        content = result["content"][0]["text"].strip()

        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
            if content.endswith("```"):
                content = content[:-3]

        return json.loads(content)
    except Exception as e:
        logger.error(f"LLM prediction failed: {e}")
        return None


def _direction_label(direction: str) -> str:
    return {"up": "偏上涨", "down_or_flat": "偏不涨", "uncertain": "不确定"}.get(direction, "不确定")
