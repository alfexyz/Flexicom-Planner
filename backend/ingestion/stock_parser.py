"""
Stock spreadsheet parser — reads a CSV or Excel stock list and returns a normalized DataFrame.

The business owner's spreadsheet will not use our exact column names.
This module uses token-overlap fuzzy matching to map whatever columns exist
to the canonical schema, then logs anything it couldn't map.

Required columns (will raise if both absent): product_code OR product_name
All other columns are optional — missing ones are filled with None.
"""

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_CANONICAL_COLUMNS = [
    "product_code",
    "product_name",
    "quantity_in_stock",
    "supplier_cui",
    "supplier_name",
    "lead_time_days",
    "min_order_qty",
    "purchase_price",
]

# Known exact aliases per canonical column (lowercase, underscored)
_COLUMN_ALIASES: dict[str, list[str]] = {
    "product_code":       ["cod_produs", "cod_articol", "sku", "item_code", "cod"],
    "product_name":       ["denumire_produs", "denumire", "description", "articol", "produs", "name"],
    "quantity_in_stock":  ["cantitate_stoc", "stoc_curent", "stoc", "qty", "cantitate", "quantity", "cant"],
    "supplier_cui":       ["cui_furnizor", "cui_supplier", "furnizor_cui"],
    "supplier_name":      ["furnizor", "supplier", "vendor", "provider"],
    "lead_time_days":     ["timp_livrare", "lead_time", "livrare_zile", "zile_livrare", "livrare"],
    "min_order_qty":      ["cantitate_minima", "min_order", "moq", "minim_comanda"],
    "purchase_price":     ["pret_achizitie", "pret_cumparare", "cost", "buy_price", "pret"],
}

_ENCODINGS = ["utf-8-sig", "utf-8", "cp1250"]


def parse(path: str | Path) -> pd.DataFrame:
    """
    Parse a stock spreadsheet (CSV or Excel).

    Returns a DataFrame with canonical column names.
    Columns the parser could not identify are dropped with a warning.
    product_name is required; product_code is optional but strongly preferred.

    Raises:
        ValueError  if neither product_code nor product_name can be identified
    """
    path = Path(path)
    df = _read_file(path)
    df = _map_columns(df)
    _validate(df, path)
    df = _fill_missing_columns(df)
    df = _normalise_types(df)

    logger.info(
        "Parsed %d stock rows from %s",
        len(df),
        path.name,
    )
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str)
    # CSV with encoding fallback
    last_err: Exception | None = None
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
        except UnicodeDecodeError as e:
            last_err = e
    raise UnicodeDecodeError(f"Could not decode {path}") from last_err


def _tokenise(s: str) -> set[str]:
    """Split a column name into lowercase tokens, filtering very short ones."""
    tokens = re.split(r"[\s_\-/]+", s.lower().strip())
    return {t for t in tokens if len(t) > 1}


def _token_overlap(col: str, canonical: str, aliases: list[str]) -> float:
    """
    Return the best token overlap ratio between a file column name and a canonical name + its aliases.
    Score is intersection / union of token sets (Jaccard).
    """
    col_tokens = _tokenise(col)
    if not col_tokens:
        return 0.0

    best = 0.0
    for target in [canonical] + aliases:
        target_tokens = _tokenise(target)
        if not target_tokens:
            continue
        intersection = col_tokens & target_tokens
        union        = col_tokens | target_tokens
        score = len(intersection) / len(union)
        if score > best:
            best = score
    return best


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map the file's actual column names to canonical names using token overlap."""
    # Build reverse map: file_col → canonical_col
    # For each file column, find the canonical column with the highest overlap score
    rename_map: dict[str, str] = {}
    used_canonicals: set[str] = set()

    for file_col in df.columns:
        # First: exact match check (after normalisation)
        normalised = file_col.strip().lower().replace(" ", "_")
        if normalised in _CANONICAL_COLUMNS and normalised not in used_canonicals:
            rename_map[file_col] = normalised
            used_canonicals.add(normalised)
            continue

        # Check exact alias match
        exact_found = False
        for canonical, aliases in _COLUMN_ALIASES.items():
            if normalised in aliases and canonical not in used_canonicals:
                rename_map[file_col] = canonical
                used_canonicals.add(canonical)
                exact_found = True
                break
        if exact_found:
            continue

        # Fuzzy token overlap
        best_score   = 0.0
        best_canonical = None
        for canonical, aliases in _COLUMN_ALIASES.items():
            if canonical in used_canonicals:
                continue
            score = _token_overlap(file_col, canonical, aliases)
            if score > best_score:
                best_score      = score
                best_canonical  = canonical

        if best_canonical and best_score >= 0.4:
            rename_map[file_col] = best_canonical
            used_canonicals.add(best_canonical)
            if best_score < 0.8:
                logger.warning(
                    "Column '%s' loosely mapped to '%s' (score=%.2f) — verify this is correct",
                    file_col, best_canonical, best_score,
                )
        else:
            logger.warning("Column '%s' could not be mapped to any canonical column — dropping it", file_col)

    # Keep only columns that were successfully mapped, renamed to canonical names
    mapped_file_cols = list(rename_map.keys())
    df = df[mapped_file_cols].rename(columns=rename_map)
    return df


def _validate(df: pd.DataFrame, path: Path) -> None:
    if "product_name" not in df.columns and "product_code" not in df.columns:
        raise ValueError(
            f"{path.name}: could not identify a product name or product code column. "
            "The parser needs at least one of: product_name, product_code."
        )


def _fill_missing_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add any canonical columns that are absent, filled with None."""
    for col in _CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
            logger.debug("Column '%s' not found in stock file — filled with None", col)
    return df[_CANONICAL_COLUMNS]


def _normalise_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("quantity_in_stock", "lead_time_days", "min_order_qty", "purchase_price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["product_code"] = df["product_code"].fillna("").str.strip()
    df["product_name"] = df["product_name"].fillna("").str.strip()
    return df
