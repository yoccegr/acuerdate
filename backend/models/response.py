from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from models.internal import SearchStatus, StoreResult


class ClassificationSummary(BaseModel):
    total_items: int
    unrecognized: int


class ParamsUsed(BaseModel):
    specialist_coverage_threshold: float
    specialist_max_items: int
    optional_coverage_threshold: float


class EngineBlock(BaseModel):
    classification_summary: ClassificationSummary
    rule_applied: str
    params_used: ParamsUsed


class RecommendationDetail(BaseModel):
    store: StoreResult
    alternatives: list[StoreResult]


class MapsBlock(BaseModel):
    recommendation: RecommendationDetail | None
    optional: list[StoreResult]
    search_status: SearchStatus


class ErrorDetail(BaseModel):
    code: str
    message: str


class RecommendResponse(BaseModel):
    status: Literal["ok", "no_results", "error"]
    engine: EngineBlock | None = None
    maps: MapsBlock | None = None
    error: ErrorDetail | None = None
