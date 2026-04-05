"""
Invoice parser — reads a CSV e-Factura export and returns a normalized DataFrame.

Handles:
  - Multiple encodings (UTF-8, UTF-8-BOM, Windows-1250)
  - Romanian header aliases from common accounting software
  - Storno rows: forces quantity/total_value negative if not already
  - CSV only for now; XML raises NotImplementedError with a clear message
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical column names and their known aliases from Romanian accounting exports
_COLUMN_ALIASES: dict[str, list[str]] = {
    "invoice_number":  ["nr_factura", "numar_factura", "invoice_no", "document_number"],
    "invoice_date":    ["data_factura", "data_document", "date", "data"],
    "invoice_type":    ["tip_document", "tip_factura", "type", "document_type"],
    "direction":       ["directie", "sens", "tip_operatiune"],
    "product_code":    ["cod_produs", "cod_articol", "sku", "item_code", "product_id"],
    "product_name":    ["denumire_produs", "denumire", "description", "item_name", "articol"],
    "quantity":        ["cantitate", "qty", "quantity", "cant"],
    "unit_price":      ["pret_unitar", "pret", "price", "unit_price_ron"],
    "total_value":     ["valoare", "total", "valoare_totala", "amount"],
    "partner_cui":     ["cui_partener", "cui_client", "cui_furnizor", "cui", "vat_number"],
    "partner_name":    ["nume_partener", "client", "furnizor", "partner", "company_name"],
    "linked_invoice":  ["factura_initiala", "ref_document", "storno_ref", "original_invoice"],
}

_REQUIRED_COLUMNS = {
    "invoice_number", "invoice_date", "invoice_type", "direction",
    "product_code", "product_name", "quantity", "unit_price", "total_value",
}

_ENCODINGS = ["utf-8-sig", "utf-8", "cp1250"]


def parse(path: str | Path) -> pd.DataFrame:
    """
    Parse an e-Factura CSV export.

    Returns a DataFrame with canonical column names, all rows (issued + received),
    storno quantities guaranteed to be negative.

    Raises:
        NotImplementedError  if the file extension is .xml
        ValueError           if required columns are missing after alias resolution
        UnicodeDecodeError   if none of the attempted encodings work
    """
    path = Path(path)
    if path.suffix.lower() == ".xml":
        raise NotImplementedError(
            "XML e-Factura parsing is not yet implemented. "
            "Export as CSV from your accounting software or the ANAF portal."
        )

    df = _read_csv_with_encoding_fallback(path)
    df = _resolve_column_aliases(df)
    _validate_required_columns(df, path)
    df = _normalise_types(df)
    df = _fix_storno_signs(df)

    logger.info(
        "Parsed %d invoice lines from %s  (issued=%d, received=%d, storno=%d)",
        len(df),
        path.name,
        (df.direction == "issued").sum(),
        (df.direction == "received").sum(),
        (df.invoice_type == "storno").sum(),
    )
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_csv_with_encoding_fallback(path: Path) -> pd.DataFrame:
    last_err: Exception | None = None
    for enc in _ENCODINGS:
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
            logger.debug("Read %s with encoding %s", path.name, enc)
            return df
        except UnicodeDecodeError as e:
            last_err = e
    raise UnicodeDecodeError(
        f"Could not decode {path} with any of {_ENCODINGS}"
    ) from last_err


def _resolve_column_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns from accounting-software aliases to canonical names."""
    # Build reverse map: alias → canonical
    alias_to_canonical: dict[str, str] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            alias_to_canonical[alias.lower()] = canonical

    rename_map: dict[str, str] = {}
    for col in df.columns:
        normalised = col.strip().lower().replace(" ", "_")
        if normalised in alias_to_canonical and col not in rename_map:
            rename_map[col] = alias_to_canonical[normalised]

    if rename_map:
        logger.debug("Renamed columns: %s", rename_map)
        df = df.rename(columns=rename_map)

    return df


def _validate_required_columns(df: pd.DataFrame, path: Path) -> None:
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path.name} is missing required columns: {sorted(missing)}. "
            f"Found columns: {sorted(df.columns)}"
        )


def _normalise_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["quantity"]    = pd.to_numeric(df["quantity"],    errors="coerce")
    df["unit_price"]  = pd.to_numeric(df["unit_price"],  errors="coerce")
    df["total_value"] = pd.to_numeric(df["total_value"], errors="coerce")
    df["linked_invoice"] = df.get("linked_invoice", pd.Series("", index=df.index)).fillna("")
    df["direction"]   = df["direction"].str.strip().str.lower()
    df["invoice_type"] = df["invoice_type"].str.strip().str.lower()
    return df


def _fix_storno_signs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Guarantee storno rows have negative quantity and total_value.
    Some exports emit positive quantities with a separate sign flag; normalise here.
    """
    mask = df["invoice_type"] == "storno"
    df.loc[mask & (df["quantity"]    > 0), "quantity"]    *= -1
    df.loc[mask & (df["total_value"] > 0), "total_value"] *= -1
    return df
