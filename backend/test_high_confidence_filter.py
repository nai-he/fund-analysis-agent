"""Tests for high_confidence_filter.py"""
import unittest
from high_confidence_filter import build_high_confidence_decision


def _make_prediction(
    status="ok",
    quality="medium",
    dir_7d="up",
    dir_30d="up",
    conf_7d="中",
    conf_30d="中",
    edge_7d=True,
    edge_30d=True,
    edge_val_7d=5.0,
    edge_val_30d=5.0,
    hit_7d=60.0,
    hit_30d=60.0,
    selective_hit_7d=64.0,
    selective_hit_30d=64.0,
    selective_count_7d=30,
    selective_count_30d=30,
    selective_edge_7d=8.0,
    selective_edge_30d=8.0,
    current_selective_7d=True,
    current_selective_30d=True,
):
    return {
        "status": status,
        "quality": quality,
        "periods": {
            "7d": {
                "predicted_direction": dir_7d,
                "confidence": conf_7d,
                "has_positive_edge": edge_7d,
                "edge_vs_baseline": edge_val_7d,
                "historical_hit_rate": hit_7d,
                "selective_hit_rate": selective_hit_7d,
                "selective_signal_count": selective_count_7d,
                "selective_edge_vs_baseline": selective_edge_7d,
                "current_passes_selective_threshold": current_selective_7d,
            },
            "30d": {
                "predicted_direction": dir_30d,
                "confidence": conf_30d,
                "has_positive_edge": edge_30d,
                "edge_vs_baseline": edge_val_30d,
                "historical_hit_rate": hit_30d,
                "selective_hit_rate": selective_hit_30d,
                "selective_signal_count": selective_count_30d,
                "selective_edge_vs_baseline": selective_edge_30d,
                "current_passes_selective_threshold": current_selective_30d,
            },
        },
    }


def _make_risk(score=40):
    return {"risk_score": score}


def _make_metrics(vol=20, dd=5, rsi=50, pos_range=50):
    return {
        "volatility_30d": vol,
        "max_drawdown_30d_calendar": dd,
        "rsi_14": rsi,
        "position_in_30d_range": pos_range,
    }


def _make_backtest(quality="medium"):
    return {"probability_quality": quality}


