#!/usr/bin/env python3
"""Simple CLI tool to search an Excel inventory file and display details.

Usage:
    python search_inventory.py --file inventory.xlsx --query "123456"  # search by exact or partial match
    python search_inventory.py --file inventory.xlsx                  # opens interactive prompt

Columns expected in the Excel sheet (case-insensitive match):
    'qr code',
    'צילומי מדך עם ירוק',
    'צילומי מדף ללא ירוק',
    'צילומים דרך 10 מצלמות',
    'האם המוצר ירוק?',
    'מס המוצר בצילום',
    'label המוצר'

Any additional columns are loaded but not shown in the default output.

Requirements (install with `pip install -r requirements.txt`):
    pandas
    tabulate (pretty table output)
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import re
from typing import List, Optional

import pandas as pd
from tabulate import tabulate


DEFAULT_COLUMNS = [
    "qr code",
    "צילומי מדך עם ירוק",
    "צילומי מדף ללא ירוק",
    "צילומים דרך 10 מצלמות",
    "האם המוצר ירוק?",
    "מס המוצר בצילום",
    "label המוצר",
]

# Columns that must contain only Yes/No (case-insensitive). Update as needed.
BOOLEAN_COLUMNS = [
    "צילומי מדך עם ירוק",
    "צילומי מדף ללא ירוק",
    "צילומי מדף עם ירוק",
    "צילומים דרך 10 מצלמות",
    "האם המוצר ירוק?",
]


def load_data(path: pathlib.Path | None, url: str | None) -> pd.DataFrame:
    """Load data from an Excel file (if *path* given) or from a Google-Sheets CSV export *url*."""
    if url:
        try:
            df = pd.read_csv(url)
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"Error reading Google Sheets CSV: {exc}")
        return df

    if path is None:
        sys.exit("Error: you must supply --file or --url")

    try:
        df = pd.read_excel(path)
    except FileNotFoundError:
        sys.exit(f"Error: Excel file not found -> {path}")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Error reading Excel file: {exc}")
    return df


def search(df: pd.DataFrame, query: str, field: Optional[str] = None) -> pd.DataFrame:
    """Return rows where the query appears.

    If *field* is provided, search only that column (case-insensitive, literal match).
    Otherwise search all columns.
    """
    # Escape any regex metacharacters so the search is literal
    safe_query = re.escape(query)

    if field:
        # Validate column existence (case-insensitive)
        col_map = {c.lower(): c for c in df.columns}
        key = field.lower()
        if key not in col_map:
            sys.exit(f"Error: column '{field}' not found in sheet.")
        col_name = col_map[key]
        mask = df[col_name].astype(str).str.contains(safe_query, case=False, na=False, regex=True)
        return df[mask]

    # Search across all columns
    mask = df.apply(lambda col: col.astype(str).str.contains(safe_query, case=False, na=False, regex=True))
    return df[mask.any(axis=1)]


def display(df: pd.DataFrame, columns: List[str]) -> None:
    if df.empty:
        print("No matching items found.")
        return

    # Ensure requested columns exist (case-insensitive lookup)
    col_map = {c.lower(): c for c in df.columns}
    selected = []
    for col in columns:
        key = col.lower()
        if key in col_map:
            selected.append(col_map[key])
    if not selected:
        selected = list(df.columns)  # fallback

    print(tabulate(df[selected], headers="keys", tablefmt="grid", showindex=False))


def validate_booleans(df: pd.DataFrame) -> None:
    """Warn if BOOLEAN_COLUMNS contain values other than Yes/No (case-insensitive)."""
    for col in BOOLEAN_COLUMNS:
        if col not in df.columns:
            continue  # skip missing columns silently
        allowed = {"yes", "no", "כן", "לא"}
        bad_mask = ~df[col].astype(str).str.strip().str.lower().isin(allowed | {"nan", ""})
        if bad_mask.any():
            print("\n[Warning] Column '%s' has non-Yes/No values:" % col)
            print(tabulate(df.loc[bad_mask, [col]].head(), headers="keys", tablefmt="simple", showindex=False))


def interactive_loop(df: pd.DataFrame, field: Optional[str] = None) -> None:
    print("Type search terms (or 'exit' to quit). Partial matches allowed.")
    while True:
        try:
            query = input("Search> ").strip()
        except EOFError:  # Ctrl-D
            break
        if query.lower() in {"exit", "quit", "q"}:
            break
        if not query:
            continue
        matches = search(df, query, field=field)
        display(matches, DEFAULT_COLUMNS)
        print("----")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Search the inventory database (Excel file or Google Sheets).")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", "-f", type=pathlib.Path, help="Path to Excel file (e.g., inventory.xlsx)")
    group.add_argument(
        "--url",
        "-u",
        help="Google Sheets CSV export URL (e.g., https://docs.google.com/spreadsheets/d/<ID>/export?format=csv)",
    )
    p.add_argument("--query", "-q", help="Search term; if omitted, launches interactive prompt")
    p.add_argument("--field", "-c", help="Restrict search to a specific column (case-insensitive)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = load_data(args.file, args.url)
    # Validate boolean columns once per run
    validate_booleans(df)

    if args.query:
        result = search(df, args.query, field=args.field)
        display(result, DEFAULT_COLUMNS)
    else:
        interactive_loop(df, field=args.field)


if __name__ == "__main__":
    main()
