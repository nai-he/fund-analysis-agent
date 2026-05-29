"""
基金画像模块
获取基金详细信息：类型、规模、经理、费率、风险等级、排名等
获取不到的内容返回 "unavailable"，前端区分"未知"和"不可用"
"""
import logging
from typing import Dict, Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

FIELD_UNAVAILABLE = "unavailable"
FIELD_UNKNOWN = "未知"


def get_fund_profile(code: str) -> Dict[str, Any]:
    """
    获取基金完整画像
    返回 dict，所有字段获取不到时为 "unavailable"
    """
    profile = {
        "fund_type": FIELD_UNAVAILABLE,
        "fund_company": FIELD_UNAVAILABLE,
        "fund_manager": FIELD_UNAVAILABLE,
        "inception_date": FIELD_UNAVAILABLE,
        "fund_size": FIELD_UNAVAILABLE,
        "tracking_index": FIELD_UNAVAILABLE,
        "purchase_status": FIELD_UNAVAILABLE,
        "redeem_status": FIELD_UNAVAILABLE,
        "management_fee": FIELD_UNAVAILABLE,
        "custody_fee": FIELD_UNAVAILABLE,
        "sales_service_fee": FIELD_UNAVAILABLE,
        "risk_level": FIELD_UNAVAILABLE,
        "return_1y": FIELD_UNAVAILABLE,
        "peer_ranking": FIELD_UNAVAILABLE,
        "data_quality": "partial",
    }

    # 从 fund_name_em 获取类型信息
    try:
        import akshare as ak
        all_funds = ak.fund_name_em()
        matched = all_funds[all_funds["基金代码"] == code]
        if not matched.empty:
            row = matched.iloc[0]
            profile["fund_type"] = str(row.get("基金类型", FIELD_UNAVAILABLE))
            logger.info(f"[profile] fund_name_em type={profile['fund_type']}")
    except Exception as e:
        logger.warning(f"[profile] fund_name_em 失败: {e}")

    # 从雪球获取详细信息
    try:
        xq_profile = _get_xq_profile(code)
        if xq_profile:
            _merge_xq_profile(profile, xq_profile)
    except Exception as e:
        logger.warning(f"[profile] 雪球数据获取失败: {e}")

    # 从天天基金获取补充信息
    try:
        tt_profile = _get_tiantian_profile(code)
        if tt_profile:
            _merge_tt_profile(profile, tt_profile)
    except Exception as e:
        logger.warning(f"[profile] 天天基金数据获取失败: {e}")

    # 补充近1年收益和排名
    try:
        y1_data = _get_fund_return_1y(code)
        if y1_data:
            profile["return_1y"] = y1_data.get("return_1y", FIELD_UNAVAILABLE)
            profile["peer_ranking"] = y1_data.get("peer_ranking", FIELD_UNAVAILABLE)
    except Exception as e:
        logger.warning(f"[profile] 近1年收益获取失败: {e}")

    # 标记数据质量
    available_count = sum(1 for v in profile.values() if v != FIELD_UNAVAILABLE and v != FIELD_UNKNOWN)
    total_fields = len([k for k in profile if k != "data_quality"])
    if available_count >= total_fields * 0.7:
        profile["data_quality"] = "good"
    elif available_count >= total_fields * 0.3:
        profile["data_quality"] = "partial"
    else:
        profile["data_quality"] = "limited"

    logger.info(f"[profile] 基金画像获取完成: {code}, quality={profile['data_quality']}, available={available_count}/{total_fields}")
    return profile


def _get_xq_profile(code: str) -> Optional[Dict[str, Any]]:
    """从雪球获取基金详细信息"""
    try:
        import akshare as ak
        info = ak.fund_individual_basic_info_xq(symbol=code)
        if info is None:
            return None
        result = {}
        if "item" in info.columns and "value" in info.columns:
            for _, row in info.iterrows():
                key = str(row["item"]).strip()
                val = str(row["value"]).strip() if pd.notna(row["value"]) else ""
                result[key] = val
        return result
    except Exception:
        return None


