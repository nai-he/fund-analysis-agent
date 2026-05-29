"""
宏观影响因素模块
获取国际市场相关数据，作为辅助参考
不编造数据，获取不到时标记 unavailable
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def get_macro_factors() -> Dict[str, Any]:
    """
    获取宏观因素数据
    返回结构化宏观数据
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    result = {
        "summary": "",
        "macro_summary": {},
        "risk_factors": [],
        "global_indices": [],
        "forex": [],
        "commodities": [],
        "interbank_rates": [],
        "status": "ok",
        "as_of": today_str,
    }

    # 获取全球指数
    indices = _get_global_indices_structured()
    result["global_indices"] = indices

    # 获取汇率
    forex = _get_forex_structured()
    result["forex"] = forex

    # 获取商品
    commodities = _get_commodities_structured()
    result["commodities"] = commodities

    # 获取银行间利率
    interbank = _get_interbank_rates()
    result["interbank_rates"] = interbank

    # 生成宏观摘要
    result["macro_summary"] = _build_macro_summary_v2(indices, forex, commodities, interbank)
    result["risk_factors"] = _analyze_macro_risks_v2(indices, forex, commodities, interbank)
    result["summary"] = result["macro_summary"].get("text", "宏观数据暂不可用")

    # 判断状态
    has_any_data = any(
        item.get("status") != "unavailable"
        for lst in [indices, forex, commodities, interbank]
        for item in lst
    )
    if not has_any_data:
        result["status"] = "unavailable"
        result["summary"] = "宏观数据暂不可用，请关注后续版本更新"

    return result


def _get_global_indices_structured() -> List[Dict[str, Any]]:
    """获取全球主要指数结构化数据"""
    results = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 尝试通过 akshare 获取
    try:
        import akshare as ak

        # 方法1：index_global_spot_em（东方财富全球指数）
        try:
            df = ak.index_global_spot_em()
            if df is not None and not df.empty:
                # 查找关键指数
                targets = {
                    "纳斯达克": ["纳斯达克", "NASDAQ"],
                    "标普500": ["标普500", "S&P 500", "标普"],
                    "恒生指数": ["恒生指数", "恒生"],
                    "恒生科技": ["恒生科技"],
                }

                for target_name, keywords in targets.items():
                    for _, row in df.iterrows():
                        row_name = str(row.get("名称", row.get("指数名称", "")))
                        if any(kw in row_name for kw in keywords):
                            latest = _safe_numeric(row.get("最新价", row.get("最新", row.get("现价"))))
                            change_pct = _safe_numeric(row.get("涨跌幅", row.get("涨跌%", row.get("变动%"))))
                            results.append({
                                "name": target_name,
                                "latest": latest,
                                "change_pct": change_pct,
                                "source": "akshare",
                                "as_of": today_str,
                            })
                            break
        except Exception as e:
            logger.warning(f"index_global_spot_em 失败: {e}")

        # 方法2：尝试获取美股指数
        try:
            if not any(r["name"] == "纳斯达克" for r in results):
                nasdaq = ak.index_us_stock_sina(symbol=".IXIC")
                if nasdaq is not None and not nasdaq.empty:
                    latest_row = nasdaq.iloc[-1]
                    latest = _safe_numeric(latest_row.get("close", latest_row.get("收盘价")))
                    prev = _safe_numeric(latest_row.get("open", latest_row.get("开盘价")))
                    change_pct = round((latest - prev) / prev * 100, 2) if prev and prev > 0 else None
                    results.append({
                        "name": "纳斯达克",
                        "latest": latest,
                        "change_pct": change_pct,
                        "source": "akshare_sina",
                        "as_of": today_str,
                    })
        except Exception:
            pass

        try:
            if not any(r["name"] == "标普500" for r in results):
                spx = ak.index_us_stock_sina(symbol=".INX")
                if spx is not None and not spx.empty:
                    latest_row = spx.iloc[-1]
                    latest = _safe_numeric(latest_row.get("close", latest_row.get("收盘价")))
                    prev = _safe_numeric(latest_row.get("open", latest_row.get("开盘价")))
                    change_pct = round((latest - prev) / prev * 100, 2) if prev and prev > 0 else None
                    results.append({
                        "name": "标普500",
                        "latest": latest,
                        "change_pct": change_pct,
                        "source": "akshare_sina",
                        "as_of": today_str,
                    })
        except Exception:
            pass

        # 方法3：港股指数
        try:
            if not any(r["name"] == "恒生指数" for r in results):
                hsi = ak.stock_hk_index_daily_sina(symbol="HSI")
                if hsi is not None and not hsi.empty:
                    latest_row = hsi.iloc[-1]
                    results.append({
                        "name": "恒生指数",
                        "latest": _safe_numeric(latest_row.get("close")),
                        "change_pct": None,
                        "source": "akshare_sina",
                        "as_of": today_str,
                    })
        except Exception:
            pass

    except ImportError:
        logger.warning("akshare 不可用，跳过全球指数获取")
    except Exception as e:
        logger.warning(f"获取全球指数异常: {e}")

    # 标记不可用的指数
    expected = ["纳斯达克", "标普500", "恒生指数", "恒生科技"]
    for name in expected:
        if not any(r["name"] == name for r in results):
            results.append({
                "name": name,
                "status": "unavailable",
                "source": "none",
                "as_of": today_str,
            })

    return results


