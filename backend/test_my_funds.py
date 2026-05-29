"""
my-funds 模块测试
覆盖：CRUD、文件读写校验、坏 JSON 备份、原子写入、去重
"""
import json
import os
import sys
import shutil
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from fastapi.testclient import TestClient

from main import app
from storage import USER_FUNDS_FILE, load_user_funds, save_user_funds

client = TestClient(app)

# ── 备份 / 恢复 ──────────────────────────────────────────────
_ORIGINAL_EXISTED = False
_BACKUP_PATH = USER_FUNDS_FILE + ".test_backup"


def setUpModule():
    global _ORIGINAL_EXISTED
    if os.path.exists(USER_FUNDS_FILE):
        _ORIGINAL_EXISTED = True
        shutil.copy2(USER_FUNDS_FILE, _BACKUP_PATH)
        os.remove(USER_FUNDS_FILE)


def tearDownModule():
    if os.path.exists(USER_FUNDS_FILE):
        os.remove(USER_FUNDS_FILE)
    for suffix in [".tmp", ".bad"]:
        p = USER_FUNDS_FILE + suffix
        if os.path.exists(p):
            os.remove(p)
    if _ORIGINAL_EXISTED and os.path.exists(_BACKUP_PATH):
        shutil.move(_BACKUP_PATH, USER_FUNDS_FILE)
    elif os.path.exists(_BACKUP_PATH):
        os.remove(_BACKUP_PATH)


def _clean_state():
    for p in [USER_FUNDS_FILE, USER_FUNDS_FILE + ".tmp", USER_FUNDS_FILE + ".bad"]:
        if os.path.exists(p):
            os.remove(p)


# ── 低级函数测试 ──────────────────────────────────────────────

class TestLoadUserFunds(unittest.TestCase):
    def setUp(self):
        _clean_state()

    def test_empty_file(self):
        self.assertEqual(load_user_funds(), [])

    def test_bad_json_backs_up(self):
        bad_json = b'this is not json {{{'
        with open(USER_FUNDS_FILE, "wb") as f:
            f.write(bad_json)

        result = load_user_funds()
        self.assertEqual(result, [])
        self.assertTrue(os.path.exists(USER_FUNDS_FILE + ".bad"))

        with open(USER_FUNDS_FILE + ".bad", "rb") as f:
            self.assertEqual(f.read(), bad_json)

    def test_wrong_structure(self):
        with open(USER_FUNDS_FILE, "w", encoding="utf-8") as f:
            json.dump([{"code": "161725"}], f)

        result = load_user_funds()
        self.assertEqual(result, [])

    def test_skips_non_dict_items(self):
        data = {"funds": [{"code": "161725"}, "not_a_dict", 123, None, {"code": "110022"}]}
        with open(USER_FUNDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        result = load_user_funds()
        codes = [r["code"] for r in result]
        self.assertEqual(codes, ["161725", "110022"])

    def test_skips_invalid_codes(self):
        data = {"funds": [
            {"code": "161725"},
            {"code": ""},
            {"code": "abc"},
            {"code": "123"},
            {"code": "1234567"},
            {"code": "110022"},
            {},
        ]}
        with open(USER_FUNDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        result = load_user_funds()
        codes = [r["code"] for r in result]
        self.assertEqual(codes, ["161725", "110022"])

    def test_dedup_by_code_last_wins(self):
        data = {"funds": [
            {"code": "161725", "note": "first"},
            {"code": "110022", "note": "first"},
            {"code": "161725", "note": "second"},
        ]}
        with open(USER_FUNDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        result = load_user_funds()
        codes = [r["code"] for r in result]
        self.assertEqual(len(codes), 2)
        self.assertIn("161725", codes)
        self.assertIn("110022", codes)
        for r in result:
            if r["code"] == "161725":
                self.assertEqual(r["note"], "second")
            if r["code"] == "110022":
                self.assertEqual(r["note"], "first")


class TestSaveUserFunds(unittest.TestCase):
    def setUp(self):
        _clean_state()

    def test_roundtrip(self):
        funds = [
            {"code": "161725", "holding_amount": 10000},
            {"code": "110022", "note": "测试"},
        ]
        save_user_funds(funds)
        self.assertTrue(os.path.exists(USER_FUNDS_FILE))
        self.assertFalse(os.path.exists(USER_FUNDS_FILE + ".tmp"))

        loaded = load_user_funds()
        self.assertEqual(len(loaded), 2)
        self.assertEqual({r["code"] for r in loaded}, {"161725", "110022"})
        for r in loaded:
            if r["code"] == "161725":
                self.assertEqual(r["holding_amount"], 10000)

    def test_cleans_codes(self):
        funds = [
            {"code": " 161725 "},
            {"code": 110022},
        ]
        save_user_funds(funds)
        loaded = load_user_funds()
        codes = [r["code"] for r in loaded]
        self.assertEqual(codes, ["161725", "110022"])

    def test_creates_dir(self):
        save_user_funds([{"code": "161725"}])
        self.assertTrue(os.path.exists(USER_FUNDS_FILE))


# ── API CRUD 测试 ──────────────────────────────────────────────

class TestMyFundsCRUD(unittest.TestCase):
    def setUp(self):
        _clean_state()

    def test_get_empty(self):
        resp = client.get("/api/my-funds")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["funds"], [])
        self.assertEqual(data["count"], 0)

    def test_post_create(self):
        resp = client.post("/api/my-funds", json={"code": "161725", "holding_amount": 5000})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["code"], "161725")
        self.assertEqual(data["count"], 1)

        loaded = load_user_funds()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["code"], "161725")
        self.assertEqual(loaded[0]["holding_amount"], 5000)

    def test_post_update(self):
        client.post("/api/my-funds", json={"code": "161725", "note": "old"})
        resp = client.post("/api/my-funds", json={"code": "161725", "note": "new", "holding_amount": 999})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 1)

        loaded = load_user_funds()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["note"], "new")
        self.assertEqual(loaded[0]["holding_amount"], 999)

    def test_post_invalid_code(self):
        for bad_code in ["", "abc", "12", "1234567"]:
            resp = client.post("/api/my-funds", json={"code": bad_code})
            self.assertEqual(resp.status_code, 422, f"code={bad_code!r}")

    def test_delete(self):
        client.post("/api/my-funds", json={"code": "161725"})
        client.post("/api/my-funds", json={"code": "110022"})

        resp = client.delete("/api/my-funds/161725")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 1)

        loaded = load_user_funds()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["code"], "110022")

    def test_delete_nonexistent(self):
        resp = client.delete("/api/my-funds/161725")
        self.assertEqual(resp.status_code, 404)

    def test_delete_invalid_code(self):
        resp = client.delete("/api/my-funds/abc")
        self.assertEqual(resp.status_code, 422)


