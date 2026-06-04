"""
测试"预测下跌"方向的准确率
- 从回测的 confusion_matrix 提取：预测 down → 实际 down 的 precision / recall / F1
- 覆盖多种基金类型（宽基、行业、债券、QDII、商品）
"""
import json
import pandas as pd
from fund_data import get_fund_info, get_fund_nav_history
from backtest_engine import run_backtest

codes = [
    # 宽基指数
    "510300",  # 沪深300ETF
    "510500",  # 中证500ETF
    "159915",  # 创业板ETF
    "588000",  # 科创50ETF
    # 行业指数
    "161725",  # 白酒LOF
    "512800",  # 银行ETF
    "159949",  # 创业板50
    "512880",  # 证券ETF
    # QDII
    "161128",  # 标普科技QDII
    "164906",  # 中概互联QDII
    "513100",  # 纳指100ETF
    # 债券/固收
    "000217",  # 华安黄金易ETF联接C
    "001595",  # 中融银行ETF联接C
    "000471",  # 富国城镇发展股票
    # 混合/主动
    "110022",  # 易方达消费行业
    "260108",  # 景顺长城新兴成长
    "519674",  # 银河创新成长
    "163406",  # 兴全合润混合
    "005827",  # 易方达蓝筹精选混合
]

results = []

for code in codes:
    item = {"code": code}
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
        item["name"] = info.get("name")
        item["type"] = info.get("type")
        item["nav_rows"] = len(nav)
        item["bt_quality"] = bt.get("probability_quality", "low")

        # 提取每个周期的"预测下跌"指标
        periods_out = {}
        for key in ["1d", "3d", "7d", "30d"]:
            p = (bt.get("periods") or {}).get(key)
            if not p:
                continue
            cm = p.get("confusion_matrix", {})
            if not cm:
                continue

            # confusion_matrix[预测][实际]
            # 预测"down"
            dp = cm.get("down", {})
            tp_down = dp.get("down", 0)       # 预测跌，实际跌
            fp_up = dp.get("up", 0)            # 预测跌，实际涨
            fp_sideways = dp.get("sideways", 0)  # 预测跌，实际震荡

            total_pred_down = tp_down + fp_up + fp_sideways

            # 实际跌但预测不是跌的
            fn_down = (cm.get("up", {}).get("down", 0)
                       + cm.get("sideways", {}).get("down", 0))

            # Precision: 预测跌中实际跌的比例
            precision_down = round(tp_down / total_pred_down * 100, 1) if total_pred_down > 0 else None

            # Recall: 实际跌中被预测出来的比例
            total_actual_down = tp_down + fn_down
            recall_down = round(tp_down / total_actual_down * 100, 1) if total_actual_down > 0 else None

            # F1
            if precision_down and recall_down and (precision_down + recall_down) > 0:
                f1_down = round(2 * precision_down * recall_down / (precision_down + recall_down), 1)
            else:
                f1_down = None

            # 整体方向准确率
            n = p.get("sample_size", 0)
            dir_acc = p.get("directional_accuracy")

            # 预测次数分布
            periods_out[key] = {
                "total_samples": n,
                "directional_accuracy": dir_acc,
                "pred_down_count": total_pred_down,
                "pred_down_pct": round(total_pred_down / n * 100, 1) if n > 0 else None,
                "precision_down": precision_down,
                "recall_down": recall_down,
                "f1_down": f1_down,
                "actual_down_pct": p.get("actual_distribution", {}).get("down_pct"),
            }

        item["periods"] = periods_out

    except Exception as e:
        item["error"] = str(e)

    results.append(item)

# 汇总统计
print("=" * 80)
print("预测下跌方向准确率 — 近一年 walk-forward 回测")
print("=" * 80)

for horizon in ["7d", "30d"]:
    precisions = []
    recalls = []
    f1s = []
    for r in results:
        p = (r.get("periods") or {}).get(horizon)
        if p and p.get("precision_down") is not None:
            precisions.append(p["precision_down"])
            recalls.append(p["recall_down"] if p.get("recall_down") is not None else 0)
            if p.get("f1_down") is not None:
                f1s.append(p["f1_down"])

    print(f"\n--- {horizon} period ---")
    print(f"Funds with down predictions: {len(precisions)} / {len(results)}")
    if precisions:
        print(f"Precision(pred down -> actual down) mean: {sum(precisions)/len(precisions):.1f}%")
        print(f"Recall(actual down -> predicted) mean: {sum(recalls)/len(recalls):.1f}%")
        print(f"F1 mean: {sum(f1s)/len(f1s):.1f}%" if f1s else "F1: N/A")

print(f"\n{'=' * 80}")
print("Per-fund detail (7d / 30d)")
print(f"{'Fund Name':<28s} {'Type':<16s} {'7d Prec':>9s} {'7d F1':>7s} {'30d Prec':>9s} {'30d F1':>7s}")
print("-" * 90)

for r in results:
    name = (r.get("name") or r["code"])[:27]
    ftype = (r.get("type") or "N/A")[:15]

    p7 = (r.get("periods") or {}).get("7d", {})
    p30 = (r.get("periods") or {}).get("30d", {})

    p7_prec = f"{p7['precision_down']}%" if p7.get("precision_down") is not None else "no_pred"
    p7_f1 = f"{p7['f1_down']}%" if p7.get("f1_down") is not None else "N/A"
    p30_prec = f"{p30['precision_down']}%" if p30.get("precision_down") is not None else "no_pred"
    p30_f1 = f"{p30['f1_down']}%" if p30.get("f1_down") is not None else "N/A"

    print(f"{name:<28s} {ftype:<16s} {p7_prec:>9s} {p7_f1:>7s} {p30_prec:>9s} {p30_f1:>7s}")

# Save full JSON
print(f"\nFull JSON output below")
print(json.dumps({
    "summary": {
        "total": len(results),
        "success": sum(1 for r in results if "error" not in r),
        "failed": sum(1 for r in results if "error" in r),
    },
    "results": results,
}, ensure_ascii=False, indent=2, default=str))
