"""
Tencent Finance / Tiantian Fund 数据提供器
适用于 ETF/LOF 实时报价，普通开放式基金仅返回日净值估算
数据来源：腾讯财经行情 + 天天基金估值
注意：仅适用于中国内地公募基金
"""
import json
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 使用 httpx 会话复用连接
_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=10.0, follow_redirects=True)
    return _client


# ---- ETF/LOF 实时行情 (Tencent) ----

def _resolve_exchange(code: str) -> str:
    """根据基金代码前缀推断交易所: sh (上海) 或 sz (深圳)"""
    if code.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


def get_tencent_fund_quote(code: str) -> Optional[dict]:
    """
    获取 ETF/LOF 实时报价 (Tencent 行情接口)
    适用于：ETF（如 510300）、LOF（如 161725）
    不适用于：普通开放式基金（无实时行情，见 get_tencent_nav_estimate）
    """
    try:
        exchange = _resolve_exchange(code)
        url = f"http://qt.gtimg.cn/q={exchange}{code}"
        resp = _get_client().get(url)
        resp.raise_for_status()
        text = resp.text

        if not text or "none" in text.lower():
            return None

        # 解析腾讯行情返回: v_sh510300="1~沪深300ETF~510300~3.850~..."
        # 标准格式用 ~ 分隔
        for line in text.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            value_part = line.split("=", 1)[1].strip().strip('"').strip("'")
            if not value_part or value_part == "":
                continue
            fields = value_part.split("~")
            if len(fields) < 10:
                continue

            name = fields[1] if len(fields) > 1 else ""
            current_price = _safe_float(fields[3])
            prev_close = _safe_float(fields[4])
            change_pct = None
            if prev_close and prev_close > 0 and current_price is not None:
                change_pct = round((current_price - prev_close) / prev_close * 100, 2)

            return {
                "code": code,
                "name": name,
                "price": current_price,
                "prev_close": prev_close,
                "change_pct": change_pct,
                "source": "tencent_quote",
                "scope": "ETF/LOF 实时行情",
            }
        return None
    except Exception as e:
        logger.warning(f"[tencent] 获取行情失败: {code}, error={e}")
        return None


def get_tencent_nav_estimate(code: str) -> Optional[dict]:
    """
    获取基金净值估算 (天天基金估值接口)
    适用于所有公募基金（含普通开放式基金）
    """
    try:
        url = f"http://fundgz.1234567.com.cn/js/{code}.js"
        resp = _get_client().get(url)
        resp.raise_for_status()
        text = resp.text

        # 格式: jsonpgz({"fundcode":"161725","name":"...","jzrq":"...","dwjz":"...","gsz":"...","gszzl":"...","gztime":"..."});
        match = re.search(r"jsonpgz\((.+)\)", text)
        if not match:
            return None
        data = json.loads(match.group(1))
        if not data or not data.get("name"):
            return None

        return {
            "code": data.get("fundcode", code),
            "name": data.get("name", ""),
            "nav_date": data.get("jzrq", ""),
            "unit_nav": _safe_float(data.get("dwjz")),
            "estimated_nav": _safe_float(data.get("gsz")),
            "estimated_change_pct": _safe_float(data.get("gszzl")),
            "estimate_time": data.get("gztime", ""),
            "source": "tiantian_nav",
            "scope": "净值估算（非实时）",
        }
    except Exception as e:
        logger.warning(f"[tencent] 获取净值估算失败: {code}, error={e}")
        return None


def get_tencent_fund_basic(code: str) -> Optional[dict]:
    """
    获取基金基本信息 (综合天天基金 + 腾讯)
    """
    # 先尝试天天基金净值接口（含名称和最新净值）
    nav = get_tencent_nav_estimate(code)
    if nav and nav.get("name"):
        result = {
            "code": code,
            "name": nav["name"],
            "type": "未知",
            "company": "未知",
            "latest_nav": nav.get("unit_nav"),
            "nav_date": nav.get("nav_date"),
            "source": "tiantian",
        }
        # 尝试从 Tencent 行情获取更多信息 (ETF/LOF)
        quote = get_tencent_fund_quote(code)
        if quote and quote.get("name"):
            result["name"] = quote["name"] or result["name"]
        return result

    # 腾讯行情作为 fallback
    quote = get_tencent_fund_quote(code)
    if quote and quote.get("name"):
        return {
            "code": code,
            "name": quote["name"],
            "type": "ETF/LOF（来自行情数据）",
            "company": "未知",
            "latest_nav": quote.get("price"),
            "source": "tencent_quote",
        }

    return None


def search_tencent_funds(keyword: str) -> list[dict]:
    """
    搜索基金 (东方财富基金搜索接口)
    返回匹配的基金列表
    """
    try:
        url = "http://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
        params = {"m": "1", "key": keyword}
        resp = _get_client().get(url, params=params)
        resp.raise_for_status()
        text = resp.text

        if not text:
            return []

        # 解析 JSONP 或 JSON
        if text.startswith("var "):
            text = text.split("=", 1)[1].strip() if "=" in text else text
        text = text.strip().rstrip(";")

        data = json.loads(text)
        results = []
        items = data.get("Datas", []) if isinstance(data, dict) else []
        for item in items[:20]:
            results.append({
                "code": item.get("CODE", ""),
                "name": item.get("NAME", ""),
                "type": item.get("FundType", ""),
                "pinyin": item.get("PINYIN", ""),
                "source": "eastmoney_search",
            })
        return results
    except Exception as e:
        logger.warning(f"[tencent] 搜索基金失败: {keyword}, error={e}")
        return []


def _safe_float(val) -> Optional[float]:
    """安全转换为 float"""
    if val is None:
        return None
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return None
