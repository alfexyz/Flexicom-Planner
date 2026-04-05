"""
SKU Normalizer — matches raw product names/codes to canonical product codes.

The canonical master is derived from issued (sales) invoices: the owner's own
product names are the ground truth.

Matching strategy (applied in order):
  1. Exact code match      — raw product_code exists in canonical master → confidence 1.0
  2. Exact name match      — normalised product_name matches a canonical name → confidence 0.95
  3. Token fuzzy match     — rapidfuzz token_set_ratio on normalised names → confidence = score/100
  4. LLM-assisted pass     — optional, env FLEXICOM_LLM_SKU=1, for rows below threshold
  5. Unmatched             — canonical_product_code = None, flagged in match log

Confidence thresholds:
  >= 0.85  auto-accept
  0.55–0.85  accepted but flagged for review
  < 0.55   rejected, canonical_product_code left as None
"""

import importlib.util
import logging
import os
import unicodedata
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

_AUTO_ACCEPT_THRESHOLD  = 0.85
_REVIEW_THRESHOLD       = 0.55
_LLM_ENV_VAR            = "FLEXICOM_LLM_SKU"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_skus(
    transactions: pd.DataFrame,
    inventory: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Add canonical_product_code, canonical_product_name, and sku_confidence columns
    to both DataFrames.

    Returns:
        transactions  — with canonical columns added
        inventory     — with canonical columns added
        match_log     — one row per unique (raw_name, source) combination
    """
    canonical_master = _build_canonical_master(transactions)

    transactions, tx_log = _match_dataframe(
        df=transactions.copy(),
        canonical_master=canonical_master,
        source="invoice_received",
        row_filter=lambda df: df["direction"] == "received",
    )

    # For issued rows, they ARE the canonical master — assign directly
    issued_mask = transactions["direction"] == "issued"
    transactions.loc[issued_mask, "canonical_product_code"] = transactions.loc[issued_mask, "product_code"]
    transactions.loc[issued_mask, "canonical_product_name"] = transactions.loc[issued_mask, "product_name"]
    transactions.loc[issued_mask, "sku_confidence"]         = 1.0

    inventory, inv_log = _match_dataframe(
        df=inventory.copy(),
        canonical_master=canonical_master,
        source="stock",
        row_filter=lambda df: pd.Series(True, index=df.index),
    )

    non_empty = [df for df in [tx_log, inv_log] if not df.empty]
    match_log = pd.concat(non_empty, ignore_index=True) if non_empty else tx_log

    # Optional LLM pass for anything still unmatched
    if os.getenv(_LLM_ENV_VAR) == "1" and _llm_available():
        transactions, inventory, match_log = _llm_pass(
            transactions, inventory, match_log, canonical_master
        )

    unmatched = (match_log["matched_canonical_code"].isna() | (match_log["matched_canonical_code"] == "")).sum()
    logger.info(
        "SKU normalization complete — %d unique names processed, %d unmatched",
        len(match_log),
        unmatched,
    )
    return transactions, inventory, match_log


# ---------------------------------------------------------------------------
# Canonical master
# ---------------------------------------------------------------------------

def _build_canonical_master(transactions: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """
    Build {product_code: (product_code, product_name)} from issued invoices.
    Also indexes by normalised product_name for name-based matching.
    """
    issued = transactions[transactions["direction"] == "issued"]
    master: dict[str, tuple[str, str]] = {}
    for _, row in issued.drop_duplicates("product_code").iterrows():
        code = str(row["product_code"]).strip()
        name = str(row["product_name"]).strip()
        if code:
            master[code] = (code, name)
    return master


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------

def _match_dataframe(
    df: pd.DataFrame,
    canonical_master: dict[str, tuple[str, str]],
    source: str,
    row_filter,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Match product_code and product_name in filtered rows against canonical_master.
    Adds canonical_product_code, canonical_product_name, sku_confidence columns.
    Returns (annotated_df, match_log_df).
    """
    df["canonical_product_code"] = None
    df["canonical_product_name"] = None
    df["sku_confidence"]         = None

    # Unique raw identifiers to match (avoid re-matching same name/code multiple times)
    mask = row_filter(df)
    subset = df.loc[mask, ["product_code", "product_name"]].drop_duplicates()

    # Build lookup structures for matching
    code_set  = set(canonical_master.keys())
    name_to_code: dict[str, str] = {
        _normalise_text(v[1]): k for k, v in canonical_master.items()
    }
    canonical_names = list(name_to_code.keys())   # for rapidfuzz

    log_rows: list[dict] = []

    for _, row in subset.iterrows():
        raw_code = str(row["product_code"]).strip()
        raw_name = str(row["product_name"]).strip()

        code, name, confidence, method = _match_single(
            raw_code, raw_name,
            code_set, name_to_code, canonical_names, canonical_master,
        )

        flagged = 0 if confidence >= _AUTO_ACCEPT_THRESHOLD else 1

        log_rows.append({
            "raw_name":              raw_name,
            "raw_code":              raw_code,
            "source":                source,
            "matched_canonical_code": code,
            "matched_canonical_name": name,
            "confidence":            confidence,
            "match_method":          method,
            "flagged":               flagged,
        })

        # Apply back to all matching rows in the DataFrame
        row_mask = mask & (
            (df["product_code"] == raw_code) | (df["product_name"] == raw_name)
        )
        df.loc[row_mask, "canonical_product_code"] = code
        df.loc[row_mask, "canonical_product_name"] = name
        df.loc[row_mask, "sku_confidence"]         = confidence

    match_log = pd.DataFrame(log_rows) if log_rows else pd.DataFrame(
        columns=["raw_name", "raw_code", "source", "matched_canonical_code",
                 "matched_canonical_name", "confidence", "match_method", "flagged"]
    )
    return df, match_log


def _match_single(
    raw_code: str,
    raw_name: str,
    code_set: set[str],
    name_to_code: dict[str, str],
    canonical_names: list[str],
    canonical_master: dict[str, tuple[str, str]],
) -> tuple[Optional[str], Optional[str], float, str]:
    """
    Returns (canonical_code, canonical_name, confidence, method) for a single raw product.
    """
    # --- Pass 1: exact code match ---
    if raw_code and raw_code in code_set:
        code, name = canonical_master[raw_code]
        return code, name, 1.0, "exact_code"

    # --- Pass 2: exact normalised name match ---
    norm_name = _normalise_text(raw_name)
    if norm_name and norm_name in name_to_code:
        code = name_to_code[norm_name]
        _, name = canonical_master[code]
        return code, name, 0.95, "exact_name"

    # --- Pass 3: token fuzzy match via rapidfuzz ---
    if norm_name and canonical_names:
        result = process.extractOne(
            norm_name,
            canonical_names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=_REVIEW_THRESHOLD * 100,
        )
        if result:
            best_norm_name, score, _ = result
            confidence = score / 100.0
            code = name_to_code[best_norm_name]
            _, name = canonical_master[code]
            return code, name, confidence, "token_fuzzy"

    # --- No match ---
    return None, None, 0.0, "no_match"


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _normalise_text(s: str) -> str:
    """
    Lowercase, strip diacritics, replace punctuation with spaces, collapse whitespace.
    "RULMENT 6205-2RS/C3 DIN625" → "rulment 6205 2rs c3 din625"
    """
    # Strip diacritics (ă→a, â→a, î→i, ș→s, ț→t, etc.)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    # Replace all non-alphanumeric chars (except spaces) with space
    import re
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Optional LLM pass
# ---------------------------------------------------------------------------

def _llm_available() -> bool:
    return importlib.util.find_spec("anthropic") is not None


def _llm_pass(
    transactions: pd.DataFrame,
    inventory: pd.DataFrame,
    match_log: pd.DataFrame,
    canonical_master: dict[str, tuple[str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Send unmatched product names to Claude for resolution.
    Updates rows that come back with confidence >= 0.7.
    """
    import anthropic
    import json

    unmatched_mask = match_log["matched_canonical_code"].isna() | (match_log["matched_canonical_code"] == "")
    unmatched = match_log[unmatched_mask]
    if unmatched.empty:
        return transactions, inventory, match_log

    canonical_list = "\n".join(
        f"{code} | {v[1]}" for code, v in sorted(canonical_master.items())
    )
    descriptions  = "\n".join(
        f"{i+1}. {row['raw_name']}"
        for i, (_, row) in enumerate(unmatched.iterrows())
    )

    prompt = f"""You are matching supplier product descriptions to a canonical product catalog for a Romanian agricultural spare parts dealer.

Canonical products:
{canonical_list}

For each supplier description below, return the best matching product code and a confidence between 0.0 and 1.0.
If no match is plausible, return "NOMATCH" with confidence 0.0.

Return ONLY a JSON array, one object per input:
[{{"index": 1, "code": "P001", "confidence": 0.92}}, ...]

Supplier descriptions to match:
{descriptions}"""

    try:
        client   = anthropic.Anthropic()
        message  = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        results = json.loads(message.content[0].text)
    except Exception as e:
        logger.warning("LLM SKU pass failed: %s — skipping", e)
        return transactions, inventory, match_log

    idx_list = list(unmatched.index)
    for item in results:
        i     = item.get("index", 0) - 1
        code  = item.get("code", "NOMATCH")
        conf  = float(item.get("confidence", 0.0))

        if code == "NOMATCH" or conf < 0.7 or code not in canonical_master:
            continue

        log_idx = idx_list[i]
        _, name = canonical_master[code]

        match_log.at[log_idx, "matched_canonical_code"] = code
        match_log.at[log_idx, "matched_canonical_name"] = name
        match_log.at[log_idx, "confidence"]             = conf
        match_log.at[log_idx, "match_method"]           = "llm"
        match_log.at[log_idx, "flagged"]                = 0

        # Propagate to transactions and inventory
        raw_name = match_log.at[log_idx, "raw_name"]
        raw_code = match_log.at[log_idx, "raw_code"]
        for df in (transactions, inventory):
            row_mask = (df["product_name"] == raw_name) | (df.get("product_code", "") == raw_code)
            df.loc[row_mask, "canonical_product_code"] = code
            df.loc[row_mask, "canonical_product_name"] = name
            df.loc[row_mask, "sku_confidence"]         = conf

    return transactions, inventory, match_log