def _get_forex_structured() -> List[Dict[str, Any]]:
    """获取汇率结构化数据"""
    results = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        import akshare as ak
        # 尝试获取美元人民币中间价
        try:
            fx_df = ak.fx_spot_quote()
            if fx_df is not None and not fx_df.empty:
                # 查找美元/人民币
                for _, row in fx_df.iterrows():
                    row_dict = row.to_dict()
                    row_str = str(row_dict)
                    if "美元" in row_str and ("人民" in row_str or "CNY" in row_str):
                        pair = "美元/人民币"
                        latest = None
                        for k, v in row_dict.items():
                            try:
                                latest = float(v)
                                break
                            except (ValueError, TypeError):
                                continue
                        results.append({
                            "name": pair,
                            "latest": latest,
                            "source": "akshare",
                            "as_of": today_str,
                        })
                        break
        except Exception as e:
            logger.warning(f"获取外汇数据失败: {e}")

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"获取汇率异常: {e}")

    if not results:
        results.append({"name": "美元/人民币", "status": "unavailable", "source": "none", "as_of": today_str})
        results.append({"name": "美元指数", "status": "unavailable", "source": "none", "as_of": today_str})

    return results


def _get_commodities_structured() -> List[Dict[str, Any]]:
    """获取商品价格结构化数据"""
    results = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        import akshare as ak

        # 黄金
        try:
            gold_df = ak.spot_golden_benchmark_sge()
            if gold_df is not None and not gold_df.empty:
                latest_row = gold_df.iloc[-1]
                latest = _safe_numeric(latest_row.iloc[0] if hasattr(latest_row, 'iloc') else latest_row)
                results.append({
                    "name": "黄金",
                    "latest": latest,
                    "source": "akshare",
                    "as_of": today_str,
                })
        except Exception:
            pass

        # 原油
        try:
            oil_df = ak.futures_foreign_hist(symbol="CL00Y")
            if oil_df is not None and not oil_df.empty:
                latest_row = oil_df.iloc[-1]
                latest = _safe_numeric(latest_row.get("close", latest_row.get("收盘价")))
                results.append({
                    "name": "原油(WTI)",
                    "latest": latest,
                    "source": "akshare",
                    "as_of": today_str,
                })
        except Exception:
            pass

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"获取商品数据异常: {e}")

    if not any(r.get("name") == "黄金" for r in results):
        results.append({"name": "黄金", "status": "unavailable", "source": "none", "as_of": today_str})
    if not any(r.get("name") == "原油(WTI)" for r in results):
        results.append({"name": "原油(WTI)", "status": "unavailable", "source": "none", "as_of": today_str})

    return results


