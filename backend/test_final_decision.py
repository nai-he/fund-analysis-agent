"""
Tests for final_decision.py — verify conservative aggregation rules.
"""
import unittest
from final_decision import build_final_decision, _build_headline, _safe_float, _has_position


class TestHelpers(unittest.TestCase):
    def test_safe_float_returns_value(self):
        self.assertEqual(_safe_float({"a": 50}, "a"), 50.0)

    def test_safe_float_returns_default_for_missing_key(self):
        self.assertIsNone(_safe_float({}, "a"))

    def test_safe_float_returns_default_for_none_dict(self):
        self.assertIsNone(_safe_float(None, "a"))

    def test_has_position_true(self):
        self.assertTrue(_has_position({"cost_nav": 1.5, "holding_amount": 1000}))

    def test_has_position_false_for_empty(self):
        self.assertFalse(_has_position({}))

    def test_has_position_false_for_none(self):
        self.assertFalse(_has_position(None))

    def test_headline_max_25_chars(self):
        for direction in ("up", "down", "neutral", "uncertain"):
            for action in ("buy_watch", "hold", "reduce", "observe", "avoid"):
                h = _build_headline(direction, action, 50)
                self.assertLessEqual(len(h), 25, f"headline too long: '{h}' ({len(h)} chars)")


