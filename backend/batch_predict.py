import json
import pandas as pd

from fund_data import get_fund_info, get_fund_nav_history
from backtest_engine import run_backtest
from prediction_engine import generate_up_probability_prediction

codes = [
    "161725", "110022", "163406", "260108", "519674",
    "320007", "001632", "040046", "000471", "001595",
    "003096", "005827", "008888", "006113", "159949",
    "000217", "001838", "217022", "161005", "000478"
]

def pick_period(bt, key):
    p = (bt.get("periods") or {}).get(key) or {}
    bc = p.get("baseline_comparison") or {}
    return {
        "sample_size": p.get("sample_size"),
        "directional_accuracy": p.get("directional_accuracy"),
        "best_baseline_acc": bc.get("best_baseline_acc"),
        "edge_vs_baseline": bc.get("rule_vs_best_baseline_edge"),
        "brier_score": p.get("brier_score"),
    }

def pick_pred(pred, key):
    p = (pred.get("periods") or {}).get(key) or {}
    return {
        "predicted_direction": p.get("predicted_direction"),
        "up_probability": p.get("up_probability"),
        "confidence": p.get("confidence"),
        "has_positive_edge": p.get("has_positive_edge"),
        "historical_hit_rate": p.get("historical_hit_rate"),
        "baseline_hit_rate": p.get("baseline_hit_rate"),
        "edge_vs_baseline": p.get("edge_vs_baseline"),
    }

results = []
summary = {
    "total": 0,
    "success": 0,
    "failed": 0,
    "backtest_quality": {"low": 0, "medium": 0, "high": 0},
    "prediction_quality": {"low": 0, "medium": 0, "high": 0},
}

for code in codes:
    item = {"code": code}
    summary["total"] += 1
    try:
        info = get_fund_info(code) or {}
        nav = get_fund_nav_history(code, days=365)
        if nav is None or nav.empty:
            raise RuntimeError("no nav data")

        if "净值日期" in nav.columns:
            nav = nav.sort_values("净值日期").copy()
            nav["净值日期"] = pd.to_datetime(nav["净值日期"], errors="coerce")
            nav = nav.dropna(subset=["净值日期"])
            if not nav.empty:
                cutoff = nav["净值日期"].max() - pd.Timedelta(days=365)
                nav = nav[nav["净值日期"] >= cutoff]

        bt = run_backtest(nav, horizons=[1, 3, 7, 30], min_samples=10)
        pred = generate_up_probability_prediction(nav, horizons=[1, 3, 7, 30], min_samples=20)

        btq = bt.get("probability_quality", "low")
        prq = pred.get("quality", "low")
        summary["success"] += 1
        summary["backtest_quality"][btq] = summary["backtest_quality"].get(btq, 0) + 1
        summary["prediction_quality"][prq] = summary["prediction_quality"].get(prq, 0) + 1

        item.update({
            "name": info.get("name"),
            "type": info.get("type"),
            "rows": len(nav),
            "backtest_quality": btq,
            "prediction_quality": prq,
            "backtest": {
                "1d": pick_period(bt, "1d"),
                "3d": pick_period(bt, "3d"),
                "7d": pick_period(bt, "7d"),
                "30d": pick_period(bt, "30d"),
            },
            "prediction": {
                "1d": pick_pred(pred, "1d"),
                "3d": pick_pred(pred, "3d"),
                "7d": pick_pred(pred, "7d"),
                "30d": pick_pred(pred, "30d"),
            },
        })
    except Exception as e:
        summary["failed"] += 1
        item["error"] = str(e)

    results.append(item)

print(json.dumps({
    "summary": summary,
    "results": results
}, ensure_ascii=False, indent=2, default=str))
