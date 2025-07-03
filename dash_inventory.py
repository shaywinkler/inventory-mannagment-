"""Dash web dashboard for searching the inventory Google Sheet.

Run with:
    python dash_inventory.py

Then open http://127.0.0.1:8050 in your browser.
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd
from dash import Dash, Input, Output, State, ctx, dash_table, dcc, html

# Re-use existing CLI logic
from search_inventory import DEFAULT_COLUMNS, load_data, search, validate_booleans

# Default Google-Sheets URL (can be changed in the UI)
DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/19RvAsEFg-0FiRjJmAt77IT07utYYxpzlpHrpwOTHpQ8/edit?usp=sharing"
)

app = Dash(__name__)
app.title = "Inventory Search"

app.layout = html.Div(
    [
        html.H2("Inventory Search Dashboard"),
        html.Div(
            [
                dcc.Input(
                    id="url-input",
                    value=DEFAULT_SHEET_URL,
                    type="text",
                    placeholder="Google Sheets URL (or CSV export)",
                    style={"width": "60%"},
                ),
                html.Button("Load Data", id="load-btn", n_clicks=0),
            ],
            style={"marginBottom": "1rem"},
        ),
        html.Div(
            [
                dcc.Input(
                    id="query-input",
                    type="text",
                    placeholder="Search term...",
                    style={"width": "40%"},
                ),
                dcc.Dropdown(id="field-dropdown", placeholder="Search specific column (optional)"),
                html.Button("Search", id="search-btn", n_clicks=0),
            ],
            style={"marginBottom": "1rem"},
        ),
        dcc.Store(id="data-store"),
        html.Div(id="warning-div", style={"color": "red", "whiteSpace": "pre-wrap"}),
        dash_table.DataTable(
            id="result-table",
            page_size=20,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left"},
        ),
    ],
    style={"padding": "2rem"},
)


def df_to_json(df: pd.DataFrame) -> str:
    """Serialize DataFrame to JSON (split orient) for dcc.Store."""
    return df.to_json(date_format="iso", orient="split")


def json_to_df(data: str | None) -> pd.DataFrame | None:
    if not data:
        return None
    return pd.read_json(data, orient="split")


@app.callback(
    Output("data-store", "data"),
    Output("field-dropdown", "options"),
    Output("warning-div", "children"),
    Input("load-btn", "n_clicks"),
    State("url-input", "value"),
    prevent_initial_call=True,
)
def load_sheet(n_clicks: int, url: str):  # noqa: D401  pylint: disable=unused-argument
    """Load the sheet, validate booleans, and populate column dropdown."""
    df = load_data(path=None, url=url)

    # Validate boolean columns (collect warnings instead of printing)
    warnings: list[str] = []
    for col in DEFAULT_COLUMNS:
        if col not in df.columns:
            continue
    # Use existing helper for validation (prints). Capture via context manager if needed
    validate_booleans(df)

    dropdown_opts = [{"label": c, "value": c} for c in df.columns]
    return df_to_json(df), dropdown_opts, "\n".join(warnings)


@app.callback(
    Output("result-table", "data"),
    Output("result-table", "columns"),
    Input("search-btn", "n_clicks"),
    State("query-input", "value"),
    State("field-dropdown", "value"),
    State("data-store", "data"),
    prevent_initial_call=True,
)
def do_search(n_clicks: int, query: str, field: str | None, data: str):  # noqa: D401  pylint: disable=unused-argument
    if not query:
        return [], []
    df = json_to_df(data)
    if df is None:
        return [], []
    result = search(df, query, field=field)
    # Ensure display columns exist, else fallback to all
    cols = [c for c in DEFAULT_COLUMNS if c in result.columns]
    if not cols:
        cols = list(result.columns)
    return result[cols].to_dict("records"), [{"name": c, "id": c} for c in cols]


if __name__ == "__main__":
    app.run(debug=True)