def _get_interbank_rates() -> List[Dict[str, Any]]:
    """获取银行间拆借利率（SHIBOR）"""
    results = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        import akshare as ak

        # SHIBOR 隔夜、1周、1月
        try:
            shibor_df = ak.rate_interbank(
                market="上海银行间同业拆放利率",
                symbol="Shibor",
                indicator="隔夜",
            )
            if shibor_df is not None and not shibor_df.empty:
                latest_row = shibor_df.iloc[-1]
                rate = _safe_numeric(latest_row.get("利率", latest_row.iloc[1] if len(latest_row) > 1 else None))
                change = _safe_numeric(latest_row.get("涨跌", latest_row.iloc[2] if len(latest_row) > 2 else None))
                results.append({
                    "name": "SHIBOR隔夜",
                    "latest": rate,
                    "change": change,
                    "source": "akshare",
                    "as_of": today_str,
                })
        except Exception:
            pass

        # SHIBOR 1周
        try:
            shibor_1w = ak.rate_interbank(
                market="上海银行间同业拆放利率",
                symbol="Shibor",
                indicator="1周",
            )
            if shibor_1w is not None and not shibor_1w.empty:
                latest_row = shibor_1w.iloc[-1]
                rate = _safe_numeric(latest_row.get("利率", latest_row.iloc[1] if len(latest_row) > 1 else None))
                results.append({
                    "name": "SHIBOR1周",
                    "latest": rate,
                    "source": "akshare",
                    "as_of": today_str,
                })
        except Exception:
            pass

        # SHIBOR 1月
        try:
            shibor_1m = ak.rate_interbank(
                market="上海银行间同业拆放利率",
                symbol="Shibor",
                indicator="1月",
            )
            if shibor_1m is not None and not shibor_1m.empty:
                latest_row = shibor_1m.iloc[-1]
                rate = _safe_numeric(latest_row.get("利率", latest_row.iloc[1] if len(latest_row) > 1 else None))
                results.append({
                    "name": "SHIBOR1月",
                    "latest": rate,
                    "source": "akshare",
                    "as_of": today_str,
                })
        except Exception:
            pass

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"获取SHIBOR异常: {e}")

    expected = ["SHIBOR隔夜", "SHIBOR1周", "SHIBOR1月"]
    for name in expected:
        if not any(r["name"] == name for r in results):
            results.append({"name": name, "status": "unavailable", "source": "none", "as_of": today_str})

    return results


