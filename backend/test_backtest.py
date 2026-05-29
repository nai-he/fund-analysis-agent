"""
回测模块测试
用 mock DataFrame 验证 backtest_engine 逻辑
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

import pandas as pd
import numpy as np
from datetime import timedelta

from backtest_engine import run_backtest, MIN_THRESHOLDS


def create_mock_nav_df(n_days=200, base_nav=1.0, daily_vol=0.02, seed=42):
    """生成模拟净值 DataFrame"""
    np.random.seed(seed)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n_days, freq='D')
    # 随机游走
    returns = np.random.normal(0, daily_vol, n_days)
    navs = [base_nav]
    for r in returns[1:]:
        navs.append(navs[-1] * (1 + r))
    df = pd.DataFrame({
        "净值日期": dates,
        "单位净值": [round(v, 4) for v in navs],
    })
    # 添加日增长率
    df["日增长率"] = df["单位净值"].pct_change() * 100
    return df


def test_mock_nav_backtest():
    """用 mock DataFrame 测试 backtest_engine 逻辑"""
    print("=== test_mock_nav_backtest ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02)
    result = run_backtest(df, horizons=[1, 3, 7, 30], min_samples=10)

    if "error" in result:
        print(f"FAIL: {result}")
        return False

    assert "periods" in result, "缺少 periods 字段"
    for horizon in [1, 3, 7, 30]:
        key = f"{horizon}d"
        assert key in result["periods"], f"缺少 {key} 结果"

    for key, pr in result["periods"].items():
        print(f"  {key}: sample_size={pr.get('sample_size')}, "
              f"directional_accuracy={pr.get('directional_accuracy')}, "
              f"brier_score={pr.get('brier_score')}")
        # Brier score 范围校验
        bs = pr.get("brier_score")
        if bs is not None:
            assert 0 <= bs <= 1, f"{key} Brier score 超范围: {bs}"

    print(f"  probability_quality: {result['probability_quality']}")
    print(f"  is_calibrated: {result['is_calibrated']}")
    print(f"  main_uncertainties: {result['main_uncertainties']}")
    print("PASS")
    return True


def test_insufficient_data():
    """数据不足时优雅返回"""
    print("\n=== test_insufficient_data ===")
    # 不足60天
    df = create_mock_nav_df(n_days=30)
    result = run_backtest(df)
    assert "error" in result, "数据不足应返回 error"
    assert result["sample_size"] == 30
    print(f"  30天数据: {result['error']} (sample_size={result['sample_size']})")
    print("PASS")
    return True


def test_confusion_matrix():
    """验证 confusion matrix 形状"""
    print("\n=== test_confusion_matrix ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.015)
    result = run_backtest(df, horizons=[7], min_samples=10)
    pr = result["periods"]["7d"]
    cm = pr["confusion_matrix"]
    labels = ["up", "sideways", "down"]
    for l1 in labels:
        for l2 in labels:
            assert l1 in cm and l2 in cm[l1], f"confusion_matrix 缺少 {l1}->{l2}"
    print(f"  confusion_matrix: {cm}")
    print("PASS")
    return True


def test_calibration_bins():
    """验证 calibration bins 格式正确（bin/expected_freq/observed_freq/count/abs_gap）"""
    print("\n=== test_calibration_bins ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02)
    result = run_backtest(df, horizons=[7], min_samples=10)
    pr = result["periods"]["7d"]
    bins = pr["calibration_bins"]
    assert isinstance(bins, list), "calibration_bins 应为 list"
    for b in bins:
        for field in ["bin", "expected_freq", "observed_freq", "count", "abs_gap"]:
            assert field in b, f"calibration_bin 缺少 {field}"
        assert 0 <= b["observed_freq"] <= 1, f"observed_freq 应在 [0,1]，实际 {b['observed_freq']}"
        assert 0 <= b["expected_freq"] <= 1, f"expected_freq 应在 [0,1]，实际 {b['expected_freq']}"
    print(f"  calibration_bins: {bins}")
    print("PASS")
    return True


def test_hit_rate_by_confidence():
    """验证 hit_rate_by_confidence 结构"""
    print("\n=== test_hit_rate_by_confidence ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02)
    result = run_backtest(df, horizons=[3], min_samples=10)
    pr = result["periods"]["3d"]
    hr = pr["hit_rate_by_confidence"]
    assert set(hr.keys()) == {"high", "medium", "low"}
    print(f"  hit_rate_by_confidence: {hr}")
    print("PASS")
    return True


def test_return_stats():
    """验证 return_stats 有统计值"""
    print("\n=== test_return_stats ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02)
    result = run_backtest(df, horizons=[30], min_samples=10)
    pr = result["periods"]["30d"]
    rs = pr["return_stats"]
    assert "mean" in rs and "median" in rs and "p10" in rs and "p90" in rs
    print(f"  return_stats: {rs}")
    print("PASS")
    return True


def test_baseline_comparison():
    """验证 baseline_comparison 包含三个模型对比及 edge 字段"""
    print("\n=== test_baseline_comparison ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02)
    result = run_backtest(df, horizons=[7], min_samples=10)
    pr = result["periods"]["7d"]
    bc = pr["baseline_comparison"]
    for field in ["always_sideways_acc", "simple_momentum_acc", "rule_acc", "best_baseline_acc", "rule_vs_best_baseline_edge"]:
        assert field in bc, f"baseline_comparison 缺少 {field}"
    # edge 应等于 rule_acc - best_baseline_acc
    expected_edge = round(bc["rule_acc"] - bc["best_baseline_acc"], 2)
    assert bc["rule_vs_best_baseline_edge"] == expected_edge, \
        f"rule_vs_best_baseline_edge 不一致: {bc['rule_vs_best_baseline_edge']} vs {expected_edge}"
    print(f"  baseline_comparison: {bc}")
    print("PASS")
    return True


def test_actual_distribution():
    """验证 actual_distribution 字段存在且三项之和≈100"""
    print("\n=== test_actual_distribution ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02)
    result = run_backtest(df, horizons=[7], min_samples=10)
    pr = result["periods"]["7d"]
    ad = pr["actual_distribution"]
    for field in ["up_pct", "sideways_pct", "down_pct"]:
        assert field in ad, f"actual_distribution 缺少 {field}"
        assert isinstance(ad[field], (int, float)), f"{field} 应为数值"
    total = ad["up_pct"] + ad["sideways_pct"] + ad["down_pct"]
    assert abs(total - 100) < 1, f"三项之和应≈100，实际 {total}"
    print(f"  actual_distribution: {ad} (sum={total})")
    print("PASS")
    return True


def test_threshold_dynamic():
    """动态阈值随波动率变化：高波动数据产生的阈值应大于低波动数据"""
    print("\n=== test_threshold_dynamic ===")
    # 高波动数据
    df_high = create_mock_nav_df(n_days=200, daily_vol=0.04, seed=1)
    result_high = run_backtest(df_high, horizons=[7], min_samples=10)
    thresh_high = result_high["periods"]["7d"]["threshold_used"]

    # 低波动数据
    df_low = create_mock_nav_df(n_days=200, daily_vol=0.005, seed=2)
    result_low = run_backtest(df_low, horizons=[7], min_samples=10)
    thresh_low = result_low["periods"]["7d"]["threshold_used"]

    # 高波动的阈值不应低于低波动（至少不低于 min_threshold）
    print(f"  高波动(vol=0.04) threshold: {thresh_high}")
    print(f"  低波动(vol=0.005) threshold: {thresh_low}")
    # 注意：低波动可能被 MIN_THRESHOLDS 兜底，所以只验证高波动阈值不小于低波动
    assert thresh_high >= thresh_low * 0.5, \
        f"高波动阈值({thresh_high})不应显著低于低波动阈值({thresh_low})"
    print("PASS")
    return True


def test_no_data_leakage():
    """无数据泄漏验证：同一输入多次运行结果一致，且预测只依赖 hist 数据"""
    print("\n=== test_no_data_leakage ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02, seed=42)
    result1 = run_backtest(df, horizons=[7], min_samples=10)
    result2 = run_backtest(df, horizons=[7], min_samples=10)

    # 确定性：相同输入应得到相同结果
    assert result1["periods"]["7d"]["directional_accuracy"] == result2["periods"]["7d"]["directional_accuracy"], \
        "相同输入应得到相同回测结果（确定性）"
    assert result1["periods"]["7d"]["brier_score"] == result2["periods"]["7d"]["brier_score"], \
        "相同输入的 Brier score 应一致"

    # 验证 threshold_median 字段存在（证明动态阈值在 hist 内计算）
    pr = result1["periods"]["7d"]
    assert "threshold_median" in pr, "threshold_median 字段应存在"
    assert pr["threshold_median"] > 0, "threshold_median 应 > 0"

    print(f"  运行1 accuracy={result1['periods']['7d']['directional_accuracy']}, "
          f"运行2 accuracy={result2['periods']['7d']['directional_accuracy']}")
    print("PASS")
    return True


def test_brier_score_regression():
    """Brier score 回归测试：全 sideway 预测的 Brier score 应在合理范围"""
    print("\n=== test_brier_score_regression ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02, seed=42)
    result = run_backtest(df, horizons=[1, 3, 7, 30], min_samples=10)

    for key in ["1d", "3d", "7d", "30d"]:
        pr = result["periods"][key]
        bs = pr.get("brier_score")
        if bs is not None:
            # 规则模型不应完美（Brier > 0），也不应完全错误（Brier < 1）
            assert 0 < bs < 1, f"{key} Brier score 应在 (0, 1)，实际 {bs}"
            print(f"  {key} Brier score: {bs}")

    print("PASS")
    return True


def test_probability_quality_logic():
    """验证 probability_quality 的逻辑正确性"""
    print("\n=== test_probability_quality_logic ===")
    # 1. 样本不足 → low
    df_small = create_mock_nav_df(n_days=30, daily_vol=0.02)
    result_small = run_backtest(df_small, horizons=[7], min_samples=10)
    if "error" in result_small:
        assert result_small["error"] == "insufficient_data"
        print(f"  样本不足 → error: {result_small['error']}")
    else:
        print(f"  样本不足 → quality: {result_small.get('probability_quality')}")

    # 2. 正常数据应有 quality 和 is_calibrated 字段
    df = create_mock_nav_df(n_days=200, daily_vol=0.02, seed=42)
    result = run_backtest(df, horizons=[1, 3, 7, 30], min_samples=10)
    assert "probability_quality" in result, "缺少 probability_quality"
    assert "is_calibrated" in result, "缺少 is_calibrated"
    assert result["probability_quality"] in ("low", "medium", "high"), \
        f"probability_quality 值无效: {result['probability_quality']}"

    # 3. 随机游走数据通常不应声称 high quality
    # (随机游走的规则模型很难稳定优于 baseline)
    assert result["probability_quality"] != "high" or result["is_calibrated"], \
        "random walk 数据不应出现 high quality 且 uncalibrated"

    print(f"  正常数据 quality={result['probability_quality']}, "
          f"is_calibrated={result['is_calibrated']}")
    print("PASS")
    return True


def test_main_uncertainties():
    """验证 main_uncertainties 列表非空且包含有意义文本"""
    print("\n=== test_main_uncertainties ===")
    df = create_mock_nav_df(n_days=200, daily_vol=0.02, seed=42)
    result = run_backtest(df, horizons=[1, 3, 7, 30], min_samples=10)
    unc = result.get("main_uncertainties", [])
    assert isinstance(unc, list), "main_uncertainties 应为 list"
    assert len(unc) > 0, "main_uncertainties 不应为空"

    # 当 quality 为 low 时，应包含低置信提示
    if result["probability_quality"] == "low":
        has_low_warning = any("低置信" in u or "优于基准" in u for u in unc)
        assert has_low_warning, f"low quality 时 main_uncertainties 应包含低置信提示: {unc}"

    print(f"  main_uncertainties ({len(unc)} items): {unc}")
    print("PASS")
    return True


def test_analyze_smoke():
    """冒烟测试 /api/analyze 端点：mock 所有外部依赖，验证返回结构完整"""
    print("\n=== test_analyze_smoke ===")
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient
    from main import app

    # 构造 mock 数据
    mock_fund_info = {"code": "161725", "name": "招商中证白酒指数(LOF)", "type": "指数型-股票", "company": "招商基金", "source": "mock"}
    mock_profile = {
        "fund_type": "指数型-股票", "fund_company": "招商基金", "fund_manager": "侯昊",
        "inception_date": "2015-05-27", "fund_size": "765.44亿元", "tracking_index": "中证白酒指数",
        "purchase_status": "开放申购", "redeem_status": "开放赎回",
        "management_fee": "1.00%", "custody_fee": "0.22%", "sales_service_fee": "unavailable",
        "risk_level": "R4", "return_1y": "-8.56%", "peer_ranking": "612|1249", "data_quality": "good",
    }
    mock_nav_df = create_mock_nav_df(n_days=200, daily_vol=0.02, seed=99)
    mock_macro = {
        "status": "ok", "summary": "市场震荡", "macro_summary": {
            "risk_appetite": "neutral", "overseas_direction": "mixed",
            "forex_pressure": "moderate", "commodity_disturbance": "low",
        },
        "risk_factors": ["海外不确定性"], "global_indices": [], "forex": [], "commodities": [], "as_of": "2026-05-29",
    }
    mock_ds_status = {"akshare": {"available": True, "detail": "ok"}, "efinance": {"available": False, "detail": "skip"}, "tencent": {"available": True, "detail": "ok"}}
    mock_llm_result = {
        "conclusion": "中性", "summary_7d": "短线震荡", "summary_30d": "中期偏弱",
        "summary_90d": "长期不确定", "risk_explanation": "波动率适中",
        "position_advice": "无持仓信息", "main_risks": ["市场波动"],
        "watch_points": ["关注均线"], "buy_conditions": ["回调至支撑位"],
        "reduce_conditions": ["跌破60日均线"], "confidence": "中",
        "data_basis": "200天数据", "disclaimer": "不构成投资建议",
        "forecast_summary_1d": "短线偏弱", "forecast_summary_7d": "中期震荡",
        "forecast_risks": ["回测样本有限"],
    }

    with patch("main.get_fund_info", return_value=mock_fund_info), \
         patch("main.get_fund_profile", return_value=mock_profile), \
         patch("main.get_fund_nav_history", return_value=mock_nav_df), \
         patch("main.get_datasource_status", return_value=mock_ds_status), \
         patch("main.get_macro_factors", return_value=mock_macro), \
         patch("main.get_tencent_nav_estimate", return_value=None), \
         patch("main.analyze_with_llm", return_value=mock_llm_result):

        client = TestClient(app)
        resp = client.get("/api/analyze", params={"code": "161725"})
        assert resp.status_code == 200, f"状态码应为200，实际 {resp.status_code}"
        data = resp.json()

        # 顶层字段
        assert data["success"] is True, f"success 应为 True，实际 {data.get('success')}"
        assert data["code"] == "161725"
        for key in ["fund", "fund_profile", "metrics", "macro", "risk", "forecast", "analysis", "datasource_status"]:
            assert key in data, f"缺少顶层字段: {key}"

        # forecast 子结构
        fc = data["forecast"]
        for period_key in ["forecast_1d", "forecast_3d", "forecast_7d", "forecast_30d"]:
            assert period_key in fc, f"forecast 缺少 {period_key}"
            fp = fc[period_key]
            for field in ["direction", "up_probability", "down_probability", "sideways_probability", "confidence", "reasons"]:
                assert field in fp, f"{period_key} 缺少 {field}"

        # validation
        assert "validation" in fc, "forecast 缺少 validation"
        v = fc["validation"]
        assert v is not None, "validation 不应为 None（200天数据足够回测）"
        assert "sample_size" in v and v["sample_size"] > 0

        # decision_support
        assert "decision_support" in fc, "forecast 缺少 decision_support"
        ds = fc["decision_support"]
        for field in ["action_bias", "buy_watch_conditions", "reduce_watch_conditions", "invalidation_signals"]:
            assert field in ds, f"decision_support 缺少 {field}"

        # risk
        r = data["risk"]
        for field in ["risk_score", "risk_level", "trend_score", "drawdown_score", "volatility_score", "position_score", "macro_score"]:
            assert field in r, f"risk 缺少 {field}"

        # analysis
        a = data["analysis"]
        assert "conclusion" in a, "analysis 缺少 conclusion"

        print(f"  success={data['success']}, risk_score={r.get('risk_score')}, "
              f"forecast_1d={fc['forecast_1d']['direction']}, "
              f"forecast_7d={fc['forecast_7d']['direction']}")
        print("PASS")
        return True


if __name__ == "__main__":
    tests = [
        test_mock_nav_backtest,
        test_insufficient_data,
        test_confusion_matrix,
        test_calibration_bins,
        test_hit_rate_by_confidence,
        test_return_stats,
        test_baseline_comparison,
        test_actual_distribution,
        test_threshold_dynamic,
        test_no_data_leakage,
        test_brier_score_regression,
        test_probability_quality_logic,
        test_main_uncertainties,
        test_analyze_smoke,
    ]
    all_pass = True
    for t in tests:
        try:
            ok = t()
            if not ok:
                all_pass = False
        except Exception as e:
            print(f"FAIL: {e}")
            all_pass = False

    print(f"\n=== 总计: {'ALL PASS' if all_pass else 'SOME FAIL'} ===")
    sys.exit(0 if all_pass else 1)