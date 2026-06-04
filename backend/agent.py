"""
LLM Agent 分析模块
将结构化指标数据交给 LLM 生成中文分析总结
优先读取 LLM_* 配置，fallback 到 DEEPSEEK_*
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个基金数据分析助手，服务于个人投资者的研究和风险辅助决策。你会收到一份包含基金基本信息、基金画像、技术指标、风险评分、宏观数据和可选持仓信息的结构化数据。

## 你的定位（严格遵守）
1. 你提供的是**个人研究参考和风险辅助**，绝对不构成投资建议
2. **绝对不能**承诺未来涨跌，不能使用"必涨""必跌""稳赚""肯定会""马上梭哈""抄底""all in""满仓""翻倍"等话术
3. **绝对不能**给出具体的买卖指令（如"立即买入""赶紧卖出""现在加仓""马上清仓"）
4. 你的判断依据必须来自于给到的结构化数据，不能凭空编造
5. 如果数据不足，**必须**降低置信度并在结论中说明
6. 输出**必须是中文**
7. 结论必须使用以下五种之一：偏积极、中性、偏谨慎、风险较高、数据不足
8. 不能编造宏观新闻、不能编造基金经理观点、不能编造市场传闻
9. 如果回测验证显示 probability_quality 为 "low"，你的 confidence 不能超过 "中"；如果 is_calibrated 为 false，confidence 不能为 "高"
10. 回测准确率（directional_accuracy）低于 50% 的周期，对应周期的判断应更保守

## 判断逻辑参考
- 短期（7天）：看近7天收益率、连续涨跌、7天最大回撤、日波动
- 中期（30天）：看近30天收益率、均线趋势、30天最大回撤、波动率、夏普比率
- 中期偏长（60-90天）：看60/90天收益、回撤、波动率、Calmar比率、均线位置
- 风险判断：综合风险引擎输出的各维度评分，解读哪些维度风险偏高
- 位置判断：当前净值在历史区间的位置，结合趋势判断追高或左侧风险
- 个人持仓：如果有持仓数据，评估盈亏情况和风险，给出定投建议

## 输出格式（严格 JSON）
{
  "conclusion": "偏积极 / 中性 / 偏谨慎 / 风险较高 / 数据不足",
  "summary_7d": "近7天视角的分析，80字以内",
  "summary_30d": "近30天视角的分析，80字以内",
  "summary_90d": "近90天视角的分析，80字以内，数据不足时说明",
  "risk_explanation": "对风险评分的解读，说明哪些因素推高或压低了风险，100字以内",
  "position_advice": "如果用户提供了持仓：分析当前持仓盈亏，结合风险偏好给出风险提示。如果没有持仓：写'未提供持仓信息，仅分析基金本身'",
  "main_risks": ["当前最值得关注的3-5个风险"],
  "watch_points": ["值得持续观察的3-5个关键信号"],
  "buy_conditions": ["适合关注的买入/加仓条件，2-4条，用'可关注'开头"],
  "reduce_conditions": ["适合警惕的减仓/止损条件，2-4条，用'警惕'或'关注'开头"],
  "dca_suggestion": "可关注 / 可暂停观察 / 可降低金额 / 数据不足 — 仅限于这四种",
  "confidence": "高 / 中 / 低",
  "data_basis": "说明判断基于哪些数据指标",
  "disclaimer": "本分析仅用于个人研究参考，不构成任何投资建议。基金投资有风险，过往业绩不预示未来表现。请在投资前充分了解产品风险特征，并根据自身风险承受能力做出决策。",
  "forecast_summary_1d": "基于程序计算的概率，解释未来1天涨跌倾向，30-60字。必须说明'不是确定预测'",
  "forecast_summary_3d": "基于程序计算的概率，解释未来3天方向倾向，30-60字。必须说明'不是确定预测'",
  "forecast_summary_7d": "基于程序计算的概率，解释未来7天方向倾向，30-60字。必须说明'不是确定预测'",
  "forecast_summary_30d": "基于程序计算的概率，解释未来30天方向倾向，30-60字。必须说明'不是确定预测'",
  "forecast_risks": ["情景判断中值得注意的1-3个不确定性因素"]
}

## 各字段注意事项
- conclusion：基于综合判断，不要随意给出"风险较高"除非指标确实支持
- position_advice：不能说你必须买/卖，只能说风险提示和观察建议
- dca_suggestion：只能说"可关注 / 可暂停观察 / 可降低金额 / 数据不足"，不能说"继续定投""停止定投"
- buy_conditions / reduce_conditions：条件应该基于技术指标，不是随意编造的价格点位
- confidence：数据源越多越完整，置信度越高；只有7天数据不能给"高"置信度
- main_risks：要结合数据说话，不能泛泛说"市场风险""政策风险"""