def _build_macro_summary_v2(
    indices: List[Dict], forex: List[Dict], commodities: List[Dict],
    interbank: Optional[List[Dict]] = None,
) -> Dict[str, str]:
    """构建结构化宏观摘要"""
    result = {
        "risk_appetite": "neutral",
        "overseas_direction": "mixed",
        "forex_pressure": "stable",
        "commodity_disturbance": "none",
        "text": "",
    }

    parts = []

    # 分析海外市场方向
    nasdaq = next((i for i in indices if i.get("name") == "纳斯达克"), None)
    spx = next((i for i in indices if i.get("name") == "标普500"), None)
    hsi = next((i for i in indices if i.get("name") == "恒生指数"), None)

    us_changes = []
    if nasdaq and nasdaq.get("change_pct") is not None:
        us_changes.append(nasdaq["change_pct"])
    if spx and spx.get("change_pct") is not None:
        us_changes.append(spx["change_pct"])

    if us_changes:
        avg_us = sum(us_changes) / len(us_changes)
        if avg_us > 1:
            result["overseas_direction"] = "bullish"
            parts.append("美股市场整体上涨")
            result["risk_appetite"] = "risk-on"
        elif avg_us < -1:
            result["overseas_direction"] = "bearish"
            parts.append("美股市场整体下跌")
            result["risk_appetite"] = "risk-off"
        else:
            parts.append("美股市场小幅波动")

    # 汇率压力
    usdcny = next((f for f in forex if f.get("name") == "美元/人民币"), None)
    if usdcny and usdcny.get("latest") is not None:
        rate = usdcny["latest"]
        if rate > 7.3:
            result["forex_pressure"] = "贬值压力较大"
            parts.append(f"人民币汇率{rate}，贬值压力较大，可能影响QDII基金收益和外资流入")
        elif rate > 7.1:
            result["forex_pressure"] = "有一定贬值压力"
            parts.append(f"人民币汇率{rate}，存在一定贬值压力")
        else:
            result["forex_pressure"] = "stable"
            parts.append("人民币汇率相对稳定")

    # 商品扰动
    gold = next((c for c in commodities if c.get("name") == "黄金"), None)
    oil = next((c for c in commodities if c.get("name", "").startswith("原油")), None)
    if gold and gold.get("latest") is not None:
        parts.append(f"黄金报价{gold['latest']}")
    if oil and oil.get("latest") is not None:
        parts.append(f"原油报价{oil['latest']}")
        result["commodity_disturbance"] = "data_available"

    # 流动性分析（基于SHIBOR）
    if interbank:
        shibor_on = next((r for r in interbank if r.get("name") == "SHIBOR隔夜"), None)
        shibor_1w = next((r for r in interbank if r.get("name") == "SHIBOR1周"), None)
        shibor_1m = next((r for r in interbank if r.get("name") == "SHIBOR1月"), None)

        has_shibor = any(
            r and r.get("latest") is not None for r in [shibor_on, shibor_1w, shibor_1m]
        )
        if has_shibor:
            on_rate = shibor_on.get("latest") if shibor_on else None
            m1_rate = shibor_1m.get("latest") if shibor_1m else None

            if on_rate is not None:
                parts.append(f"SHIBOR隔夜{on_rate}%")
                if on_rate > 2.5:
                    result["liquidity"] = "tight"
                    parts.append("短期资金面偏紧，可能抑制风险偏好")
                    if result["risk_appetite"] == "risk-on":
                        result["risk_appetite"] = "neutral"
                elif on_rate < 1.5:
                    result["liquidity"] = "loose"
                    parts.append("短期资金面宽松，有利于风险资产")
                    if result["risk_appetite"] == "neutral":
                        result["risk_appetite"] = "risk-on"
                else:
                    result["liquidity"] = "neutral"

            # 期限利差判断
            if on_rate is not None and m1_rate is not None:
                spread = m1_rate - on_rate
                result["interbank_spread"] = round(spread, 2)
                if spread < 0.1:
                    result["liquidity"] = "tight"
                    parts.append("SHIBOR期限利差收窄，资金面趋于紧张")
                elif spread > 0.8:
                    parts.append("SHIBOR期限利差较宽，短期资金充裕")
        else:
            result["liquidity"] = "unknown"
    else:
        result["liquidity"] = "unknown"

    if parts:
        result["text"] = "；".join(parts) + "（宏观数据仅供参考，不构成预测依据）"
    else:
        result["text"] = "宏观数据暂不可用"

    return result


def _analyze_macro_risks_v2(
    indices: List[Dict], forex: List[Dict], commodities: List[Dict],
    interbank: Optional[List[Dict]] = None,
) -> List[str]:
    """分析宏观风险因素 v2"""
    risks = []

    nasdaq = next((i for i in indices if i.get("name") == "纳斯达克"), None)
    if nasdaq and nasdaq.get("status") != "unavailable":
        change = nasdaq.get("change_pct")
        if change is not None and change < -1:
            risks.append("纳斯达克指数下跌，科技股风险偏好下降")

    usdcny = next((f for f in forex if f.get("name") == "美元/人民币"), None)
    if usdcny and usdcny.get("latest") is not None and usdcny["latest"] > 7.2:
        risks.append("人民币汇率承压，可能影响跨境资金流动和外资持仓偏好")

    if commodities:
        has_commodities = any(c.get("status") != "unavailable" for c in commodities)
        if has_commodities:
            risks.append("大宗商品价格波动可能影响相关行业板块")

    # SHIBOR流动性风险
    if interbank:
        shibor_on = next((r for r in interbank if r.get("name") == "SHIBOR隔夜"), None)
        if shibor_on and shibor_on.get("latest") is not None:
            if shibor_on["latest"] > 2.5:
                risks.append(f"SHIBOR隔夜利率{shibor_on['latest']}%，短期资金面偏紧，可能对股市估值形成压力")
            elif shibor_on["latest"] < 1.2:
                risks.append("银行间流动性极度宽松，需关注资金空转和政策调控风险")

    if indices or forex:
        risks.append("国际地缘政治风险可能影响全球资本市场情绪")
        risks.append("美联储货币政策不确定性可能影响全球流动性和QDII基金表现")

    return risks


def _safe_numeric(val) -> Optional[float]:
    """安全转为数字"""
    if val is None:
        return None
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return None
