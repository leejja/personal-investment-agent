from pydantic import BaseModel, Field

from app.models.common import Evidence, RiskLevel


class PortfolioPosition(BaseModel):
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)

    quantity: int = Field(ge=0)
    average_price: float = Field(ge=0)
    current_price: float = Field(ge=0)

    market_value: float = Field(ge=0)
    profit_loss: float
    profit_loss_pct: float
    weight: float = Field(ge=0, le=1)


class PortfolioContext(BaseModel):
    total_value: float = Field(ge=0)
    cash: float = Field(ge=0)

    positions: list[PortfolioPosition] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class InvestorProfile(BaseModel):
    risk_tolerance: RiskLevel
    investment_horizon_months: int | None = Field(default=None, ge=1)
    target_return_pct: float | None = None

    objectives: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
