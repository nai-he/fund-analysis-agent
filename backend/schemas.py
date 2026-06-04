"""Pydantic models for API request/response."""
from typing import Optional, List
from pydantic import BaseModel, Field


class PositionInput(BaseModel):
    cost_nav: Optional[float] = None
    holding_amount: Optional[float] = None
    holding_units: Optional[float] = None
    is_dca: Optional[bool] = False
    monthly_dca_amount: Optional[float] = None
    max_loss_percent: Optional[float] = None
    holding_horizon: Optional[str] = None
    risk_preference: Optional[str] = None
    planned_buy_amount: Optional[float] = None


class AnalyzeRequest(BaseModel):
    code: str
    position: Optional[PositionInput] = None


class AnalyzeResponse(BaseModel):
    success: bool
    code: str
    fund: Optional[dict] = None
    fund_profile: Optional[dict] = None
    metrics: Optional[dict] = None
    macro: Optional[dict] = None
    risk: Optional[dict] = None
    forecast: Optional[dict] = None
    prediction: Optional[dict] = None
    analysis: Optional[dict] = None
    datasource_status: Optional[dict] = None
    decision_advice: Optional[dict] = None
    final_decision: Optional[dict] = None
    high_confidence_decision: Optional[dict] = None
    error: Optional[str] = None


class UserFundInput(BaseModel):
    code: str
    cost_nav: Optional[float] = None
    holding_amount: Optional[float] = None
    holding_units: Optional[float] = None
    is_dca: Optional[bool] = False
    monthly_dca_amount: Optional[float] = None
    max_loss_percent: Optional[float] = None
    holding_horizon: Optional[str] = None
    risk_preference: Optional[str] = None
    note: Optional[str] = None


class UserFundItem(BaseModel):
    code: str
    cost_nav: Optional[float] = None
    holding_amount: Optional[float] = None
    holding_units: Optional[float] = None
    is_dca: Optional[bool] = False
    monthly_dca_amount: Optional[float] = None
    max_loss_percent: Optional[float] = None
    holding_horizon: Optional[str] = None
    risk_preference: Optional[str] = None
    note: Optional[str] = None


class BatchFundResult(BaseModel):
    code: str
    success: bool
    error: Optional[str] = None
    fund: Optional[dict] = None
    fund_profile: Optional[dict] = None
    metrics: Optional[dict] = None
    macro: Optional[dict] = None
    risk: Optional[dict] = None
    forecast: Optional[dict] = None
    prediction: Optional[dict] = None
    analysis: Optional[dict] = None
    datasource_status: Optional[dict] = None
    decision_advice: Optional[dict] = None
    final_decision: Optional[dict] = None
    high_confidence_decision: Optional[dict] = None


class MacroResponse(BaseModel):
    success: bool
    macro: Optional[dict] = None
    error: Optional[str] = None


class BatchAnalyzeResponse(BaseModel):
    success: bool
    total: int
    results: List[BatchFundResult] = Field(default_factory=list)
