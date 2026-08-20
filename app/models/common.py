from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalysisConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Evidence(BaseModel):
    source: str = Field(min_length=1)
    description: str = Field(min_length=1)
    reference: str | None = None
    timestamp: datetime | None = None


class UserRequest(BaseModel):
    question: str = Field(min_length=1)
    symbols: list[str] = Field(default_factory=list)