class TestNoPredictionEdge(unittest.TestCase):
    """Test 1: No prediction edge → direction=uncertain, confidence=低"""

    def test_no_edge_both_low_confidence(self):
        prediction = {
            "quality": "low",
            "periods": {
                "7d": {
                    "up_probability": 48,
                    "has_positive_edge": False,
                    "confidence": "低",
                    "predicted_direction": "uncertain",
                },
                "30d": {
                    "up_probability": 49,
                    "has_positive_edge": False,
                    "confidence": "低",
                    "predicted_direction": "uncertain",
                },
            },
        }
        result = build_final_decision(
            fund=None, risk=None, forecast=None,
            prediction=prediction, decision_advice=None, position=None,
        )
        self.assertEqual(result["direction"], "uncertain")
        self.assertEqual(result["direction_label"], "不确定")
        self.assertEqual(result["confidence"], "低")

    def test_no_edge_low_quality(self):
        prediction = {
            "quality": "low",
            "periods": {
                "7d": {
                    "up_probability": 55,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
                "30d": {
                    "up_probability": 40,
                    "has_positive_edge": False,
                    "confidence": "低",
                    "predicted_direction": "down_or_flat",
                },
            },
        }
        result = build_final_decision(
            fund=None, risk=None, forecast=None,
            prediction=prediction, decision_advice=None, position=None,
        )
        self.assertEqual(result["direction"], "uncertain")
        self.assertEqual(result["confidence"], "低")


class TestBothUpLowRisk(unittest.TestCase):
    """Test 2: 7d+30d both up + low risk → direction=up"""

    def test_both_up_low_risk(self):
        prediction = {
            "quality": "medium",
            "periods": {
                "7d": {
                    "up_probability": 68,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
                "30d": {
                    "up_probability": 63,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
            },
        }
        risk = {"risk_score": 35}
        result = build_final_decision(
            fund={"code": "000001", "name": "测试基金"},
            risk=risk, forecast=None,
            prediction=prediction, decision_advice=None, position=None,
        )
        self.assertEqual(result["direction"], "up")
        self.assertEqual(result["direction_label"], "偏涨")
        self.assertIn(result["action"], ("buy_watch", "observe"))
        self.assertIsNotNone(result["headline"])

    def test_both_up_high_confidence(self):
        prediction = {
            "quality": "medium",
            "periods": {
                "7d": {
                    "up_probability": 72,
                    "has_positive_edge": True,
                    "confidence": "高",
                    "predicted_direction": "up",
                },
                "30d": {
                    "up_probability": 65,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
            },
        }
        risk = {"risk_score": 25}
        result = build_final_decision(
            fund=None, risk=risk, forecast=None,
            prediction=prediction, decision_advice=None, position=None,
        )
        self.assertEqual(result["direction"], "up")
        self.assertEqual(result["confidence"], "高")


class TestHighRiskWithPosition(unittest.TestCase):
    """Test 3: High risk + has position → action NOT buy_watch"""

    def test_high_risk_with_position_action_not_buy_watch(self):
        prediction = {
            "quality": "medium",
            "periods": {
                "7d": {
                    "up_probability": 65,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
                "30d": {
                    "up_probability": 60,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
            },
        }
        risk = {"risk_score": 80}
        position = {"cost_nav": 1.2, "holding_amount": 5000}
        result = build_final_decision(
            fund=None, risk=risk, forecast=None,
            prediction=prediction, decision_advice=None, position=position,
        )
        self.assertNotEqual(result["action"], "buy_watch")
        self.assertIn(result["action"], ("reduce", "hold", "observe", "avoid"))
        # With risk_score >= 70 and has_position, action should be "reduce"
        self.assertEqual(result["action"], "reduce")

    def test_high_risk_no_position_action_avoid(self):
        prediction = {
            "quality": "medium",
            "periods": {
                "7d": {
                    "up_probability": 65,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
                "30d": {
                    "up_probability": 60,
                    "has_positive_edge": True,
                    "confidence": "中",
                    "predicted_direction": "up",
                },
            },
        }
        risk = {"risk_score": 78}
        result = build_final_decision(
            fund=None, risk=risk, forecast=None,
            prediction=prediction, decision_advice=None, position=None,
        )
        self.assertEqual(result["action"], "avoid")
        self.assertEqual(result["action_label"], "暂不参与")


class TestRequiredOutputFields(unittest.TestCase):
    """Test 4: Output must have headline, why, warning, disclaimer"""

    def test_all_required_fields_present(self):
        result = build_final_decision(
            fund=None, risk={"risk_score": 50}, forecast=None,
            prediction={
                "quality": "medium",
                "periods": {
                    "7d": {
                        "up_probability": 55,
                        "has_positive_edge": False,
                        "confidence": "低",
                        "predicted_direction": "up",
                    },
                    "30d": {
                        "up_probability": 52,
                        "has_positive_edge": False,
                        "confidence": "低",
                        "predicted_direction": "up",
                    },
                },
            },
            decision_advice=None, position=None,
        )
        self.assertIn("headline", result)
        self.assertIsInstance(result["headline"], str)
        self.assertGreater(len(result["headline"]), 0)
        self.assertLessEqual(len(result["headline"]), 25)

        self.assertIn("why", result)
        self.assertIsInstance(result["why"], list)
        self.assertIn("warning", result)
        self.assertIsInstance(result["warning"], list)
        self.assertIn("disclaimer", result)
        self.assertIsInstance(result["disclaimer"], str)
        self.assertGreater(len(result["disclaimer"]), 0)

        self.assertIn("direction", result)
        self.assertIn(result["direction"], ("up", "down", "neutral", "uncertain"))
        self.assertIn("direction_label", result)
        self.assertIn("action", result)
        self.assertIn(result["action"], ("buy_watch", "hold", "reduce", "observe", "avoid"))
        self.assertIn("action_label", result)
        self.assertIn("confidence", result)
        self.assertIn(result["confidence"], ("低", "中", "高"))
        self.assertIn("up_probability_7d", result)
        self.assertIn("up_probability_30d", result)
        self.assertIn("risk_score", result)

    def test_why_not_empty_for_uncertain(self):
        result = build_final_decision(
            fund=None, risk=None, forecast=None,
            prediction={
                "quality": "low",
                "periods": {
                    "7d": {"up_probability": 50, "has_positive_edge": False, "confidence": "低", "predicted_direction": "uncertain"},
                    "30d": {"up_probability": 50, "has_positive_edge": False, "confidence": "低", "predicted_direction": "uncertain"},
                },
            },
            decision_advice=None, position=None,
        )
        self.assertGreater(len(result["why"]), 0, "why should have at least one reason")

    def test_disclaimer_is_conservative(self):
        result = build_final_decision(
            fund=None, risk=None, forecast=None,
            prediction={
                "quality": "high",
                "periods": {
                    "7d": {"up_probability": 80, "has_positive_edge": True, "confidence": "高", "predicted_direction": "up"},
                    "30d": {"up_probability": 75, "has_positive_edge": True, "confidence": "高", "predicted_direction": "up"},
                },
            },
            decision_advice=None, position=None,
        )
        self.assertIn("不构成投资建议", result["disclaimer"])


if __name__ == "__main__":
    unittest.main()