USER_PROMPT_TEMPLATE = """请分析以下基金的结构化数据，给出辅助判断：

## 基金基本信息
- 基金代码：{fund_code}
- 基金名称：{fund_name}
- 基金类型：{fund_type}
- 基金公司：{fund_company}

## 基金画像
{fund_profile_text}

## 技术指标
- 最新净值：{latest_nav}
- 当日估算：{current_estimate_text}
### 自然日口径（阶段涨跌，从最新净值日期往前推自然日）
- 近7个自然日涨跌幅：{return_7d}%（计算区间：{period_7d_range}）
- 近30个自然日涨跌幅：{return_30d}%（计算区间：{period_30d_range}）
- 近60个自然日涨跌幅：{return_60d}%
- 近90个自然日涨跌幅：{return_90d}%（计算区间：{period_90d_range}）
- 近7个自然日最大回撤：{max_drawdown_7d}%
- 近30个自然日最大回撤：{max_drawdown_30d}%
- 近60个自然日最大回撤：{max_drawdown_60d}%
- 近90个自然日最大回撤：{max_drawdown_90d}%
### 交易日口径（最近N条净值记录）
- 近1个交易日涨跌：{return_1trading}%
- 近5个交易日涨跌：{return_5trading}%
- 近10个交易日涨跌：{return_10trading}%
- 近20个交易日涨跌：{return_20trading}%
- 近60个交易日涨跌：{return_60trading}%
### 波动与趋势
- 近30个自然日年化波动率：{volatility_30d}%
- 近60个自然日年化波动率：{volatility_60d}%
- 近90个自然日年化波动率：{volatility_90d}%
- 近30个自然日下行波动率：{downside_volatility_30d}%
- 近60个自然日下行波动率：{downside_volatility_60d}%
- 5日均线：{ma_5}
- 10日均线：{ma_10}
- 20日均线：{ma_20}
- 60日均线：{ma_60}
- 均线趋势：{trend}
- 当前净值在7日区间位置：{position_7d}%（0=最低点，100=最高点）
- 当前净值在30日区间位置：{position_30d}%（0=最低点，100=最高点）
- 当前净值在60日区间位置：{position_60d}%
- 当前净值在90日区间位置：{position_90d}%
- 近30日反弹强度：{rebound_30d}%
- 近30日回落幅度：{pullback_30d}%
- 5日动能加速度：{momentum_acceleration_5d}%
- 20日EWMA年化波动率：{ewma_volatility_20d}%
- 30日波动率分位：{volatility_percentile_30d}%（状态：{volatility_regime_30d}）
- 60日Calmar比率：{calmar_60d}
- 90日Calmar比率：{calmar_90d}
- 连续涨跌：{consecutive}
- 近30天夏普比率：{sharpe_30d}
- 近60天夏普比率：{sharpe_60d}
- 近30天上涨胜率：{win_rate_30d}%
- 近60天上涨胜率：{win_rate_60d}%
- 近20天日均涨跌：{daily_mean}%
- 近20天最大单日涨幅：{daily_max}%
- 近20天最大单日跌幅：{daily_min}%
- 净值延迟提示：{nav_delay_note}

## 风险评分
{risk_text}

## 未来走势情景判断（程序规则计算，非确定预测）
{forecast_text}

## 回测验证（历史规则准确率参考，不代表未来表现）
{backtest_validation_text}

## 宏观因素
{macro_summary}
宏观风险因素：{macro_risks}

## 个人持仓信息
{position_text}

请严格按 JSON 格式输出分析结果。"""


