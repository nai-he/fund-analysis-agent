"""
对比测试：规则模型 vs 纯LLM判断
目标：验证当前prediction_engine是否比直接问LLM更准确
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv
from fund_data import get_fund_nav_history
from prediction_engine import generate_up_probability_prediction

load_dotenv()

def ask_llm_prediction(fund_code: str, nav_df) -> dict:
    """直接让LLM看历史数据做预测"""
    # 准备最近30天的数据摘要
    recent_30 = nav_df.tail(30)
    nav_list = recent_30["单位净值"].tolist()
    date_list = recent_30["净值日期"].tolist() if "净值日期" in recent_30.columns else []

    latest_nav = nav_list[-1]
    ret_7d = ((nav_list[-1] / nav_list[-5]) - 1) * 100 if len(nav_list) >= 5 else 0
    ret_30d = ((nav_list[-1] / nav_list[0]) - 1) * 100 if len(nav_list) >= 30 else 0

    prompt = f"""你是一个基金预测专家。请根据以下历史净值数据，预测未来7天和30天的涨跌方向。

基金代码: {fund_code}
最新净值: {latest_nav:.4f}
近7日涨跌: {ret_7d:.2f}%
近30日涨跌: {ret_30d:.2f}%

最近30天净值序列（从旧到新）:
{nav_list}

请严格按以下JSON格式输出，不要有任何其他内容：
{{
  "7d_prediction": "up" 或 "down_or_flat",
  "7d_confidence": "高" 或 "中" 或 "低",
  "7d_reason": "判断理由，50字以内",
  "30d_prediction": "up" 或 "down_or_flat",
  "30d_confidence": "高" 或 "中" 或 "低",
  "30d_reason": "判断理由，50字以内"
}}"""

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")

    url = f"{base_url}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 500,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            return {"error": f"API error: {response.status_code}"}

        result = response.json()
        content = result["content"][0]["text"].strip()

        # 提取JSON
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        return json.loads(content)
    except Exception as e:
        return {"error": str(e)}


def compare_predictions(fund_code: str):
    """对比两种方法的预测结果"""
    print(f"\n{'='*60}")
    print(f"对比测试: {fund_code}")
    print(f"{'='*60}\n")

    # 获取历史数据
    nav_df = get_fund_nav_history(fund_code, days=120)
    if nav_df is None or nav_df.empty:
        print(f"  [X] 无法获取基金 {fund_code} 的数据")
        return

    print(f"[OK] 获取到 {len(nav_df)} 天历史数据\n")

    # 方法1: 规则模型
    print("【方法1: 规则模型 (prediction_engine)】")
    rule_result = generate_up_probability_prediction(nav_df, horizons=[7, 30])

    if rule_result.get("status") == "ok":
        pred_7d = rule_result["periods"].get("7d", {})
        pred_30d = rule_result["periods"].get("30d", {})

        print(f"  7天预测:")
        print(f"    方向: {pred_7d.get('predicted_direction')}")
        print(f"    置信度: {pred_7d.get('confidence')}")
        print(f"    上涨概率: {pred_7d.get('up_probability')}%")
        print(f"    历史命中率: {pred_7d.get('historical_hit_rate')}%")
        print(f"    边际优势: {pred_7d.get('edge_vs_baseline')}%")

        print(f"\n  30天预测:")
        print(f"    方向: {pred_30d.get('predicted_direction')}")
        print(f"    置信度: {pred_30d.get('confidence')}")
        print(f"    上涨概率: {pred_30d.get('up_probability')}%")
        print(f"    历史命中率: {pred_30d.get('historical_hit_rate')}%")
        print(f"    边际优势: {pred_30d.get('edge_vs_baseline')}%")
    else:
        print(f"  [X] 规则模型无法生成预测: {rule_result.get('summary')}")

    # 方法2: 纯LLM
    print(f"\n{'='*60}")
    print("【方法2: 纯LLM判断】")
    llm_result = ask_llm_prediction(fund_code, nav_df)

    if "error" in llm_result:
        print(f"  [X] LLM调用失败: {llm_result['error']}")
    else:
        print(f"  7天预测:")
        print(f"    方向: {llm_result.get('7d_prediction')}")
        print(f"    置信度: {llm_result.get('7d_confidence')}")
        print(f"    理由: {llm_result.get('7d_reason')}")

        print(f"\n  30天预测:")
        print(f"    方向: {llm_result.get('30d_prediction')}")
        print(f"    置信度: {llm_result.get('30d_confidence')}")
        print(f"    理由: {llm_result.get('30d_reason')}")

    print(f"\n{'='*60}")
    print("【对比分析】")

    if rule_result.get("status") == "ok" and "error" not in llm_result:
        # 7天对比
        rule_7d_dir = pred_7d.get('predicted_direction')
        llm_7d_dir = llm_result.get('7d_prediction')

        print(f"\n7天预测:")
        print(f"  规则模型: {rule_7d_dir} (置信度: {pred_7d.get('confidence')})")
        print(f"  纯LLM:    {llm_7d_dir} (置信度: {llm_result.get('7d_confidence')})")
        print(f"  是否一致: {'[一致]' if rule_7d_dir == llm_7d_dir else '[不一致]'}")

        # 30天对比
        rule_30d_dir = pred_30d.get('predicted_direction')
        llm_30d_dir = llm_result.get('30d_prediction')

        print(f"\n30天预测:")
        print(f"  规则模型: {rule_30d_dir} (置信度: {pred_30d.get('confidence')})")
        print(f"  纯LLM:    {llm_30d_dir} (置信度: {llm_result.get('30d_confidence')})")
        print(f"  是否一致: {'[一致]' if rule_30d_dir == llm_30d_dir else '[不一致]'}")

        print(f"\n规则模型优势:")
        print(f"  - 有历史回测验证（命中率、边际优势）")
        print(f"  - 7天命中率: {pred_7d.get('historical_hit_rate')}%")
        print(f"  - 30天命中率: {pred_30d.get('historical_hit_rate')}%")

        print(f"\nLLM优势:")
        print(f"  - 可以理解复杂模式和市场逻辑")
        print(f"  - 给出明确的判断理由")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    # 测试几只不同类型的基金
    test_funds = [
        "000001",  # 华夏成长混合
        "110022",  # 易方达消费行业
        "161725",  # 招商中证白酒
    ]

    if len(sys.argv) > 1:
        test_funds = [sys.argv[1]]

    for fund_code in test_funds:
        compare_predictions(fund_code)
        print("\n" + "="*60 + "\n")
