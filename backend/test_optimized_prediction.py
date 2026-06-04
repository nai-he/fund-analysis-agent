"""
快速验证优化效果：对比优化前后的预测结果
"""
import sys
sys.path.insert(0, '.')

from fund_data import get_fund_nav_history
from prediction_engine import generate_up_probability_prediction

def test_optimized_model(fund_code: str):
    print(f"\n{'='*60}")
    print(f"测试基金: {fund_code}")
    print(f"{'='*60}\n")

    nav_df = get_fund_nav_history(fund_code, days=120)
    if nav_df is None or nav_df.empty:
        print(f"无法获取数据")
        return

    result = generate_up_probability_prediction(nav_df, horizons=[7, 30])

    if result.get("status") != "ok":
        print(f"预测失败: {result.get('summary')}")
        return

    print(f"整体质量: {result.get('quality')}")
    print(f"可用周期数: {result.get('usable_period_count')}")
    print(f"总样本数: {result.get('sample_size')}\n")

    for period_key in ["7d", "30d"]:
        period = result["periods"].get(period_key, {})
        print(f"【{period_key} 预测】")
        print(f"  方向: {period.get('predicted_direction')} ({period.get('direction_label')})")
        print(f"  置信度: {period.get('confidence')}")
        print(f"  上涨概率: {period.get('up_probability')}%")
        print(f"  历史命中率: {period.get('historical_hit_rate')}%")
        print(f"  基线命中率: {period.get('baseline_hit_rate')}%")
        print(f"  边际优势: {period.get('edge_vs_baseline')}%")
        print(f"  有正向优势: {period.get('has_positive_edge')}")
        print(f"  样本数: {period.get('sample_size')}")
        print(f"  Brier分数: {period.get('brier_score')}")

        warning = period.get('warning')
        if warning:
            print(f"  ⚠️  警告: {warning}")

        print()

    print(f"{'='*60}\n")


if __name__ == "__main__":
    # 测试不同类型的基金
    test_funds = [
        "000001",  # 华夏成长混合
        "110022",  # 易方达消费行业
        "161725",  # 招商中证白酒
    ]

    for code in test_funds:
        test_optimized_model(code)