def _merge_xq_profile(profile: Dict, xq: Dict) -> None:
    """将雪球数据合并到 profile"""
    field_map = {
        "基金简称": "fund_name",
        "基金全称": "fund_full_name",
        "基金类型": "fund_type",
        "基金公司": "fund_company",
        "基金管理人": "fund_company",
        "基金经理": "fund_manager",
        "成立日期": "inception_date",
        "成立日": "inception_date",
        "基金规模": "fund_size",
        "资产规模": "fund_size",
        "跟踪标的": "tracking_index",
        "跟踪指数": "tracking_index",
        "业绩比较基准": "tracking_index",
        "管理费率": "management_fee",
        "管理费": "management_fee",
        "托管费率": "custody_fee",
        "托管费": "custody_fee",
        "销售服务费": "sales_service_fee",
        "风险等级": "risk_level",
        "申购状态": "purchase_status",
        "赎回状态": "redeem_status",
    }

    for xq_key, profile_key in field_map.items():
        for k, v in xq.items():
            if xq_key in k or k in xq_key:
                val = str(v).strip()
                if val and val not in ("nan", "<NA>", "None", ""):
                    if profile_key in profile and profile[profile_key] in (FIELD_UNAVAILABLE, FIELD_UNKNOWN):
                        profile[profile_key] = val
                    elif profile_key not in profile:
                        pass
                break


def _get_tiantian_profile(code: str) -> Optional[Dict[str, Any]]:
    """从天天基金获取补充信息"""
    try:
        from providers.tencent_fund import get_tencent_nav_estimate
        est = get_tencent_nav_estimate(code)
        if est:
            return {
                "fund_name": est.get("name"),
                "nav_date": est.get("nav_date"),
                "latest_nav": est.get("unit_nav"),
            }
    except Exception:
        pass
    return None


def _merge_tt_profile(profile: Dict, tt: Dict) -> None:
    """将天天基金数据合并到 profile"""
    pass  # 天天基金只提供基本估值，profile 所需字段由其他来源获取


def _get_fund_return_1y(code: str) -> Optional[Dict[str, Any]]:
    """获取基金近1年收益和同类排名"""
    result = {"return_1y": FIELD_UNAVAILABLE, "peer_ranking": FIELD_UNAVAILABLE}
    try:
        import akshare as ak
        # 尝试 fund_rank_em 获取排名
        rank_df = ak.fund_open_fund_rank_em(symbol="开放式基金")
        if rank_df is not None and not rank_df.empty:
            # 查找代码
            code_col = None
            for col in rank_df.columns:
                if "代码" in str(col):
                    code_col = col
                    break
            if code_col:
                matched = rank_df[rank_df[code_col].astype(str) == code]
                if not matched.empty:
                    row = matched.iloc[0]
                    # 尝试获取近1年收益
                    for col in rank_df.columns:
                        col_str = str(col)
                        if "近一年" in col_str or "近1年" in col_str or "今年以来" in col_str:
                            val = row.get(col)
                            if val is not None and pd.notna(val):
                                result["return_1y"] = f"{val}%"
                                break
    except Exception as e:
        logger.warning(f"[profile] 排名/收益获取失败: {e}")

    # Fallback: 用近一年净值计算
    if result["return_1y"] == FIELD_UNAVAILABLE:
        try:
            import akshare as ak
            nav_df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            if nav_df is not None and not nav_df.empty:
                from fund_data import _normalize_nav_df
                nav_df = _normalize_nav_df(nav_df, source="akshare")
                if nav_df is not None and not nav_df.empty and "单位净值" in nav_df.columns:
                    nav_df = nav_df.sort_values("净值日期", ascending=True)
                    if len(nav_df) >= 250:
                        year_ago = nav_df.iloc[-250]
                        latest = nav_df.iloc[-1]
                        y1_return = (float(latest["单位净值"]) - float(year_ago["单位净值"])) / float(year_ago["单位净值"]) * 100
                        result["return_1y"] = f"{round(y1_return, 2)}%"
        except Exception:
            pass

    return result


def get_short_profile(code: str) -> Dict[str, str]:
    """获取基金简要画像（用于快速展示）"""
    full = get_fund_profile(code)
    return {
        "type": full.get("fund_type", FIELD_UNAVAILABLE),
        "company": full.get("fund_company", FIELD_UNAVAILABLE),
        "manager": full.get("fund_manager", FIELD_UNAVAILABLE),
        "size": full.get("fund_size", FIELD_UNAVAILABLE),
        "risk_level": full.get("risk_level", FIELD_UNAVAILABLE),
        "return_1y": full.get("return_1y", FIELD_UNAVAILABLE),
    }
