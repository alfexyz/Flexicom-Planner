"""
Shared pytest fixtures.

Loads the real synthetic database once per session and exposes
the key DataFrames and a pre-configured Engine instance.
"""

import pytest
from datetime import date
from pathlib import Path

import pandas as pd

from backend.engine.data_access import DataAccess

DB_PATH  = "data/flexicom.db"
AS_OF    = date(2026, 3, 29)   # pinned to the generator's END_DATE

# ---- planting-season product (P005 = Disc frictiune ambreiaj U650) ----
SEASONAL_PRODUCT = "P005"
# ---- fast-moving general product ----
NORMAL_PRODUCT   = "P001"
# ---- declining product ----
DECLINING_PRODUCT = "P024"
# ---- a product with barely any history (simulate by filtering window) ----
EDGE_PRODUCT     = "P017"   # low demand (1/week), tests edge of data sparsity
# ---- dominant customer ----
DOMINANT_CUSTOMER = "RO12345678"
# ---- churned customer ----
CHURNED_CUSTOMER  = "RO22334455"


@pytest.fixture(scope="session")
def da() -> DataAccess:
    if not Path(DB_PATH).exists():
        pytest.skip(f"Database not found at {DB_PATH} — run the ingestion pipeline first")
    return DataAccess(DB_PATH)


@pytest.fixture(scope="session")
def sales(da) -> pd.DataFrame:
    return da.sales()


@pytest.fixture(scope="session")
def purchases(da) -> pd.DataFrame:
    return da.purchases()


@pytest.fixture(scope="session")
def inventory(da) -> pd.DataFrame:
    return da.inventory()


@pytest.fixture(scope="session")
def engine():
    from backend.engine import Engine
    if not Path(DB_PATH).exists():
        pytest.skip(f"Database not found at {DB_PATH} — run the ingestion pipeline first")
    return Engine(DB_PATH, as_of=AS_OF)
