"""
基金数据获取模块
数据源优先级：AKShare > efinance > Tencent/Tiantian (from akshare-fund logic)
"""
import logging
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

from providers.tencent_fund import (
    get_tencent_fund_basic,
    get_tencent_fund_quote,
    get_tencent_nav_estimate,
)

logger = logging.getLogger(__name__)

# 常见列名候选列表，用于兼容不同数据源返回格式
NAV_DATE_CANDIDATES = ["净值日期", "date", "日期", "time", "净值日", "交易日期", "Date", "nav_date"]
UNIT_NAV_CANDIDATES = ["单位净值", "nav", "netvalue", "单位", "净值", "dwjz", "NAV", "unit_nav"]
ACC_NAV_CANDIDATES = ["累计净值", "accumulatednav", "累计", "ljjz", "acc_nav", "累计单位净值"]
DAILY_RETURN_CANDIDATES = ["日增长率", "dailyreturn", "增长率", "日涨幅", "涨跌幅", "rzzl", "change_pct", "日增长"]


def get_fund_info(code: str) -> Optional[Dict[str, Any]]:
    """
    获取基金基本信息：名称、类型、基金公司
    优先级：AKShare > efinance > Tencent/Tiantian
    """
    # 方式1：akshare fund_name_em（快速，含基金类型）
    try:
        import akshare as ak
        all_funds = ak.fund_name_em()
        matched = all_funds[all_funds["基金代码"] == code]
        if not matched.empty:
            row = matched.iloc[0]
            result = {
                "code": code,
                "name": str(row.get("基金简称", f"基金{code}")),
                "type": str(row.get("基金类型", "未知")),
                "company": "未知",
                "source": "akshare",
            }
            logger.info(f"[akshare] fund_name_em 获取基金信息成功: {code} -> {result['name']}")
            company = _get_fund_company_from_xq(code)
            if company:
                result["company"] = company
            return result
    except Exception as e:
        logger.warning(f"[akshare] fund_name_em 失败: {code}, error={e}")

    # 方式2：efinance 备用
    try:
        import efinance as ef
        base_info = ef.fund.get_base_info(code)
        if base_info is not None:
            info_dict = _parse_efinance_fund_info(base_info, code)
            if info_dict and info_dict.get("name"):
                if info_dict.get("type") == "未知":
                    info_dict["type"] = _get_fund_type_from_em(code)
                logger.info(f"[efinance] 获取基金信息成功: {code} -> {info_dict.get('name')}")
                return info_dict
    except Exception as e:
        logger.warning(f"[efinance] 获取基金信息失败: {code}, error={e}")

    # 方式3：Tencent/Tiantian fallback (from akshare-fund logic)
    try:
        tc_info = get_tencent_fund_basic(code)
        if tc_info and tc_info.get("name"):
            logger.info(f"[tencent] 获取基金信息成功: {code} -> {tc_info.get('name')}")
            return tc_info
    except Exception as e:
        logger.warning(f"[tencent] 获取基金信息失败: {code}, error={e}")

    return None


def _get_fund_company_from_xq(code: str) -> Optional[str]:
    """通过雪球接口补充基金公司信息"""
    try:
        import akshare as ak
        info = ak.fund_individual_basic_info_xq(symbol=code)
        if info is not None and "item" in info.columns and "value" in info.columns:
            items = info["item"]
            values = info["value"]
            for i, item in enumerate(items):
                if "基金公司" in str(item) or "管理人" in str(item):
                    val = str(values.iloc[i])
                    if val and val != "nan" and val != "<NA>":
                        return val
    except Exception:
        pass
    return None


def _get_fund_type_from_em(code: str) -> str:
    """通过 fund_name_em 补充基金类型"""
    try:
        import akshare as ak
        all_funds = ak.fund_name_em()
        matched = all_funds[all_funds["基金代码"] == code]
        if not matched.empty:
            return str(matched.iloc[0].get("基金类型", "未知"))
    except Exception:
        pass
    return "未知"


