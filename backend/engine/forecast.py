"""
Demand forecasting engine.

Method selection per product:
  - XGBoost (weekly aggregation, lag + time features): products with >= 52 weeks of
    history AND fewer than 60% zero-demand weeks
  - Croston TSB: intermittent/lumpy demand (>= 60% zero-demand weeks)
  - Trend + seasonal fallback: fewer than 52 weeks of history or xgboost unavailable

Output: weekly forecast buckets for the next `horizon_days` days, with 80% prediction
interval estimated from training residuals.

Dependencies: xgboost, scikit-learn (both listed in requirements.txt)
"""

import logging
import math
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
_MIN_TRAIN_WEEKS    = 52     # need at least 1 full year to train XGBoost
_INTERMITTENT_ZERO  = 0.60   # > 60% zero weeks → Croston TSB
_MAX_LAG_WEEKS      = 52     # longest lag feature (1 year)
_PI_Z               = 1.28   # z-score for ~80% prediction interval

try:
    import xgboost as xgb
    from sklearn.preprocessing import StandardScaler  # noqa: F401 (import check)
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False
    logger.warning("xgboost / scikit-learn not installed — using trend+seasonal fallback")


# ── Public API ────────────────────────────────────────────────────────────────

def forecast_demand(
    product_code: str,
    sales_df: pd.DataFrame,
    horizon_days: int = 90,
    as_of: Optional[date] = None,
) -> dict:
    """
    Forecast weekly demand for `product_code` over the next `horizon_days` days.

    Returns:
        {
          product_code, method, horizon_days, as_of,
          weeks: [{week_start, week_end, forecast, lower, upper}],
          total_forecast, total_lower, total_upper
        }
    """
    as_of = as_of or date.today()
    weekly = _build_weekly_series(product_code, sales_df, as_of)

    n_weeks = len(weekly)
    if n_weeks == 0:
        return _empty_forecast(product_code, horizon_days, as_of)

    zero_pct = float((weekly == 0).mean())

    if not _XGB_AVAILABLE or n_weeks < _MIN_TRAIN_WEEKS:
        method = "trend_seasonal"
        buckets = _trend_seasonal_forecast(weekly, horizon_days, as_of)
    elif zero_pct >= _INTERMITTENT_ZERO:
        method = "croston"
        buckets = _croston_forecast(weekly, horizon_days, as_of)
    else:
        method = "xgboost"
        buckets = _xgboost_forecast(weekly, horizon_days, as_of)

    total_f = round(sum(b["forecast"] for b in buckets), 1)
    total_l = round(sum(b["lower"]    for b in buckets), 1)
    total_u = round(sum(b["upper"]    for b in buckets), 1)

    return {
        "product_code":   product_code,
        "method":         method,
        "horizon_days":   horizon_days,
        "as_of":          str(as_of),
        "weeks":          buckets,
        "total_forecast": total_f,
        "total_lower":    total_l,
        "total_upper":    total_u,
    }


# ── Weekly series builder ─────────────────────────────────────────────────────

def _build_weekly_series(
    product_code: str,
    sales_df: pd.DataFrame,
    as_of: date,
) -> pd.Series:
    """
    Aggregate daily sales to ISO weeks ending on `as_of`.
    Returns a pd.Series indexed by week-start date (Monday), values = units sold.
    """
    ps = sales_df[sales_df["canonical_product_code"] == product_code].copy()
    if ps.empty:
        return pd.Series(dtype=float)

    ps["week"] = ps["invoice_date"].dt.to_period("W").dt.start_time.dt.date

    weekly = (
        ps.groupby("week")["quantity"]
        .sum()
        .sort_index()
    )

    # Fill gaps so every week in the range has a value
    if len(weekly) < 2:
        return weekly.astype(float)

    first_week = weekly.index[0]
    last_week  = pd.Timestamp(as_of - timedelta(days=as_of.weekday())).date()  # Monday
    all_weeks  = pd.date_range(
        pd.Timestamp(first_week), pd.Timestamp(last_week), freq="W-MON"
    ).date
    weekly = weekly.reindex(all_weeks, fill_value=0).astype(float)
    return weekly