# ── 批量分析测试 ──────────────────────────────────────────────

# Mock 数据生成（用于批量分析测试，避免网络请求）
def _make_mock_nav_df(n_days=200):
    """生成模拟净值 DataFrame"""
    import numpy as np
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n_days, freq='D')
    np.random.seed(42)
    returns = np.random.normal(0, 0.02, n_days)
    navs = [1.0]
    for r in returns[1:]:
        navs.append(navs[-1] * (1 + r))
    return pd.DataFrame({"净值日期": dates, "单位净值": [round(v, 4) for v in navs]})

_mock_fund_info = {"code": "161725", "name": "招商中证白酒指数(LOF)", "type": "指数型-股票", "company": "招商基金", "source": "mock"}
_mock_profile = {
    "fund_type": "指数型-股票", "fund_company": "招商基金", "fund_manager": "侯昊",
    "inception_date": "2015-05-27", "fund_size": "765.44亿元", "tracking_index": "中证白酒指数",
    "purchase_status": "开放申购", "redeem_status": "开放赎回",
    "management_fee": "1.00%", "custody_fee": "0.22%",
    "risk_level": "R4", "return_1y": "-8.56%", "peer_ranking": "612|1249", "data_quality": "good",
}
_mock_macro = {
    "status": "ok", "summary": "市场震荡", "macro_summary": {
        "risk_appetite": "neutral", "overseas_direction": "mixed",
        "forex_pressure": "moderate", "commodity_disturbance": "low",
    },
    "risk_factors": ["海外不确定性"], "global_indices": [], "forex": [], "commodities": [], "as_of": "2026-05-29",
}
_mock_ds_status = {"akshare": {"available": True, "detail": "ok"}, "efinance": {"available": False, "detail": "skip"}, "tencent": {"available": True, "detail": "ok"}}
_mock_llm_result = {
    "conclusion": "中性", "summary_7d": "短线震荡", "summary_30d": "中期偏弱",
    "summary_90d": "长期不确定", "risk_explanation": "波动率适中",
    "position_advice": "无持仓信息", "main_risks": ["市场波动"],
    "watch_points": ["关注均线"], "buy_conditions": ["回调至支撑位"],
    "reduce_conditions": ["跌破60日均线"], "confidence": "中",
    "data_basis": "200天数据", "disclaimer": "不构成投资建议",
}


class TestBatchAnalyze(unittest.TestCase):
    def setUp(self):
        _clean_state()

    def test_empty(self):
        resp = client.post("/api/my-funds/analyze")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["results"], [])

    @mock.patch("main.get_fund_info", return_value=_mock_fund_info)
    @mock.patch("main.get_fund_profile", return_value=_mock_profile)
    @mock.patch("main.get_fund_nav_history", return_value=_make_mock_nav_df())
    @mock.patch("main.get_macro_factors", return_value=_mock_macro)
    @mock.patch("main.get_tencent_nav_estimate", return_value=None)
    @mock.patch("main.analyze_with_llm", return_value=_mock_llm_result)
    @mock.patch("main.get_datasource_status", return_value=_mock_ds_status)
    def test_missing_code(self, *mocks):
        # load_user_funds 会过滤无有效 code 的项，所以只有 161725 进入批量分析
        save_user_funds([
            {"holding_amount": 100},
            {"code": "161725", "holding_amount": 5000},
        ])
        resp = client.post("/api/my-funds/analyze")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # 无 code 的项在 load_user_funds 阶段已被过滤
        self.assertEqual(data["total"], 1)
        self.assertTrue(data["results"][0]["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