def _parse_efinance_fund_info(base_info, code: str) -> Optional[Dict[str, Any]]:
    """解析 efinance 基金基本信息"""
    try:
        if isinstance(base_info, dict):
            return {
                "code": code,
                "name": base_info.get("名称", base_info.get("基金简称", f"基金{code}")),
                "type": base_info.get("类型", base_info.get("基金类型", "未知")),
                "company": base_info.get("基金公司", base_info.get("基金管理人", "未知")),
                "source": "efinance",
            }
        if isinstance(base_info, pd.Series):
            return {
                "code": code,
                "name": base_info.get("名称", base_info.get("基金简称", f"基金{code}")),
                "type": base_info.get("类型", base_info.get("基金类型", "未知")),
                "company": base_info.get("基金公司", base_info.get("基金管理人", "未知")),
                "source": "efinance",
            }
    except Exception as e:
        logger.warning(f"解析 efinance 基金信息失败: {e}")
    return None


def get_fund_nav_history(code: str, days: int = 90) -> Optional[pd.DataFrame]:
    """
    获取基金历史净值数据
    优先级：AKShare > efinance > Tencent（净值估值仅作参考）
    返回 DataFrame，包含 净值日期、单位净值、日增长率 等列
    """
    best_df = None

    # 尝试 akshare
    try:
        import akshare as ak
        # 尝试多个 indicator 值以兼容不同版本
        for indicator in ["单位净值走势", "单位净值", "累计净值走势"]:
            try:
                nav_df = ak.fund_open_fund_info_em(symbol=code, indicator=indicator)
                if nav_df is not None and not nav_df.empty:
                    nav_df = _normalize_nav_df(nav_df, source="akshare")
                    if nav_df is not None and not nav_df.empty:
                        nav_df = nav_df.sort_values("净值日期", ascending=True)
                        logger.info(f"[akshare] 获取净值数据成功: {code}, 共 {len(nav_df)} 条")
                        if len(nav_df) >= 5:
                            return nav_df
                        elif best_df is None or len(nav_df) > len(best_df):
                            best_df = nav_df
                    break  # 成功获取，跳出 indicator 循环
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[akshare] 获取净值数据失败: {code}, error={e}")

    # 尝试 efinance
    try:
        import efinance as ef
        # efinance 不同版本 API 不同
        for func_name in ["get_quote_history", "get_history_bill"]:
            try:
                func = getattr(ef.fund, func_name, None)
                if func is None:
                    continue
                nav_df = func(code)
                if nav_df is not None and not nav_df.empty:
                    nav_df = _normalize_nav_df(nav_df, source="efinance")
                    if nav_df is not None and not nav_df.empty:
                        nav_df = nav_df.sort_values("净值日期", ascending=True)
                        logger.info(f"[efinance:{func_name}] 获取净值数据成功: {code}, 共 {len(nav_df)} 条")
                        if len(nav_df) >= 5:
                            return nav_df
                        elif best_df is None or len(nav_df) > len(best_df):
                            best_df = nav_df
                    break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[efinance] 获取净值数据失败: {code}, error={e}")

    # 如果前面已有部分数据，返回最佳结果
    if best_df is not None and len(best_df) >= 2:
        logger.info(f"使用部分净值数据: {code}, 共 {len(best_df)} 条")
        return best_df

    # 尝试 Tencent 净值估算（仅作为参考，数据精度不如前两者）
    try:
        est = get_tencent_nav_estimate(code)
        if est and est.get("unit_nav"):
            logger.info(f"[tencent] 获取净值估算成功: {code}, 但无历史序列，仅当日估值")
            # Tencent 只返回当日估值，无法构建时间序列
            # 仍返回一条记录供参考
            df = pd.DataFrame([{
                "净值日期": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "单位净值": est.get("unit_nav"),
                "日增长率": est.get("estimated_change_pct"),
            }])
            return df
    except Exception as e:
        logger.warning(f"[tencent] 获取净值估算失败: {code}, error={e}")

    logger.error(f"所有数据源均无法获取基金 {code} 的净值数据")
    return None