def analyze_with_llm(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将结构化数据交给 LLM 进行中文分析总结
    """
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "3000"))

    if not api_key:
        logger.warning("未配置 LLM_API_KEY 或 DEEPSEEK_API_KEY，返回规则化分析")
        return _rule_based_analysis(analysis_data)

    fund = analysis_data.get("fund", {})
    metrics = analysis_data.get("metrics", {})
    macro = analysis_data.get("macro", {})
    fund_profile = analysis_data.get("fund_profile", {})
    risk = analysis_data.get("risk", {})
    forecast = analysis_data.get("forecast", {})
    position = analysis_data.get("position")

    if metrics.get("error"):
        return {
            "conclusion": "数据不足",
            "summary_7d": f"无法分析：{metrics.get('error')}",
            "summary_30d": "数据不足以进行中期分析",
            "summary_90d": "数据不足以进行长期分析",
            "risk_explanation": "数据不足，无法评估风险",
            "position_advice": "未提供持仓信息，仅分析基金本身",
            "main_risks": ["净值数据不足"],
            "watch_points": ["获取到足够数据后再进行分析"],
            "buy_conditions": [],
            "reduce_conditions": [],
            "dca_suggestion": "数据不足",
            "confidence": "低",
            "data_basis": f"仅获取到 {metrics.get('data_days', 0)} 条净值数据",
            "disclaimer": "本分析仅用于个人研究参考，不构成任何投资建议。",
            "forecast_summary_1d": "数据不足，无法生成1日涨跌情景",
            "forecast_summary_3d": "数据不足，无法生成3日走势情景",
            "forecast_summary_7d": "数据不足，无法生成走势情景",
            "forecast_summary_30d": "数据不足，无法生成走势情景",
            "forecast_risks": ["净值数据不足"],
        }

    user_prompt = _build_user_prompt(fund, metrics, macro, fund_profile, risk, forecast, position)

    # 尝试调用 LLM，带 response_format 回退
    result = _call_llm(api_key, base_url, model, user_prompt, temperature, max_tokens)

    if result is None:
        logger.warning("LLM 调用失败，回退到规则化分析")
        result = _rule_based_analysis(analysis_data)
        result["llm_error"] = "LLM 调用失败"
        result["note"] = "LLM 调用失败，以下为规则化分析结果"
        return result

    # 确保必要字段
    _ensure_fields(result, position)

    # 基于回测质量强制降级 LLM 置信度
    validation = forecast.get("validation") if forecast else None
    if validation:
        quality = validation.get("probability_quality", "low")
        calibrated = validation.get("is_calibrated", False)
        llm_conf = result.get("confidence", "中")
        if quality == "low" and llm_conf == "高":
            result["confidence"] = "中"
        if not calibrated and llm_conf == "高":
            result["confidence"] = "中"

    return result


def _build_user_prompt(fund, metrics, macro, fund_profile, risk, forecast, position) -> str:
    """构建用户提示词"""

    # 基金画像
    profile_lines = []
    if fund_profile:
        profile_fields = [
            ("fund_type", "基金类型"),
            ("fund_company", "基金公司"),
            ("fund_manager", "基金经理"),
            ("inception_date", "成立日期"),
            ("fund_size", "基金规模"),
            ("tracking_index", "跟踪指数"),
            ("purchase_status", "申购状态"),
            ("redeem_status", "赎回状态"),
            ("management_fee", "管理费率"),
            ("custody_fee", "托管费率"),
            ("risk_level", "风险等级"),
            ("return_1y", "近一年收益"),
            ("peer_ranking", "同类排名"),
        ]
        for key, label in profile_fields:
            val = fund_profile.get(key, "unavailable")
            if val == "unavailable":
                profile_lines.append(f"- {label}：不可用")
            else:
                profile_lines.append(f"- {label}：{val}")
        profile_lines.append(f"- 数据质量：{fund_profile.get('data_quality', 'unknown')}")
    fund_profile_text = "\n".join(profile_lines) if profile_lines else "暂无基金画像数据"

    # 风险评分
    risk_text = "暂无风险评分"
    if risk:
        risk_lines = [
            f"- 综合风险评分：{risk.get('risk_score', 'N/A')} / 100",
            f"- 风险等级：{risk.get('risk_level', 'N/A')}",
            f"- 趋势评分：{risk.get('trend_score', 'N/A')}",
            f"- 回撤评分：{risk.get('drawdown_score', 'N/A')}",
            f"- 波动率评分：{risk.get('volatility_score', 'N/A')}",
            f"- 位置评分：{risk.get('position_score', 'N/A')}",
            f"- 宏观评分：{risk.get('macro_score', 'N/A')}",
        ]
        if risk.get("position_personal_score") is not None:
            risk_lines.append(f"- 个人持仓评分：{risk['position_personal_score']}")
        risk_text = "\n".join(risk_lines)

    # 未来走势情景
    forecast_text = "暂无走势情景判断"
    if forecast:
        f1 = forecast.get("forecast_1d", {})
        f3 = forecast.get("forecast_3d", {})
        f7 = forecast.get("forecast_7d", {})
        f30 = forecast.get("forecast_30d", {})
        def _range_text(fp):
            rng = fp.get("expected_return_range", {}) or {}
            if rng.get("low") is None or rng.get("high") is None:
                return "N/A"
            return f"{rng.get('low')}% ~ {rng.get('high')}%"
        flines = [
            "--- 未来1天 ---",
            f"- 涨跌判断：{f1.get('rise_fall', 'N/A')}",
            f"- 方向倾向：{f1.get('direction', 'N/A')}",
            f"- 上行概率：{f1.get('up_probability', 'N/A')}%",
            f"- 震荡概率：{f1.get('sideways_probability', 'N/A')}%",
            f"- 下行概率：{f1.get('down_probability', 'N/A')}%",
            f"- 概率涨跌幅区间：{_range_text(f1)}",
            f"- 置信度：{f1.get('confidence', 'N/A')}",
            f"- 理由：{'；'.join(f1.get('reasons', []))}",
            "--- 未来3天 ---",
            f"- 涨跌判断：{f3.get('rise_fall', 'N/A')}",
            f"- 方向倾向：{f3.get('direction', 'N/A')}",
            f"- 上行概率：{f3.get('up_probability', 'N/A')}%",
            f"- 震荡概率：{f3.get('sideways_probability', 'N/A')}%",
            f"- 下行概率：{f3.get('down_probability', 'N/A')}%",
            f"- 概率涨跌幅区间：{_range_text(f3)}",
            f"- 置信度：{f3.get('confidence', 'N/A')}",
            f"- 理由：{'；'.join(f3.get('reasons', []))}",
            "--- 未来7天 ---",
            f"- 涨跌判断：{f7.get('rise_fall', 'N/A')}",
            f"- 方向倾向：{f7.get('direction', 'N/A')}",
            f"- 上行概率：{f7.get('up_probability', 'N/A')}%",
            f"- 震荡概率：{f7.get('sideways_probability', 'N/A')}%",
            f"- 下行概率：{f7.get('down_probability', 'N/A')}%",
            f"- 概率涨跌幅区间：{_range_text(f7)}",
            f"- 置信度：{f7.get('confidence', 'N/A')}",
            f"- 理由：{'；'.join(f7.get('reasons', []))}",
            f"- 上行情景：{'；'.join(f7.get('up_triggers', []))}",
            f"- 下行情景：{'；'.join(f7.get('down_triggers', []))}",
            "--- 未来30天 ---",
            f"- 涨跌判断：{f30.get('rise_fall', 'N/A')}",
            f"- 方向倾向：{f30.get('direction', 'N/A')}",
            f"- 上行概率：{f30.get('up_probability', 'N/A')}%",
            f"- 震荡概率：{f30.get('sideways_probability', 'N/A')}%",
            f"- 下行概率：{f30.get('down_probability', 'N/A')}%",
            f"- 概率涨跌幅区间：{_range_text(f30)}",
            f"- 置信度：{f30.get('confidence', 'N/A')}",
            f"- 理由：{'；'.join(f30.get('reasons', []))}",
            f"- 上行情景：{'；'.join(f30.get('up_triggers', []))}",
            f"- 下行情景：{'；'.join(f30.get('down_triggers', []))}",
        ]
        forecast_text = "\n".join(flines)

    # 回测验证信息
    validation = forecast.get("validation") if forecast else None
    if validation:
        vlines = [
            f"- 回测样本量：{validation.get('sample_size', 'N/A')}",
            f"- 概率质量评级：{validation.get('probability_quality', 'low')}",
            f"- 是否已校准：{'是' if validation.get('is_calibrated') else '否'}",
        ]
        for pk, pv in validation.get("periods", {}).items():
            acc = pv.get("directional_accuracy")
            bs = pv.get("brier_score")
            bc = pv.get("baseline_comparison", {}) or {}
            edge = bc.get("rule_vs_best_baseline_edge")
            vlines.append(
                f"- {pk}周期：准确率{acc if acc is not None else 'N/A'}%，"
                f"Brier={bs if bs is not None else 'N/A'}，"
                f"vs基线优势={edge if edge is not None else 'N/A'}%"
            )
        backtest_validation_text = "\n".join(vlines)
    else:
        backtest_validation_text = "暂无回测验证数据"

    # 持仓信息
    position_text = "未提供个人持仓信息"
    if position and position.get("cost_nav") is not None:
        pos_lines = [
            f"- 持仓成本价：{position.get('cost_nav', 'N/A')}",
            f"- 持有金额：{position.get('holding_amount', '未填写')}",
            f"- 持有份额：{position.get('holding_units', '未填写')}",
            f"- 是否定投：{'是' if position.get('is_dca') else '否'}",
            f"- 每月定投金额：{position.get('monthly_dca_amount', '未填写')}",
            f"- 最大可承受亏损：{position.get('max_loss_percent', '未填写')}%",
            f"- 计划持有周期：{position.get('holding_horizon', '未填写')}",
            f"- 风险偏好：{position.get('risk_preference', '未填写')}",
        ]
        # 计算浮盈浮亏
        latest_nav = metrics.get("latest_nav")
        cost_nav = position.get("cost_nav")
        if latest_nav and cost_nav and float(cost_nav) > 0:
            profit_pct = (float(latest_nav) - float(cost_nav)) / float(cost_nav) * 100
            pos_lines.append(f"- 当前浮盈/浮亏：{profit_pct:.2f}%")
        position_text = "\n".join(pos_lines)

    # 连续涨跌
    consecutive_info = "无"
    cons = metrics.get("consecutive_days", {})
    if cons and cons.get("days", 0) > 0:
        consecutive_info = f"连续{cons.get('direction', '')}{cons.get('days', 0)}天"

    daily_stats = metrics.get("daily_stats", {})

    # 自然日期区间文本
    p7 = metrics.get("period_7d_calendar") or {}
    p30 = metrics.get("period_30d_calendar") or {}
    p90 = metrics.get("period_90d_calendar") or {}
    period_7d_range = f"{p7.get('start_date','?')} ~ {p7.get('end_date','?')}" if p7 else "N/A"
    period_30d_range = f"{p30.get('start_date','?')} ~ {p30.get('end_date','?')}" if p30 else "N/A"
    period_90d_range = f"{p90.get('start_date','?')} ~ {p90.get('end_date','?')}" if p90 else "N/A"

    nav_delay_note = metrics.get("note_nav_delay", "无") or "无"
    current_estimate = metrics.get("current_estimate") or {}
    if current_estimate.get("estimated_change_pct") is not None:
        current_estimate_text = (
            f"{current_estimate.get('estimated_change_pct')}% "
            f"（估算净值{current_estimate.get('estimated_nav', 'N/A')}，"
            f"估算时间{current_estimate.get('estimate_time', 'N/A')}，非正式净值）"
        )
    else:
        current_estimate_text = "暂无当日估算数据"

    return USER_PROMPT_TEMPLATE.format(
        fund_code=fund.get("code", ""),
        fund_name=fund.get("name", ""),
        fund_type=fund.get("type", ""),
        fund_company=fund.get("company", ""),
        fund_profile_text=fund_profile_text,
        latest_nav=_fmt(metrics.get("latest_nav")),
        current_estimate_text=current_estimate_text,
        return_7d=_fmt(metrics.get("return_7d_calendar")),
        return_30d=_fmt(metrics.get("return_30d_calendar")),
        return_60d=_fmt(metrics.get("return_60d")),
        return_90d=_fmt(metrics.get("return_90d_calendar")),
        return_1trading=_fmt(metrics.get("return_1trading")),
        return_5trading=_fmt(metrics.get("return_5trading")),
        return_10trading=_fmt(metrics.get("return_10trading")),
        return_20trading=_fmt(metrics.get("return_20trading")),
        return_60trading=_fmt(metrics.get("return_60trading")),
        period_7d_range=period_7d_range,
        period_30d_range=period_30d_range,
        period_90d_range=period_90d_range,
        max_drawdown_7d=_fmt(metrics.get("max_drawdown_7d_calendar")),
        max_drawdown_30d=_fmt(metrics.get("max_drawdown_30d_calendar")),
        max_drawdown_60d=_fmt(metrics.get("max_drawdown_60d")),
        max_drawdown_90d=_fmt(metrics.get("max_drawdown_90d_calendar")),
        volatility_30d=_fmt(metrics.get("volatility_30d")),
        volatility_60d=_fmt(metrics.get("volatility_60d")),
        volatility_90d=_fmt(metrics.get("volatility_90d")),
        downside_volatility_30d=_fmt(metrics.get("downside_volatility_30d")),
        downside_volatility_60d=_fmt(metrics.get("downside_volatility_60d")),
        ma_5=_fmt(metrics.get("ma_5")),
        ma_10=_fmt(metrics.get("ma_10")),
        ma_20=_fmt(metrics.get("ma_20")),
        ma_60=_fmt(metrics.get("ma_60")),
        trend=str(metrics.get("trend", "未知")),
        position_7d=_fmt(metrics.get("position_in_7d_range")),
        position_30d=_fmt(metrics.get("position_in_30d_range")),
        position_60d=_fmt(metrics.get("position_in_60d_range")),
        position_90d=_fmt(metrics.get("position_in_90d_range")),
        rebound_30d=_fmt(metrics.get("rebound_from_30d_low")),
        pullback_30d=_fmt(metrics.get("pullback_from_30d_high")),
        momentum_acceleration_5d=_fmt(metrics.get("momentum_acceleration_5d")),
        ewma_volatility_20d=_fmt(metrics.get("ewma_volatility_20d")),
        volatility_percentile_30d=_fmt(metrics.get("volatility_percentile_30d")),
        volatility_regime_30d=str(metrics.get("volatility_regime_30d", "未知")),
        calmar_60d=_fmt(metrics.get("calmar_60d")),
        calmar_90d=_fmt(metrics.get("calmar_90d")),
        consecutive=consecutive_info,
        sharpe_30d=_fmt(metrics.get("sharpe_30d")),
        sharpe_60d=_fmt(metrics.get("sharpe_60d")),
        win_rate_30d=_fmt(metrics.get("win_rate_30d")),
        win_rate_60d=_fmt(metrics.get("win_rate_60d")),
        daily_mean=daily_stats.get("mean", "N/A"),
        daily_max=daily_stats.get("max", "N/A"),
        daily_min=daily_stats.get("min", "N/A"),
        nav_delay_note=nav_delay_note,
        risk_text=risk_text,
        forecast_text=forecast_text,
        macro_summary=macro.get("summary", "宏观数据暂不可用"),
        macro_risks="；".join(macro.get("risk_factors", [])) or "暂无",
        position_text=position_text,
        backtest_validation_text=backtest_validation_text,
    )


def _call_llm(api_key, base_url, model, user_prompt, temperature, max_tokens) -> Optional[Dict[str, Any]]:
    """调用 LLM，自动检测 Anthropic 或 OpenAI 格式"""

    # 检测是否为 Claude 模型（使用 Anthropic API）
    if model and 'claude' in model.lower():
        return _call_anthropic_api(api_key, base_url, model, user_prompt, temperature, max_tokens)
    else:
        return _call_openai_api(api_key, base_url, model, user_prompt, temperature, max_tokens)


def _call_anthropic_api(api_key, base_url, model, user_prompt, temperature, max_tokens) -> Optional[Dict[str, Any]]:
    """调用 Anthropic Messages API（使用直接 HTTP 请求以避免 SDK 兼容性问题）"""
    try:
        import requests

        url = f"{base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_prompt + "\n\n请严格按 JSON 格式输出，不要输出其他内容。"}
            ]
        }

        response = requests.post(url, headers=headers, json=payload, timeout=120)

        if response.status_code != 200:
            logger.error(f"Anthropic API 返回错误: {response.status_code} - {response.text[:200]}")
            return None

        result = response.json()
        content = result["content"][0]["text"]
        logger.info(f"Anthropic API 调用成功: {content[:200]}...")

        # 提取 JSON
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3]

        return json.loads(content)
    except Exception as e:
        logger.error(f"Anthropic API 调用失败: {e}")
        return None


def _call_openai_api(api_key, base_url, model, user_prompt, temperature, max_tokens) -> Optional[Dict[str, Any]]:
    """调用 OpenAI 兼容 API"""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 尝试1：使用 response_format={"type": "json_object"}
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        logger.info(f"OpenAI API 调用成功: {content[:200]}...")
        return json.loads(content)
    except Exception as e1:
        logger.warning(f"response_format=json_object 失败: {e1}，尝试去掉 response_format 重试")

    # 尝试2：去掉 response_format 重试
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt + "\n\n请只输出 JSON，不要输出其他内容。"},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        logger.info(f"OpenAI API 重试完成: {content[:200]}...")
        # 尝试提取 JSON
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)
    except Exception as e2:
        logger.error(f"OpenAI API 调用两次均失败: {e2}")
        return None


def _ensure_fields(result: Dict, position: Optional[Dict]) -> None:
    """确保所有必要字段存在"""
    defaults = {
        "conclusion": "中性",
        "summary_7d": "",
        "summary_30d": "",
        "summary_90d": "",
        "risk_explanation": "",
        "position_advice": "未提供持仓信息，仅分析基金本身" if not position or not position.get("cost_nav") else "",
        "main_risks": [],
        "watch_points": [],
        "buy_conditions": [],
        "reduce_conditions": [],
        "dca_suggestion": "数据不足",
        "confidence": "中",
        "data_basis": "",
        "disclaimer": "本分析仅用于个人研究参考，不构成任何投资建议。基金投资有风险，过往业绩不预示未来表现。",
        "forecast_summary_1d": "",
        "forecast_summary_3d": "",
        "forecast_summary_7d": "",
        "forecast_summary_30d": "",
        "forecast_risks": [],
    }
    for key, default in defaults.items():
        result.setdefault(key, default)


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _safe_num(value, default=0):
    if value is None:
        return default
    return value


def _rule_based_analysis(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """规则化分析：当 LLM 不可用时的回退方案"""
    metrics = analysis_data.get("metrics", {})
    macro = analysis_data.get("macro", {})
    risk = analysis_data.get("risk", {})
    position = analysis_data.get("position")

    if metrics.get("error"):
        return {
            "conclusion": "数据不足",
            "summary_7d": f"无法完成分析：{metrics.get('error')}",
            "summary_30d": "数据不足以进行中期分析",
            "summary_90d": "数据不足以进行长期分析",
            "risk_explanation": "数据不足",
            "position_advice": "未提供持仓信息，仅分析基金本身",
            "main_risks": ["净值数据不足"],
            "watch_points": [],
            "buy_conditions": [],
            "reduce_conditions": [],
            "dca_suggestion": "数据不足",
            "confidence": "低",
            "data_basis": "数据不足，无法给出有效判断",
            "disclaimer": "本分析仅用于个人研究参考，不构成任何投资建议。",
            "forecast_summary_1d": "数据不足，无法生成1日涨跌情景",
            "forecast_summary_3d": "数据不足，无法生成3日走势情景",
            "forecast_summary_7d": "数据不足，无法生成走势情景",
            "forecast_summary_30d": "数据不足，无法生成走势情景",
            "forecast_risks": ["净值数据不足"],
        }

    return_7d = _safe_num(metrics.get("return_7d"), 0)
    return_30d = _safe_num(metrics.get("return_30d"), 0)
    return_60d = _safe_num(metrics.get("return_60d"), 0)
    return_90d = _safe_num(metrics.get("return_90d"), 0)
    dd_30d = abs(_safe_num(metrics.get("max_drawdown_30d"), 0))
    dd_60d = abs(_safe_num(metrics.get("max_drawdown_60d"), 0))
    vol_30d = _safe_num(metrics.get("volatility_30d"), 0)
    trend = metrics.get("trend", "")
    pos_30d = _safe_num(metrics.get("position_in_30d_range"), 50)
    pos_60d = _safe_num(metrics.get("position_in_60d_range"), 50)
    sharpe = _safe_num(metrics.get("sharpe_30d"), 0)
    win_rate = _safe_num(metrics.get("win_rate_30d"), 50)
    rebound = _safe_num(metrics.get("rebound_from_30d_low"), 0)
    pullback = _safe_num(metrics.get("pullback_from_30d_high"), 0)

    # 使用 risk_engine 的评分
    risk_score = risk.get("risk_score", 50) if risk else 50
    risk_level = risk.get("risk_level", "中") if risk else "中"
    risk_reasons = risk.get("reasons", []) if risk else []
    risk_warnings = risk.get("warnings", []) if risk else []

    # 判定结论
    if risk_score <= 30:
        conclusion = "偏积极"
    elif risk_score <= 50:
        conclusion = "中性"
    elif risk_score <= 70:
        conclusion = "偏谨慎"
    else:
        conclusion = "风险较高"

    # 构建内容
    summary_7d = f"近7天涨跌幅{return_7d}%，"
    summary_7d += "短期表现较好。" if return_7d > 0 else "短期承压，建议观察。"

    summary_30d = f"近30天涨跌幅{return_30d}%，趋势{trend}，波动率{vol_30d}%。"
    if return_30d > 0:
        summary_30d += "中期有一定涨幅，注意回调风险。"

    summary_90d = f"近90天涨跌幅{return_90d}%，近60天回撤{dd_60d}%。"
    if return_90d < -10:
        summary_90d += "长期趋势偏弱，需关注是否企稳。"

    risk_explanation = f"风险评分{risk_score}/100（{risk_level}）。"
    if risk_reasons:
        risk_explanation += "主要因素：" + "；".join(risk_reasons[:3]) + "。"

    # 持仓建议
    position_advice = "未提供持仓信息，仅分析基金本身"
    if position and position.get("cost_nav") is not None:
        latest_nav = metrics.get("latest_nav")
        cost_nav = float(position.get("cost_nav", 0))
        if latest_nav and cost_nav > 0:
            profit_pct = (float(latest_nav) - cost_nav) / cost_nav * 100
            max_loss = float(position.get("max_loss_percent", 20))
            position_advice = f"当前持仓浮盈/浮亏{profit_pct:.2f}%。"
            if profit_pct < 0 and abs(profit_pct) / max_loss > 0.7:
                position_advice += f"亏损已接近最大可承受亏损线({max_loss}%)，需关注风险。"

    main_risks = risk_warnings[:4] if risk_warnings else [
        f"近30天最大回撤{dd_30d}%",
        f"年化波动率{vol_30d}%",
    ]

    watch_points = []
    if pos_30d < 20 and "空头" not in str(trend):
        watch_points.append("净值接近30日低位，关注是否企稳反弹")
    if rebound > 5:
        watch_points.append(f"近期反弹强度{rebound}%，关注反弹持续性")
    if pullback > 5:
        watch_points.append(f"近期回落{pullback}%，关注是否继续下探")
    if not watch_points:
        watch_points = ["关注20日/60日均线支撑", "关注成交量变化"]

    buy_conditions = [
        "可关注：连续3天以上缩量企稳信号出现",
        "可关注：净值回调至60日均线附近且获得支撑",
        "可关注：波动率下降且趋势转多",
    ]
    reduce_conditions = [
        "警惕：单日跌幅超过3%且伴随放量",
        "警惕：跌破近60日低点支撑位",
        "警惕：均线出现死叉信号",
    ]
    dca_suggestion = "数据不足"
    if position and position.get("is_dca"):
        if "空头" in str(trend):
            dca_suggestion = "可降低金额"
        elif risk_score < 50:
            dca_suggestion = "可关注"
        elif risk_score > 70:
            dca_suggestion = "可暂停观察"

    forecast = analysis_data.get("forecast", {})
    f1 = forecast.get("forecast_1d", {})
    f3 = forecast.get("forecast_3d", {})
    f7 = forecast.get("forecast_7d", {})
    f30 = forecast.get("forecast_30d", {})
    forecast_summary_1d = f"涨跌判断{f1.get('rise_fall','不确定')}，方向倾向{f1.get('direction','不确定')}，上行概率{f1.get('up_probability',33)}%，震荡概率{f1.get('sideways_probability',34)}%，下行概率{f1.get('down_probability',33)}%。置信度{f1.get('confidence','低')}。此判断不是确定预测。"
    forecast_summary_3d = f"涨跌判断{f3.get('rise_fall','不确定')}，方向倾向{f3.get('direction','不确定')}，上行概率{f3.get('up_probability',33)}%，震荡概率{f3.get('sideways_probability',34)}%，下行概率{f3.get('down_probability',33)}%。置信度{f3.get('confidence','低')}。此判断不是确定预测。"
    forecast_summary_7d = f"涨跌判断{f7.get('rise_fall','不确定')}，方向倾向{f7.get('direction','不确定')}，上行概率{f7.get('up_probability',33)}%，震荡概率{f7.get('sideways_probability',34)}%，下行概率{f7.get('down_probability',33)}%。置信度{f7.get('confidence','低')}。此判断不是确定预测。"
    forecast_summary_30d = f"涨跌判断{f30.get('rise_fall','不确定')}，方向倾向{f30.get('direction','不确定')}，上行概率{f30.get('up_probability',33)}%，震荡概率{f30.get('sideways_probability',34)}%，下行概率{f30.get('down_probability',33)}%。置信度{f30.get('confidence','低')}。此判断不是确定预测。"
    forecast_risks = [f"置信度为{f7.get('confidence','低')}，存在不确定性"] if f7.get("confidence") == "低" else []

    # 基于回测质量调整置信度
    validation = forecast.get("validation") if forecast else None
    rule_confidence = "中（规则化分析，建议配置LLM获得更全面分析）"
    if validation:
        quality = validation.get("probability_quality", "low")
        calibrated = validation.get("is_calibrated", False)
        if quality == "low":
            rule_confidence = "低（规则化分析，回测未验证规则有效性）"
        elif not calibrated:
            rule_confidence = "低（规则化分析，回测未校准）"

    return {
        "conclusion": conclusion,
        "summary_7d": summary_7d,
        "summary_30d": summary_30d,
        "summary_90d": summary_90d,
        "risk_explanation": risk_explanation,
        "position_advice": position_advice,
        "main_risks": main_risks[:5],
        "watch_points": watch_points[:5],
        "buy_conditions": buy_conditions,
        "reduce_conditions": reduce_conditions,
        "dca_suggestion": dca_suggestion,
        "confidence": rule_confidence,
        "data_basis": f"基于近{metrics.get('data_days', 'N/A')}个交易日的历史净值数据、技术指标和宏观因素综合分析",
        "disclaimer": "本分析基于规则引擎生成，仅用于个人研究参考，不构成任何投资建议。基金投资有风险，过往业绩不预示未来表现。",
        "score_details": risk_reasons,
        "forecast_summary_1d": forecast_summary_1d,
        "forecast_summary_3d": forecast_summary_3d,
        "forecast_summary_7d": forecast_summary_7d,
        "forecast_summary_30d": forecast_summary_30d,
        "forecast_risks": forecast_risks,
    }
