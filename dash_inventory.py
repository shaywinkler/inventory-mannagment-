"""Dash web dashboard for searching the inventory Google Sheet.

Run with:
    python dash_inventory.py

Then open http://127.0.0.1:8050 in your browser.
"""
from __future__ import annotations

import json
import pathlib
import re
import os
import sys

import pandas as pd
from dash import Dash, Input, Output, State, ALL, ctx, dash_table, dcc, html
import dash_bootstrap_components as dbc
import dash  # for PreventUpdate

# Re-use existing CLI logic
from search_inventory import DEFAULT_COLUMNS, load_data, search, validate_booleans

# Default Google-Sheets URL (can be changed in the UI)
DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/19RvAsEFg-0FiRjJmAt77IT07utYYxpzlpHrpwOTHpQ8/edit?usp=sharing"
)

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
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
        html.Hr(),
        html.H4("Add New Item"),
        html.Div([
            dcc.Input(id="name-input", placeholder="name", type="text", style={"width": "220px"}),
            dcc.Input(id="qr-input", placeholder="qr code", type="text", style={"width": "200px"}),
            dcc.Dropdown(id="picture-input", options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}], placeholder="picture?", style={"width": "160px"}),
            dcc.Dropdown(id="shelfpic-input", options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}], placeholder="picture by shelf?", style={"width": "180px"}),
            dcc.Dropdown(id="green-input", options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}], placeholder="is it green?", style={"width": "160px"}),
            dcc.Input(id="notes-input", placeholder="notes", type="text", style={"width": "250px"}),
            dcc.Dropdown(id="visible-input", options=[{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}], placeholder="VISIBLE/ NOT", style={"width": "160px"}),
            html.Button("Upload", id="upload-btn", n_clicks=0, style={"marginLeft": "1rem"}),
        ], style={"display": "flex", "gap": "0.5rem", "flexWrap": "wrap", "marginBottom": "1rem"}),
        html.Div(id="upload-status", style={"color": "green", "whiteSpace": "pre-wrap"}),
        dash_table.DataTable(
            id="result-table",
            page_size=20,
            row_selectable="single",
            selected_rows=[],
            style_table={"overflowX": "auto", "maxHeight": "60vh", "overflowY": "auto"},
            style_cell={"textAlign": "left"},
        ),
        html.Button("Edit Selected", id="edit-btn", n_clicks=0, disabled=True, className="btn btn-secondary mt-2"),
        # Edit modal (hidden by default)
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Edit Row"), close_button=False),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col(dbc.Input(id="edit-name", placeholder="name")),
                    dbc.Col(dbc.Input(id="edit-qr", placeholder="qr code")),
                    dbc.Col(dbc.Select(id="edit-picture", options=[{"label":"yes","value":"yes"},{"label":"no","value":"no"}])),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col(dbc.Select(id="edit-shelfpic", options=[{"label":"yes","value":"yes"},{"label":"no","value":"no"}])),
                    dbc.Col(dbc.Select(id="edit-green", options=[{"label":"yes","value":"yes"},{"label":"no","value":"no"}])),
                    dbc.Col(dbc.Input(id="edit-notes", placeholder="notes")),
                    dbc.Col(dbc.Select(id="edit-visible", options=[{"label":"yes","value":"yes"},{"label":"no","value":"no"}])),
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("Save", id="save-btn", n_clicks=0, className="btn btn-primary"),
                dbc.Button("Cancel", id="cancel-btn", n_clicks=0, className="btn btn-outline-secondary")
            ])
        ], id="edit-modal", is_open=False),
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
    Input("query-input", "value"),  # triggers on every keystroke (auto-search)
    Input("field-dropdown", "value"),
    State("data-store", "data"),
    prevent_initial_call=True,
)
def do_search(query: str, field: str | None, data: str):  # noqa: D401
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


# ---------------- Upload callback -----------------
try:
    import gspread  # noqa: WPS433
    from google.auth.exceptions import GoogleAuthError  # noqa: WPS433
except ImportError:  # gspread not installed yet
    gspread = None  # type: ignore


