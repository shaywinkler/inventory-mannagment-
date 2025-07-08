"""Thin wrapper around Google Sheets operations.

Encapsulates all direct gspread / Sheets API logic so the rest of the
application can be swapped to a different backend (Airtable, Postgres, etc.)
by touching only this module.

Functions
---------
get_df(url) -> pd.DataFrame
    Return the entire sheet as a DataFrame.
update_row(url, idx, values)
    Overwrite a single (0-based) data row with *values*.
append_row(url, values)
    Append *values* as a new row at the bottom of the sheet.

This module **expects** that the service-account JSON key path has been set in
`GOOGLE_APPLICATION_CREDENTIALS` and that the sheet is shared with the account.
"""
from __future__ import annotations

import re
from typing import Sequence, Any

import pandas as pd
import gspread

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sheet_from_url(url: str):
    """Return gspread worksheet object for the first sheet given a user URL."""
    m = re.search(r"/d/([\w-]+)/", url)
    if not m:
        raise ValueError("Invalid Google Sheets URL")
    sheet_id = m.group(1)
    gc = gspread.service_account()  # relies on env-var
    return gc.open_by_key(sheet_id).sheet1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_df(url: str) -> pd.DataFrame:
    """Download entire sheet into a DataFrame (via exported CSV)."""
    # Derive CSV export link – this avoids the slower API call per cell
    if "format=csv" not in url:
        m = re.search(r"/d/([\w-]+)/", url)
        if m:
            sheet_id = m.group(1)
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    return pd.read_csv(url)


def update_row(url: str, row_idx: int, row_values: Sequence[Any]) -> None:
    """Update a single row in the sheet.

    Parameters
    ----------
    url
        Regular Google-Sheets URL (the *edit* one).
    row_idx
        Zero-based index **excluding** the header row (so 0 updates row 2 in
        the sheet). This matches pandas indexing of the DataFrame returned by
        `get_df`.
    row_values
        Iterable of cell values. The length should match the sheet columns.
    """
    ws = _sheet_from_url(url)
    # gspread expects 1-based row number including header
    ws.update(range_name=f"A{row_idx + 2}", values=[list(row_values)])


def append_row(url: str, row_values: Sequence[Any]) -> None:
    """Append *row_values* at the bottom of the sheet."""
    ws = _sheet_from_url(url)
    ws.append_row(list(row_values), value_input_option="USER_ENTERED")