# ── Method 1: XGBoost ─────────────────────────────────────────────────────────

def _build_xgb_features(weekly: pd.Series) -> pd.DataFrame:
    df = weekly.to_frame(name="y").copy()
    df.index = pd.to_datetime(df.index)

    # Time features
    df["week_of_year"] = df.index.isocalendar().week.astype(int)
    df["month"]        = df.index.month
    df["quarter"]      = df.index.quarter

    # Cyclical encoding (no discontinuity at year boundary)
    df["week_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
    df["week_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Lag features (in weeks)
    for lag in [1, 2, 4, 8, 13, 26, 52]:
        df[f"lag_{lag}"] = df["y"].shift(lag)

    # Rolling statistics (shift by 1 to avoid leakage)
    for w in [4, 8, 13, 26]:
        df[f"roll_mean_{w}"] = df["y"].shift(1).rolling(w, min_periods=2).mean()

    df["roll_std_8"]  = df["y"].shift(1).rolling(8,  min_periods=4).std().fillna(0)
    df["roll_std_13"] = df["y"].shift(1).rolling(13, min_periods=6).std().fillna(0)

    # Trend: ratio of 4-week mean to 13-week mean
    df["trend_ratio"] = (
        df["roll_mean_4"] / (df["roll_mean_13"] + 1e-6)
    ).clip(0, 5)

    return df


_FEATURE_COLS = [
    "week_of_year", "month", "quarter",
    "week_sin", "week_cos", "month_sin", "month_cos",
    "lag_1", "lag_2", "lag_4", "lag_8", "lag_13", "lag_26", "lag_52",
    "roll_mean_4", "roll_mean_8", "roll_mean_13", "roll_mean_26",
    "roll_std_8", "roll_std_13",
    "trend_ratio",
]


def _xgboost_forecast(
    weekly: pd.Series,
    horizon_days: int,
    as_of: date,
) -> list[dict]:
    df = _build_xgb_features(weekly)
    train = df.dropna(subset=_FEATURE_COLS)

    X_train = train[_FEATURE_COLS].values
    y_train = train["y"].values

    model = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        objective="reg:squarederror",
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)

    # Residual std for prediction interval
    y_pred_train = model.predict(X_train)
    residuals    = y_train - y_pred_train
    residual_std = float(np.std(residuals))

    # Recursive forecast: extend the series one week at a time
    extended = list(weekly.values)
    extended_index = list(weekly.index)

    n_weeks = math.ceil(horizon_days / 7)
    results = []

    for i in range(n_weeks):
        next_monday = extended_index[-1] + timedelta(weeks=1)
        extended_index.append(next_monday)
        extended.append(0.0)  # placeholder

        tmp = pd.Series(extended, index=extended_index)
        feat_df = _build_xgb_features(tmp)
        row     = feat_df.iloc[-1]

        if row[_FEATURE_COLS].isna().any():
            # Not enough lag data — fall back to rolling mean
            pred = float(np.mean(extended[-13:])) if len(extended) >= 13 else float(np.mean(extended))
        else:
            pred = float(model.predict(row[_FEATURE_COLS].values.reshape(1, -1))[0])

        pred = max(0.0, pred)
        extended[-1] = pred  # use prediction as next input for recursive steps

        week_start = next_monday
        week_end   = next_monday + timedelta(days=6)
        results.append(_bucket(week_start, week_end, pred, residual_std))

    return results[:math.ceil(horizon_days / 7)]


# ── Method 2: Croston TSB ─────────────────────────────────────────────────────

def _croston_forecast(
    weekly: pd.Series,
    horizon_days: int,
    as_of: date,
) -> list[dict]:
    """
    Teunter-Syntetos-Babai method for intermittent demand.
    Separately smooths demand size and demand probability.
    """
    alpha = 0.15  # smoothing for demand size
    beta  = 0.10  # smoothing for demand probability

    values = weekly.values.astype(float)
    nonzero_idx = np.nonzero(values)[0]

    if len(nonzero_idx) == 0:
        return _flat_buckets(0.0, 0.0, horizon_days, as_of)

    # Initialize at first non-zero
    d = float(values[nonzero_idx[0]])
    p = 1.0 / (nonzero_idx[0] + 1) if nonzero_idx[0] > 0 else 1.0

    for v in values:
        if v > 0:
            d = alpha * v + (1 - alpha) * d
            p = beta + (1 - beta) * p
        else:
            p = (1 - beta) * p

    forecast_per_week = max(0.0, d * p)

    # Uncertainty: std of non-zero values scaled by probability
    nonzero_vals = values[nonzero_idx]
    std_nonzero  = float(np.std(nonzero_vals)) if len(nonzero_vals) > 1 else forecast_per_week * 0.5
    weekly_std   = std_nonzero * p

    return _flat_buckets(forecast_per_week, weekly_std, horizon_days, as_of)


# ── Method 3: Trend + seasonal fallback ──────────────────────────────────────

def _trend_seasonal_forecast(
    weekly: pd.Series,
    horizon_days: int,
    as_of: date,
) -> list[dict]:
    """
    Simple linear trend on recent 26 weeks × seasonal index from full history.
    No external dependencies.
    """
    values  = weekly.values.astype(float)
    n       = len(values)
    window  = min(n, 26)
    recent  = values[-window:]

    # Linear trend over recent window
    x      = np.arange(window, dtype=float)
    slope, intercept = (
        np.polyfit(x, recent, 1) if window >= 4 else (0.0, float(np.mean(recent)))
    )

    # Monthly seasonal indices from full history
    idx_series = pd.Series(values, index=weekly.index)
    idx_series.index = pd.to_datetime(idx_series.index)
    monthly    = idx_series.groupby(idx_series.index.month).mean()
    overall    = monthly.mean() if monthly.mean() > 0 else 1.0
    s_indices  = (monthly / overall).to_dict()

    # Uncertainty from recent residuals
    fitted     = intercept + slope * x
    residuals  = recent - fitted
    weekly_std = float(np.std(residuals)) if len(residuals) > 3 else float(np.mean(recent)) * 0.25

    n_weeks = math.ceil(horizon_days / 7)
    results = []
    last_monday = weekly.index[-1] if len(weekly) > 0 else as_of - timedelta(days=as_of.weekday())

    for i in range(n_weeks):
        week_start = last_monday + timedelta(weeks=i + 1)
        week_end   = week_start + timedelta(days=6)
        month      = pd.Timestamp(week_start).month
        s_mult     = s_indices.get(month, 1.0)
        base_demand = intercept + slope * (window + i)
        pred        = max(0.0, base_demand * s_mult)
        results.append(_bucket(week_start, week_end, pred, weekly_std))

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bucket(
    week_start,
    week_end,
    forecast: float,
    weekly_std: float,
) -> dict:
    margin = _PI_Z * weekly_std
    return {
        "week_start": str(week_start) if not isinstance(week_start, str) else week_start,
        "week_end":   str(week_end)   if not isinstance(week_end,   str) else week_end,
        "forecast":   round(max(0.0, forecast), 1),
        "lower":      round(max(0.0, forecast - margin), 1),
        "upper":      round(forecast + margin, 1),
    }


def _flat_buckets(
    weekly_forecast: float,
    weekly_std: float,
    horizon_days: int,
    as_of: date,
) -> list[dict]:
    n_weeks    = math.ceil(horizon_days / 7)
    last_monday = as_of - timedelta(days=as_of.weekday())
    results = []
    for i in range(n_weeks):
        week_start = last_monday + timedelta(weeks=i + 1)
        week_end   = week_start + timedelta(days=6)
        results.append(_bucket(week_start, week_end, weekly_forecast, weekly_std))
    return results


def _empty_forecast(product_code: str, horizon_days: int, as_of: date) -> dict:
    buckets = _flat_buckets(0.0, 0.0, horizon_days, as_of)
    return {
        "product_code":   product_code,
        "method":         "no_data",
        "horizon_days":   horizon_days,
        "as_of":          str(as_of),
        "weeks":          buckets,
        "total_forecast": 0.0,
        "total_lower":    0.0,
        "total_upper":    0.0,
    }