@app.callback(
    Output("upload-status", "children"),
    Input("upload-btn", "n_clicks"),
    State("url-input", "value"),
    State("name-input", "value"),
    State("qr-input", "value"),
    State("picture-input", "value"),
    State("shelfpic-input", "value"),
    State("green-input", "value"),
    State("notes-input", "value"),
    State("visible-input", "value"),
    prevent_initial_call=True,
)
def upload_row(n_clicks: int, url: str, name: str, qr: str, picture: str, shelfpic: str, green: str, notes: str, visible: str):  # noqa: D401
    if gspread is None:
        return "gspread not installed. Run pip install -r requirements.txt again."
    if not all([name, qr]):
        return "Name and QR code are required."
    # Extract sheet ID
    m = re.search(r"/d/([\w-]+)/", url)
    if not m:
        return "Invalid sheet URL."
    sheet_id = m.group(1)
    try:
        gc = gspread.service_account()  # relies on GOOGLE_APPLICATION_CREDENTIALS env var
        sh = gc.open_by_key(sheet_id)
        worksheet = sh.sheet1  # first tab
        # Normalise boolean fields to "yes"/"no" and validate
        bool_fields = {
            "picture": picture,
            "picture by shelf": shelfpic,
            "is it green?": green,
            "VISIBLE/ NOT": visible,
        }
        allowed_set = {"yes", "no", ""}
        norm_values: list[str] = []
        for key, val in bool_fields.items():
            v = (val or "").strip().lower()
            if v not in allowed_set:
                return f"Field '{key}' must be Yes or No (got '{val}')."
            norm_values.append(v)
        new_row = [
            name,
            qr,
            norm_values[0],  # picture
            norm_values[1],  # picture by shelf
            norm_values[2],  # is it green?
            notes or "",
            norm_values[3],  # visible/not
        ]
        worksheet.append_row(new_row, value_input_option="USER_ENTERED")
        return "Row uploaded successfully."
    except GoogleAuthError as exc:
        return f"Auth error: {exc}. Ensure GOOGLE_APPLICATION_CREDENTIALS env var points to service-account JSON and that the sheet is shared with it."
    except Exception as exc:  # noqa: BLE001
        return f"Upload failed: {exc}"



# ---------- Enable/disable Edit button ----------
@app.callback(
    Output("edit-btn", "disabled"),
    Input("result-table", "selected_rows"),
)
def _toggle_edit_btn(selected_rows):
    # Disabled when nothing selected
    return not bool(selected_rows)

# ---------- Open edit modal and populate fields ----------
@app.callback(
    Output("edit-modal", "is_open"),
    Output("edit-name", "value"),
    Output("edit-qr", "value"),
    Output("edit-picture", "value"),
    Output("edit-shelfpic", "value"),
    Output("edit-green", "value"),
    Output("edit-notes", "value"),
    Output("edit-visible", "value"),
    Input("edit-btn", "n_clicks"),
    Input("cancel-btn", "n_clicks"),
    State("result-table", "selected_rows"),
    State("data-store", "data"),
    prevent_initial_call=True,
)
def _open_modal(n_edit, n_cancel, selected_rows, data_json):
    # Close on cancel or no selection
    if dash.ctx.triggered_id == "cancel-btn" or not selected_rows:
        return False, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    df = json_to_df(data_json)
    if df is None:
        return False, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    row = df.iloc[selected_rows[0]]
    return True, row.get("name"), row.get("qr code"), row.get("picture"), row.get("picture by shelf"), row.get("is it green?"), row.get("notes"), row.get("VISIBLE/ NOT")

# ---------- Save edits back to sheet ----------
@app.callback(
    Output("data-store", "data", allow_duplicate=True),
    Output("edit-modal", "is_open", allow_duplicate=True),
    Input("save-btn", "n_clicks"),
    State("result-table", "selected_rows"),
    State("url-input", "value"),
    State("edit-name", "value"),
    State("edit-qr", "value"),
    State("edit-picture", "value"),
    State("edit-shelfpic", "value"),
    State("edit-green", "value"),
    State("edit-notes", "value"),
    State("edit-visible", "value"),
    prevent_initial_call=True,
)
def _save_row(n_clicks, selected_rows, url, name, qr, picture, shelfpic, green, notes, visible):
    if n_clicks == 0 or not selected_rows:
        raise dash.exceptions.PreventUpdate
    row_idx = selected_rows[0]
    df = load_data(None, url)
    # apply edits
    df.at[row_idx, "name"] = name
    df.at[row_idx, "qr code"] = qr
    df.at[row_idx, "picture"] = picture
    df.at[row_idx, "picture by shelf"] = shelfpic
    df.at[row_idx, "is it green?"] = green
    df.at[row_idx, "notes"] = notes
    df.at[row_idx, "VISIBLE/ NOT"] = visible

    # write single row to sheet
    try:
        m = re.search(r"/d/([\w-]+)/", url)
        if m:
            sheet_id = m.group(1)
            gc = gspread.service_account()
            ws = gc.open_by_key(sheet_id).sheet1
            ws.update(f"A{row_idx + 2}", [df.iloc[row_idx].tolist()])
    except Exception as exc:  # noqa: BLE001
        print("[Warning] Failed to write row:", exc)

    return df_to_json(df), False

if __name__ == "__main__":
    # Allow overriding port via --port=<num> or PORT env var
    port = 8050
    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
    port = int(os.getenv("PORT", port))
    app.run(debug=True, port=port)