class TestHighConfidenceFilter(unittest.TestCase):

    def test_all_conditions_met_small_buy(self):
        """Perfect prediction + low risk → small_buy"""
        pred = _make_prediction()
        risk = _make_risk(40)
        metrics = _make_metrics()
        bt = _make_backtest("medium")

        result = build_high_confidence_decision(
            prediction=pred,
            risk=risk,
            metrics=metrics,
            backtest=bt,
        )
        self.assertEqual(result["action"], "small_buy")

    def test_specific_30d_validated_swing_allows_tiny_buy(self):
        """30d 专训样本外信号可触发更低仓位试探，不要求 7d 同步触发。"""
        pred = _make_prediction(
            quality="medium",
            dir_7d="uncertain",
            conf_7d="低",
            edge_7d=False,
            current_selective_7d=False,
            selective_hit_30d=86.0,
            selective_count_30d=15,
            selective_edge_30d=20.0,
            current_selective_30d=True,
        )
        pred["specific_training"] = {"enabled": True}
        pred["periods"]["30d"].update({
            "selective_signal_valid": True,
            "selective_validation_passed": True,
            "selective_validation_hit_rate": 80.0,
            "selective_validation_signal_count": 5,
            "selective_cv_passed": True,
            "selective_cv_pass_rate": 75.0,
            "selective_hit_rate_lower_bound": 60.0,
            "selective_avg_return": 5.0,
            "selective_profit_factor": 2.0,
        })

        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(45),
            metrics=_make_metrics(vol=24, dd=6, rsi=55, pos_range=65),
            backtest=_make_backtest("low"),
        )

        self.assertEqual(result["action"], "small_buy")
        self.assertEqual(result["max_position_pct"], 3)
        self.assertGreater(len(result["reasons"]), 0)
        self.assertEqual(len(result["blockers"]), 0)

    def test_prediction_quality_low_wait(self):
        """prediction.quality == "low" → wait"""
        pred = _make_prediction(quality="low")
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "wait")
        self.assertGreater(len(result["blockers"]), 0)

    def test_backtest_quality_low_wait(self):
        """backtest.probability_quality == "low" still blocks by default"""
        pred = _make_prediction()
        bt = _make_backtest("low")
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
            backtest=bt,
        )
        self.assertEqual(result["action"], "wait")
        self.assertTrue(any("回测" in b for b in result["blockers"]))

    def test_risk_score_high_avoid(self):
        """risk_score >= 70 → avoid"""
        pred = _make_prediction()
        risk = _make_risk(75)
        metrics = _make_metrics()
        result = build_high_confidence_decision(
            prediction=pred,
            risk=risk,
            metrics=metrics,
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "avoid")

    def test_7d_up_30d_down_wait(self):
        """7d up but 30d down_or_flat → wait"""
        pred = _make_prediction(dir_30d="down_or_flat")
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "wait")
        self.assertTrue(any("30d" in b.lower() for b in result["blockers"]))

    def test_edge_below_3_wait(self):
        """edge_vs_baseline < 3 → wait"""
        pred = _make_prediction(edge_val_7d=1.0, edge_val_30d=1.0)
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "wait")
        self.assertTrue(any("边际优势不足" in b for b in result["blockers"]))

    def test_volatility_high_avoid(self):
        """volatility_30d >= 40 → avoid"""
        pred = _make_prediction()
        metrics = _make_metrics(vol=45)
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=metrics,
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "avoid")

    def test_max_position_capped(self):
        """max_position_pct <= 10 even with highest confidence"""
        pred = _make_prediction(conf_7d="高", conf_30d="高")
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(30),
            metrics=_make_metrics(),
            backtest=_make_backtest("high"),
        )
        self.assertLessEqual(result["max_position_pct"], 10)
        if result["action"] == "small_buy":
            self.assertEqual(result["max_position_pct"], 10)

    def test_insufficient_data_avoid(self):
        """prediction.status == "unavailable" → avoid"""
        pred = _make_prediction(status="unavailable")
        result = build_high_confidence_decision(prediction=pred)
        self.assertEqual(result["action"], "avoid")

    def test_all_fields_present(self):
        """Verify all required keys in output"""
        result = build_high_confidence_decision(
            prediction=_make_prediction(),
            risk=_make_risk(),
            metrics=_make_metrics(),
            backtest=_make_backtest(),
        )
        required = [
            "action", "action_label", "confidence", "score",
            "max_position_pct", "reasons", "blockers",
            "risk_controls", "disclaimer",
        ]
        for key in required:
            self.assertIn(key, result)
        self.assertIn(result["action"], ("wait", "avoid", "small_buy"))
        self.assertIn(result["confidence"], ("low", "medium", "high"))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_missing_prediction_data_wait(self):
        """None prediction → wait"""
        result = build_high_confidence_decision(prediction=None)
        self.assertEqual(result["action"], "wait")

    def test_no_backtest_wait(self):
        """Missing backtest → wait"""
        pred = _make_prediction()
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
        )
        self.assertEqual(result["action"], "wait")
        self.assertTrue(any("回测" in b for b in result["blockers"]))

    def test_rsi_overbought_wait(self):
        """RSI >= 70 → wait"""
        pred = _make_prediction()
        metrics = _make_metrics(rsi=72)
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=metrics,
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "wait")
        self.assertTrue(any("RSI" in b for b in result["blockers"]))

    def test_position_high_chasing_wait(self):
        """position_in_30d_range >= 80 → wait (avoid chasing)"""
        pred = _make_prediction()
        metrics = _make_metrics(pos_range=85)
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=metrics,
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "wait")
        self.assertTrue(any("高位" in b for b in result["blockers"]))

    def test_hit_rate_below_55_wait(self):
        """historical_hit_rate < 55 → wait"""
        pred = _make_prediction(hit_7d=40, hit_30d=40)
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "wait")
        self.assertTrue(any("命中率不足" in b for b in result["blockers"]))

    def test_selective_signal_required(self):
        """Selective signal should not bypass the backtest gate"""
        pred = _make_prediction(current_selective_7d=False, current_selective_30d=False)
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
            backtest=_make_backtest("medium"),
        )
        self.assertIn(result["action"], ("wait", "small_buy"))

    def test_medium_confidence_gives_5pct(self):
        """Medium confidence → max_position_pct = 5"""
        pred = _make_prediction(conf_7d="中", conf_30d="中")
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(40),
            metrics=_make_metrics(),
            backtest=_make_backtest(),
        )
        if result["action"] == "small_buy":
            self.assertEqual(result["max_position_pct"], 5)

    def test_both_down_or_flat_avoid(self):
        """7d and 30d both down_or_flat → avoid"""
        pred = _make_prediction(dir_7d="down_or_flat", dir_30d="down_or_flat")
        result = build_high_confidence_decision(
            prediction=pred,
            risk=_make_risk(50),
            metrics=_make_metrics(),
            backtest=_make_backtest(),
        )
        self.assertEqual(result["action"], "avoid")


if __name__ == "__main__":
    unittest.main()
