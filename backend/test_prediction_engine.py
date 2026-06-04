"""Tests for binary up-probability prediction engine."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

from prediction_engine import generate_up_probability_prediction, is_specific_trained_fund


def make_nav_df(n_days=180, seed=7, drift=0.0005, vol=0.01):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n_days, freq="D")
    returns = rng.normal(drift, vol, n_days)
    navs = [1.0]
    for ret in returns[1:]:
        navs.append(navs[-1] * (1 + ret))
    df = pd.DataFrame({
        "净值日期": dates,
        "单位净值": [round(v, 4) for v in navs],
    })
    df["日增长率"] = df["单位净值"].pct_change() * 100
    return df


def make_external_factor_df(nav_df):
    dates = pd.to_datetime(nav_df["净值日期"])
    nav = pd.Series(nav_df["单位净值"].astype(float).values)
    factor_nav = nav.rolling(3, min_periods=1).mean() * 1.02
    return pd.DataFrame({
        "净值日期": dates,
        "factor_return_1d": factor_nav.pct_change(1) * 100,
        "factor_return_5d": factor_nav.pct_change(5) * 100,
        "factor_return_20d": factor_nav.pct_change(20) * 100,
        "factor_position_30d": 50.0,
        "factor_above_ma20": 1.0,
        "factor_volatility_20d": 12.0,
    })


class TestPredictionEngine(unittest.TestCase):
    def test_output_shape(self):
        result = generate_up_probability_prediction(make_nav_df(), horizons=[1, 3, 7, 30], min_samples=10)

        self.assertEqual(result["status"], "ok")
        self.assertIn(result["quality"], ("low", "medium", "high"))
        self.assertIn("periods", result)
        for key in ["1d", "3d", "7d", "30d"]:
            self.assertIn(key, result["periods"])
            period = result["periods"][key]
            self.assertIn("up_probability", period)
            self.assertIn("down_or_flat_probability", period)
            self.assertIn("selective_hit_rate", period)
            self.assertIn("selective_signal_count", period)
            self.assertIn("current_passes_selective_threshold", period)
            total = period["up_probability"] + period["down_or_flat_probability"]
            self.assertAlmostEqual(total, 100.0, delta=0.2)
            self.assertIn(period["predicted_direction"], ("up", "down_or_flat", "uncertain"))

    def test_insufficient_data(self):
        result = generate_up_probability_prediction(make_nav_df(n_days=30), horizons=[7], min_samples=10)

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["periods"], {})

    def test_random_walk_is_not_overclaimed(self):
        result = generate_up_probability_prediction(
            make_nav_df(n_days=160, seed=42, drift=0.0, vol=0.02),
            horizons=[1, 3, 7],
            min_samples=10,
        )

        self.assertEqual(result["status"], "ok")
        self.assertNotEqual(result["quality"], "high")
        for period in result["periods"].values():
            if not period.get("has_positive_edge"):
                self.assertEqual(period["confidence"], "低")
                self.assertEqual(period["predicted_direction"], "uncertain")
            if period["predicted_direction"] == "up":
                self.assertTrue(period["current_passes_selective_threshold"])
                self.assertGreaterEqual(period["selective_hit_rate"], 60)

    def test_deterministic(self):
        df = make_nav_df(n_days=180, seed=21, drift=0.0008, vol=0.012)
        result1 = generate_up_probability_prediction(df, horizons=[7], min_samples=10)
        result2 = generate_up_probability_prediction(df, horizons=[7], min_samples=10)

        self.assertEqual(result1["periods"]["7d"]["up_probability"], result2["periods"]["7d"]["up_probability"])
        self.assertEqual(result1["periods"]["7d"]["edge_vs_baseline"], result2["periods"]["7d"]["edge_vs_baseline"])

    def test_specific_fund_training_metadata(self):
        result = generate_up_probability_prediction(
            make_nav_df(n_days=720, seed=33, drift=0.0004, vol=0.015),
            horizons=[7, 30],
            min_samples=20,
            fund_code="015566",
            fund_name="万家精选混合C",
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["model_basis"], "specific_fund_walk_forward_80_target")
        self.assertTrue(result["specific_training"]["enabled"])
        for period in result["periods"].values():
            self.assertEqual(period["selective_target_hit_rate"], 80.0)
            self.assertIn("selective_rule_text", period)
            self.assertIn("selective_profit_factor", period)
            self.assertIn("selective_hit_rate_lower_bound", period)
            self.assertIn("selective_train_hit_rate", period)
            self.assertIn("selective_train_passed", period)
            self.assertIn("selective_validation_hit_rate", period)
            self.assertIn("selective_validation_passed", period)
            self.assertIn("selective_cv_passed", period)
            self.assertIn("selective_cv_pass_rate", period)
            self.assertIn("selective_training_status", period)
            if period.get("current_passes_selective_threshold"):
                self.assertGreaterEqual(period["selective_hit_rate"], 80.0)
                self.assertTrue(period["selective_validation_passed"])
                self.assertTrue(period["selective_cv_passed"])

    def test_new_specific_fund_codes_enabled(self):
        for code in ["020872", "017811", "017516"]:
            self.assertTrue(is_specific_trained_fund(code))

    def test_specific_training_accepts_external_factors(self):
        nav_df = make_nav_df(n_days=360, seed=44, drift=0.0005, vol=0.014)
        factor_df = make_external_factor_df(nav_df)
        factor_meta = {
            "status": "available",
            "sources": [{
                "type": "latest_holding_stock_basket",
                "name": "测试股票篮子",
                "stock_count": 3,
                "holdings": ["测试A(000001)", "测试B(000002)", "测试C(000003)"],
            }],
            "note": "测试因子",
        }

        result = generate_up_probability_prediction(
            nav_df,
            horizons=[7],
            min_samples=20,
            fund_code="017811",
            fund_name="东方人工智能主题混合C",
            external_features=factor_df,
            external_factor_meta=factor_meta,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["specific_training"]["factor_status"], "available")
        self.assertEqual(result["specific_training"]["factor_sources"][0]["stock_count"], 3)
        self.assertIn("已纳入", result["summary"])

    def test_main_api_smoke_with_prediction(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from main import app

        mock_fund_info = {"code": "161725", "name": "测试基金", "type": "指数型", "company": "测试", "source": "mock"}
        mock_profile = {"fund_type": "指数型", "data_quality": "good"}
        mock_macro = {"status": "ok", "summary": "市场震荡", "macro_summary": {}, "risk_factors": []}
        mock_ds_status = {"akshare": {"available": True, "detail": "ok"}}
        mock_llm_result = {
            "conclusion": "中性",
            "summary_7d": "震荡",
            "summary_30d": "震荡",
            "summary_90d": "震荡",
            "risk_explanation": "风险中等",
            "confidence": "中",
            "disclaimer": "不构成投资建议",
        }

        with patch("main.get_fund_info", return_value=mock_fund_info), \
             patch("main.get_fund_profile", return_value=mock_profile), \
             patch("main.get_fund_nav_history", return_value=make_nav_df(n_days=180)), \
             patch("main.get_datasource_status", return_value=mock_ds_status), \
             patch("main.get_macro_factors", return_value=mock_macro), \
             patch("main.get_tencent_nav_estimate", return_value=None), \
             patch("main.analyze_with_llm", return_value=mock_llm_result):
            client = TestClient(app)
            resp = client.get("/api/analyze", params={"code": "161725"})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("prediction", data)
        self.assertEqual(data["prediction"]["status"], "ok")
        self.assertIn("7d", data["prediction"]["periods"])


if __name__ == "__main__":
    unittest.main()
