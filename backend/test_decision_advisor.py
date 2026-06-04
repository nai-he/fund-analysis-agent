"""Tests for the rule-based decision advisor."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from decision_advisor import build_decision_advice


def _forecast(
    direction_7d="震荡",
    direction_30d="震荡",
    quality="medium",
    calibrated=True,
):
    return {
        "forecast_7d": {"direction": direction_7d, "rise_fall": ""},
        "forecast_30d": {"direction": direction_30d, "rise_fall": ""},
        "validation": {
            "probability_quality": quality,
            "is_calibrated": calibrated,
        },
    }


class TestDecisionAdvisor(unittest.TestCase):
    def test_planned_amount_small_trial_with_low_quality(self):
        result = build_decision_advice(
            fund={"name": "测试基金"},
            metrics={"latest_nav": 1.0},
            risk={"risk_score": 65},
            forecast=_forecast(quality="low", calibrated=False),
            position={"planned_buy_amount": 10000},
        )

        self.assertEqual(result["action"], "small_trial")
        self.assertEqual(result["confidence"], "低")
        self.assertEqual(result["suggested_buy_pct"], 15)
        self.assertEqual(result["suggested_buy_amount"], 1500)
        self.assertTrue(any("回测未证明" in r for r in result["reasons"]))

    def test_holding_units_count_as_existing_position(self):
        result = build_decision_advice(
            fund={"name": "测试基金"},
            metrics={"latest_nav": 1.0},
            risk={"risk_score": 80},
            forecast=_forecast(quality="medium", calibrated=True),
            position={"holding_units": 1000},
        )

        self.assertEqual(result["action"], "reduce")
        self.assertEqual(result["action_label"], "降低仓位")

    def test_up_direction_substring_enables_batch_attention(self):
        result = build_decision_advice(
            fund={"name": "测试基金"},
            metrics={"latest_nav": 1.0},
            risk={"risk_score": 40},
            forecast=_forecast(
                direction_7d="偏上行",
                direction_30d="偏上行",
                quality="medium",
                calibrated=True,
            ),
            position={"planned_buy_amount": 9000},
        )

        self.assertEqual(result["action"], "batch_buy")
        self.assertEqual(result["action_label"], "分批关注")
        self.assertEqual(result["suggested_buy_pct"], 33)
        self.assertEqual(result["suggested_buy_amount"], 2970)

    def test_down_direction_substring_prefers_observe_when_risk_is_elevated(self):
        result = build_decision_advice(
            fund={"name": "测试基金"},
            metrics={"latest_nav": 1.0},
            risk={"risk_score": 58},
            forecast=_forecast(
                direction_7d="偏下行",
                direction_30d="震荡",
                quality="medium",
                calibrated=True,
            ),
            position={"planned_buy_amount": 10000},
        )

        self.assertEqual(result["action"], "observe")
        self.assertEqual(result["suggested_buy_amount"], 0)

    def test_missing_validation_is_low_confidence_by_default(self):
        result = build_decision_advice(
            fund={"name": "测试基金"},
            metrics={"latest_nav": 1.0},
            risk={"risk_score": 45},
            forecast={"forecast_7d": {"direction": "震荡"}, "forecast_30d": {"direction": "震荡"}},
            position=None,
        )

        self.assertEqual(result["confidence"], "低")
        self.assertTrue(any("模型概率估计尚不稳定" in w for w in result["risk_warnings"]))

    def test_position_hint_near_max_loss(self):
        result = build_decision_advice(
            fund={"name": "测试基金"},
            metrics={"latest_nav": 0.86},
            risk={"risk_score": 50},
            forecast=_forecast(quality="medium", calibrated=True),
            position={"cost_nav": 1.0, "max_loss_percent": 15},
        )

        self.assertIn("已接近最大亏损线", result["position_hint"])
        self.assertTrue(result["sell_or_reduce_conditions"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
