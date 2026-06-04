"""
FastAPI 入口
提供 /api/analyze 接口（GET 和 POST）：接收基金代码，返回完整分析结果
提供 /api/my-funds 接口：管理关注基金列表，批量分析
"""
import logging
import os
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    PositionInput, AnalyzeRequest, AnalyzeResponse, MacroResponse,
    UserFundInput, UserFundItem, BatchFundResult, BatchAnalyzeResponse,
)
from storage import load_user_funds, save_user_funds, validate_fund_code

from fund_data import get_fund_info, get_fund_nav_history, get_datasource_status
from metrics import calculate_metrics
from macro import get_macro_factors
from fund_profile import get_fund_profile
from risk_engine import calculate_risk
from forecast_engine import generate_forecast
from agent import analyze_with_llm
from providers.tencent_fund import get_tencent_nav_estimate
from backtest_engine import run_backtest
from decision_advisor import build_decision_advice
from final_decision import build_final_decision
from high_confidence_filter import build_high_confidence_decision
from prediction_engine import is_specific_trained_fund

load_dotenv()

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="基金决策辅助分析",
    description="国内公募基金数据采集与 AI 辅助分析工具",
    version="2.0.0",
)

# CORS：从环境变量读取允许的前端源
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
if _cors_origins_env:
    _cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_analysis(code: str, position: Optional[dict] = None) -> AnalyzeResponse:
    """核心分析流程"""
    logger.info(f"收到分析请求: {code}, has_position={position is not None and position.get('cost_nav') is not None}")

    # Step 1: 获取基金基本信息
    fund_info = get_fund_info(code)
    if fund_info is None:
        logger.warning(f"未找到基金: {code}")
        return AnalyzeResponse(
            success=False,
            code=code,
            error=f"未找到基金代码 {code} 对应的基金，请确认代码是否正确（如 161725、110022、510300）",
        )

    logger.info(f"基金信息: {fund_info.get('name')}")

    # Step 2: 获取基金画像
    fund_profile = get_fund_profile(code)
    logger.info(f"基金画像: quality={fund_profile.get('data_quality')}")

    # Step 3: 获取历史净值数据
    nav_days = 3650 if is_specific_trained_fund(code) else 120
    nav_df = get_fund_nav_history(code, days=nav_days)
    if nav_df is None or nav_df.empty:
        return AnalyzeResponse(
            success=False,
            code=code,
            fund=fund_info,
            fund_profile=fund_profile,
            error="无法获取该基金的历史净值数据，请稍后重试或检查网络连接",
        )

    # Step 4: 计算技术指标
    metrics = calculate_metrics(nav_df)
    current_estimate = get_tencent_nav_estimate(code)
    if current_estimate and current_estimate.get("estimated_change_pct") is not None:
        metrics["current_estimate"] = current_estimate
    logger.info(f"指标计算完成，数据天数: {metrics.get('data_days')}")

    # Step 5: 获取宏观因素
    macro = get_macro_factors()
    logger.info(f"宏观数据状态: {macro.get('status')}")

    # Step 6: 风险评分
    risk = calculate_risk(metrics, fund_profile, position, macro)
    logger.info(f"风险评分: {risk.get('risk_score')} ({risk.get('risk_level')})")

    # Step 6.5: 运行回测获取验证结果
    backtest_result = None
    try:
        backtest_result = run_backtest(nav_df, horizons=[1, 3, 7, 30], min_samples=10)
        if "error" not in backtest_result:
            logger.info(f"回测完成: quality={backtest_result.get('probability_quality')}, "
                       f"sample_size={backtest_result.get('sample_size')}, "
                       f"is_calibrated={backtest_result.get('is_calibrated')}")
        else:
            logger.info(f"回测跳过: {backtest_result.get('error')}")
            backtest_result = None
    except Exception as e:
        logger.warning(f"回测失败（不阻塞主流程）: {e}")
        backtest_result = None

    # Step 6.6: 未来走势情景判断
    forecast = generate_forecast(metrics, risk, fund_profile, macro, backtest_result=backtest_result)
    logger.info(
        f"走势情景: 1d={forecast['forecast_1d']['direction']}, "
        f"7d={forecast['forecast_7d']['direction']}, 30d={forecast['forecast_30d']['direction']}"
    )

    # Step 6.7: 短线预测（专注1天、3天、7天）
    from short_term_prediction import short_term_prediction
    prediction = short_term_prediction(
        nav_df,
        fund_code=code,
        fund_name=fund_info.get("name", ""),
        fund_type=fund_info.get("type", "")
    )
    logger.info(
        f"短线预测: quality={prediction.get('quality')}, "
        f"method={prediction.get('model_basis')}"
    )

    # Step 7: 数据源状态
    ds_status = get_datasource_status(code)

    # Step 8: 构建分析数据
    analysis_data = {
        "fund": fund_info,
        "fund_profile": fund_profile,
        "metrics": metrics,
        "macro": macro,
        "risk": risk,
        "forecast": forecast,
        "prediction": prediction,
        "position": position,
    }

    # Step 9: LLM 分析
    llm_result = analyze_with_llm(analysis_data)
    logger.info(f"分析结论: {llm_result.get('conclusion')}")

    # Step 10: 规则化买卖决策辅助
    decision_advice = build_decision_advice(
        fund=fund_info,
        metrics=metrics,
        risk=risk,
        forecast=forecast,
        position=position,
    )
    logger.info(f"决策建议: action={decision_advice.get('action')}, confidence={decision_advice.get('confidence')}")

    # Step 11: 最终结论聚合
    final_decision = build_final_decision(
        fund=fund_info,
        risk=risk,
        forecast=forecast,
        prediction=prediction,
        decision_advice=decision_advice,
        position=position,
    )
    logger.info(f"最终结论: direction={final_decision.get('direction')}, action={final_decision.get('action')}")

    # Step 12: 高置信度小资金决策
    high_confidence_decision = build_high_confidence_decision(
        fund=fund_info,
        metrics=metrics,
        risk=risk,
        forecast=forecast,
        prediction=prediction,
        backtest=backtest_result,
        position=position,
    )
    logger.info(f"高置信度决策: action={high_confidence_decision.get('action')}, confidence={high_confidence_decision.get('confidence')}")

    return AnalyzeResponse(
        success=True,
        code=code,
        fund=fund_info,
        fund_profile=fund_profile,
        metrics=metrics,
        macro=macro,
        risk=risk,
        forecast=forecast,
        prediction=prediction,
        analysis=llm_result,
        datasource_status=ds_status,
        decision_advice=decision_advice,
        final_decision=final_decision,
        high_confidence_decision=high_confidence_decision,
    )


