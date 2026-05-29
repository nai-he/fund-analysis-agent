"""File-based storage for user funds (user_funds.json)."""
import json
import logging
import os
import shutil
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from fastapi import HTTPException

USER_FUNDS_FILE = os.path.join(os.path.dirname(__file__), "user_funds.json")


def load_user_funds() -> List[dict]:
    """安全读取 user_funds.json，解析失败时返回空列表并备份坏文件

    读取后清洗：每条必须是 dict、code 必须为 5-6 位数字字符串、无效项跳过、相同 code 去重（后出现的覆盖前面的）
    """
    if not os.path.exists(USER_FUNDS_FILE):
        return []
    raw_items = None
    try:
        with open(USER_FUNDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("funds"), list):
            raw_items = data["funds"]
        else:
            logger.warning("user_funds.json 格式异常（非 {funds: [...]}），忽略")
            return []
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"user_funds.json 解析失败: {e}")
        backup_path = USER_FUNDS_FILE + ".bad"
        try:
            shutil.copy2(USER_FUNDS_FILE, backup_path)
            logger.warning(f"已备份坏文件至 {backup_path}")
        except Exception:
            pass
        return []

    # 清洗：过滤无效项 + 去重（后出现的覆盖前面的）
    seen: dict = {}
    for item in raw_items:
        if not isinstance(item, dict):
            logger.warning(f"跳过非 dict 项: {item}")
            continue
        code = str(item.get("code", "")).strip()
        if not code or not code.isdigit() or len(code) < 5 or len(code) > 6:
            logger.warning(f"跳过无效 code: {code}")
            continue
        item["code"] = code
        seen[code] = item  # 后出现的覆盖前面的

    return list(seen.values())


def save_user_funds(funds: List[dict]) -> None:
    """保存基金列表到 user_funds.json，原子写入，UTF-8 编码"""
    # 清洗 code
    for item in funds:
        item["code"] = str(item.get("code", "")).strip()
    # 确保目录存在
    os.makedirs(os.path.dirname(USER_FUNDS_FILE), exist_ok=True)
    tmp_path = USER_FUNDS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"funds": funds}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, USER_FUNDS_FILE)


def validate_fund_code(code: str) -> str:
    """校验并清洗基金代码，返回清洗后的 code，非法时抛出 HTTPException"""
    code = code.strip()
    if not code or not code.isdigit():
        raise HTTPException(status_code=422, detail="基金代码必须为纯数字")
    if len(code) < 5 or len(code) > 6:
        raise HTTPException(status_code=422, detail="基金代码长度为 5-6 位数字")
    return code