def _normalize_nav_df(df: pd.DataFrame, source: str = "unknown") -> Optional[pd.DataFrame]:
    """标准化净值 DataFrame，兼容多种列名格式"""
    try:
        df = df.copy()

        # 探测定量列
        _probe_and_rename(df, "净值日期", NAV_DATE_CANDIDATES)
        _probe_and_rename(df, "单位净值", UNIT_NAV_CANDIDATES)
        _probe_and_rename(df, "累计净值", ACC_NAV_CANDIDATES)
        _probe_and_rename(df, "日增长率", DAILY_RETURN_CANDIDATES)

        # 日期列标准化
        if "净值日期" in df.columns:
            df["净值日期"] = pd.to_datetime(df["净值日期"], errors="coerce")
            df = df.dropna(subset=["净值日期"])

        # 单位净值标准化
        if "单位净值" in df.columns:
            df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
            df = df.dropna(subset=["单位净值"])

        # 日增长率：缺失时从单位净值 pct_change 计算
        if "日增长率" in df.columns:
            df["日增长率"] = pd.to_numeric(df["日增长率"], errors="coerce")
        else:
            if "单位净值" in df.columns and len(df) >= 2:
                df["日增长率"] = df["单位净值"].pct_change() * 100
                logger.info(f"[{source}] 日增长率缺失，从单位净值 pct_change 计算")

        return df
    except Exception as e:
        logger.warning(f"[{source}] 标准化净值 DataFrame 失败: {e}")
        return df


def _probe_and_rename(df: pd.DataFrame, target: str, candidates: list[str]) -> None:
    """探测 DataFrame 列名并重命名为标准列名（优先精确匹配，再尝试模糊匹配）"""
    # 第一轮：精确匹配
    for col in df.columns:
        col_str = str(col).strip()
        for cand in candidates:
            if col_str == cand:
                if col != target:
                    df.rename(columns={col: target}, inplace=True)
                return
    # 第二轮：模糊匹配
    for col in df.columns:
        col_lower = str(col).lower().replace("_", "").replace("(", "").replace(")", "").replace(".", "")
        for cand in candidates:
            cand_lower = cand.lower().replace("_", "").replace("(", "").replace(")", "").replace(".", "")
            # 更严格的匹配：两个方向都检查，且长度差不太大
            if (cand_lower == col_lower) or (len(cand) >= 3 and cand_lower in col_lower):
                if col != target:
                    df.rename(columns={col: target}, inplace=True)
                return


def get_datasource_status(code: str) -> Dict[str, Any]:
    """返回各数据源可用性状态"""
    status = {
        "akshare": {"available": False, "detail": ""},
        "efinance": {"available": False, "detail": ""},
        "tencent": {"available": False, "detail": ""},
    }

    # AKShare
    try:
        import akshare as ak
        all_funds = ak.fund_name_em()
        matched = all_funds[all_funds["基金代码"] == code]
        if not matched.empty:
            status["akshare"]["available"] = True
            status["akshare"]["detail"] = "fund_name_em OK"
        else:
            status["akshare"]["detail"] = f"基金代码 {code} 未在 fund_name_em 中找到"
    except Exception as e:
        status["akshare"]["detail"] = str(e)[:100]

    # efinance
    try:
        import efinance as ef
        base_info = ef.fund.get_base_info(code)
        if base_info is not None:
            status["efinance"]["available"] = True
            status["efinance"]["detail"] = "get_base_info OK"
        else:
            status["efinance"]["detail"] = "返回空数据"
    except Exception as e:
        status["efinance"]["detail"] = str(e)[:100]

    # Tencent/Tiantian
    try:
        tc = get_tencent_fund_basic(code)
        if tc and tc.get("name"):
            status["tencent"]["available"] = True
            status["tencent"]["detail"] = "tiantian/tencent OK"
        else:
            status["tencent"]["detail"] = "返回空数据"
    except Exception as e:
        status["tencent"]["detail"] = str(e)[:100]

    return status
