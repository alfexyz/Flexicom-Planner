import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from backend.api.dependencies import get_engine, reload_engine, DB_PATH
from backend.api.schemas import UploadResponse
from backend.engine import Engine
from backend.ingestion import run_pipeline

router = APIRouter(prefix="/upload", tags=["upload"])

# Where uploaded files are staged before ingestion
_UPLOAD_DIR   = Path("data/uploads")
_INVOICES_CSV = Path("data/invoices.csv")
_STOCK_CSV    = Path("data/stock.csv")


def _save_upload(upload: UploadFile, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest


@router.post("/invoices", response_model=UploadResponse)
async def upload_invoices(
    file: UploadFile = File(..., description="e-Factura CSV or XML export"),
    _engine: Engine = Depends(get_engine),   # ensures DB exists before upload
):
    """
    Upload a new e-Factura export (issued + received invoices).
    Replaces the existing invoices file and re-runs the full ingestion pipeline.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".csv", ".xml"):
        raise HTTPException(status_code=400, detail="Only .csv and .xml files are accepted")

    dest = _INVOICES_CSV.with_suffix(suffix)
    _save_upload(file, dest)

    try:
        summary = run_pipeline(str(dest), str(_STOCK_CSV), str(DB_PATH))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {e}")

    reload_engine()

    return UploadResponse(
        status            = "ok",
        transactions      = summary["transactions"],
        inventory_rows    = summary["inventory_rows"],
        sku_matches       = summary["sku_matches"],
        uncertain_matches = summary["uncertain_matches"],
        unmatched         = summary["unmatched"],
        elapsed_seconds   = summary["elapsed_seconds"],
        message           = (
            f"Ingested {summary['transactions']} invoice lines. "
            + (f"{summary['unmatched']} products could not be matched — check /sku_match_log."
               if summary["unmatched"] > 0 else "All products matched successfully.")
        ),
    )


@router.post("/stock", response_model=UploadResponse)
async def upload_stock(
    file: UploadFile = File(..., description="Stock spreadsheet (CSV or Excel)"),
    _engine: Engine = Depends(get_engine),
):
    """
    Upload a new stock spreadsheet (CSV or .xlsx).
    Replaces the existing stock file and re-runs the full ingestion pipeline.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="Only .csv, .xlsx and .xls files are accepted")

    dest = _STOCK_CSV.with_suffix(suffix)
    _save_upload(file, dest)

    try:
        summary = run_pipeline(str(_INVOICES_CSV), str(dest), str(DB_PATH))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {e}")

    reload_engine()

    return UploadResponse(
        status            = "ok",
        transactions      = summary["transactions"],
        inventory_rows    = summary["inventory_rows"],
        sku_matches       = summary["sku_matches"],
        uncertain_matches = summary["uncertain_matches"],
        unmatched         = summary["unmatched"],
        elapsed_seconds   = summary["elapsed_seconds"],
        message           = f"Stock updated with {summary['inventory_rows']} products.",
    )