@app.get("/api/analyze", response_model=AnalyzeResponse)
async def analyze_fund_get(
    code: str = Query(..., description="基金代码，如 161725、110022", min_length=5, max_length=6),
):
    """
    GET 方式分析指定基金代码（无持仓信息）
    """
    code = code.strip()
    return _run_analysis(code, position=None)


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_fund_post(request: AnalyzeRequest):
    """
    POST 方式分析指定基金代码（可选持仓信息）
    """
    code = request.code.strip()
    position = request.position.model_dump() if request.position else None
    return _run_analysis(code, position=position)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "基金决策辅助分析", "version": "2.0.0"}


@app.get("/api/macro", response_model=MacroResponse)
async def get_macro():
    """
    获取宏观一览数据（全球指数、汇率、商品、SHIBOR）
    轻量接口，不依赖基金代码，不运行完整分析流程
    """
    try:
        macro = get_macro_factors()
        return MacroResponse(success=True, macro=macro)
    except Exception as e:
        logger.error(f"宏观数据获取失败: {e}")
        return MacroResponse(success=False, macro=None, error=f"宏观数据获取失败：{e}")


# === 我的基金 API ===

@app.get("/api/my-funds")
async def get_my_funds():
    """获取我的基金列表"""
    funds = load_user_funds()
    return {"funds": funds, "count": len(funds)}


@app.post("/api/my-funds")
async def upsert_my_fund(input_data: UserFundInput):
    """新增或更新一只基金，按 code 去重"""
    code = validate_fund_code(input_data.code)
    funds = load_user_funds()

    item = input_data.model_dump()
    item["code"] = code

    # 按 code 去重：找到则更新，否则追加
    existing_idx = next((i for i, f in enumerate(funds) if f.get("code") == code), None)
    if existing_idx is not None:
        funds[existing_idx] = item
        logger.info(f"更新基金: {code}")
    else:
        funds.append(item)
        logger.info(f"新增基金: {code}")

    save_user_funds(funds)
    return {"success": True, "code": code, "count": len(funds)}


@app.delete("/api/my-funds/{code}")
async def delete_my_fund(code: str):
    """删除一只基金"""
    code = validate_fund_code(code)
    funds = load_user_funds()
    new_funds = [f for f in funds if f.get("code") != code]
    if len(new_funds) == len(funds):
        raise HTTPException(status_code=404, detail=f"基金 {code} 不在列表中")
    save_user_funds(new_funds)
    logger.info(f"删除基金: {code}")
    return {"success": True, "code": code, "count": len(new_funds)}


@app.post("/api/my-funds/analyze", response_model=BatchAnalyzeResponse)
async def batch_analyze_my_funds():
    """批量分析我的基金列表，顺序执行，单只失败不阻塞其他"""
    funds = load_user_funds()
    if not funds:
        return BatchAnalyzeResponse(success=True, total=0, results=[])

    logger.info(f"批量分析开始，共 {len(funds)} 只基金")
    results: List[BatchFundResult] = []

    for item in funds:
        code = item.get("code", "").strip()
        if not code:
            results.append(BatchFundResult(code="", success=False, error="缺少基金代码"))
            continue

        # 构建持仓信息
        position = {k: v for k, v in item.items() if k != "code" and k != "note" and v is not None}
        if not any(position.get(k) for k in ["cost_nav", "holding_amount", "holding_units"]):
            position = None  # 无实质性持仓信息时传 None

        try:
            analysis = _run_analysis(code, position=position)
            results.append(BatchFundResult(
                code=code,
                success=analysis.success,
                error=analysis.error,
                fund=analysis.fund,
                fund_profile=analysis.fund_profile,
                metrics=analysis.metrics,
                macro=analysis.macro,
                risk=analysis.risk,
                forecast=analysis.forecast,
                prediction=analysis.prediction,
                analysis=analysis.analysis,
                datasource_status=analysis.datasource_status,
                decision_advice=analysis.decision_advice,
                final_decision=analysis.final_decision,
                high_confidence_decision=analysis.high_confidence_decision,
            ))
            logger.info(f"批量分析 {code}: success={analysis.success}")
        except Exception as e:
            logger.error(f"批量分析 {code} 异常: {e}")
            results.append(BatchFundResult(code=code, success=False, error=str(e)))

    return BatchAnalyzeResponse(success=True, total=len(funds), results=results)


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"启动服务: {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
