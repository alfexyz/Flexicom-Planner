from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_engine
from backend.api.schemas import ForecastResponse, ForecastWeek
from backend.engine import Engine

router = APIRouter(prefix="/products", tags=["forecast"])


@router.get("/{product_code}/forecast", response_model=ForecastResponse)
def get_forecast(
    product_code: str,
    days: int = Query(default=90, ge=7, le=365),
    engine: Engine = Depends(get_engine),
):
    result = engine.forecast(product_code, horizon_days=days)
    return ForecastResponse(
        product_code   = result["product_code"],
        method         = result["method"],
        horizon_days   = result["horizon_days"],
        as_of          = result["as_of"],
        weeks          = [ForecastWeek(**w) for w in result["weeks"]],
        total_forecast = result["total_forecast"],
        total_lower    = result["total_lower"],
        total_upper    = result["total_upper"],
    )
