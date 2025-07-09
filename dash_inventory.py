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
from sheets import get_df, update_row, append_row
import dash  # for PreventUpdate

# Re-use existing CLI logic
from search_inventory import DEFAULT_COLUMNS, load_data, search, validate_booleans

# Default Google-Sheets URL (can be changed in the UI)
DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/19RvAsEFg-0FiRjJmAt77IT07utYYxpzlpHrpwOTHpQ8/edit?usp=sharing"
)

external_stylesheets = [
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css",  # Font Awesome icons
]

# Custom HTML to include Intro.js assets
INTRO_INDEX_STRING = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link id=\"theme-css\" rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/lux/bootstrap.min.css\">\n        <link rel=\"stylesheet\" href=\"https://unpkg.com/intro.js/minified/introjs.min.css\">\n        <style>\n          body.dark-mode .introjs-tooltip { background:#343a40 !important; color:#fff !important;}\n          body.dark-mode .introjs-tooltiptext { color:#fff !important;}\n          body.dark-mode .introjs-helperLayer { background:rgba(0,0,0,0.6) !important;}\n          body.magenta-mode {background-color:#5f3dc4; color:#000;}
          body.magenta-mode .btn-primary, body.magenta-mode .bg-primary {background-color:#d633ff !important; border-color:#d633ff !important;}
          body.magenta-mode .nav-link.active {background-color:#d633ff !important;}
          body.magenta-mode .introjs-tooltip {background:#7048e8 !important; color:#000 !important;}
        </style>
        <script src=\"https://unpkg.com/intro.js/minified/intro.min.js\"></script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""
app = Dash(__name__, external_stylesheets=external_stylesheets)
app.index_string = INTRO_INDEX_STRING
app.title = "Inventory Search"

app.layout = html.Div([
    # ---------- Top navigation ----------
    dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand("Inventory Dashboard", className="fw-bold"),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink("Dashboard", href="#", id="tab-dashboard")),
                dbc.NavItem(dbc.NavLink("Products", href="#", id="tab-products")),
                dbc.NavItem(dbc.NavLink("Orders", href="#", id="tab-orders")),
                dbc.NavItem(dbc.NavLink("Reports", href="#", id="tab-reports")),
            ], className="me-auto", pills=True, id="nav-links"),
            dbc.Input(type="search", placeholder="Global search…", id="global-search", style={"maxWidth": "250px"}),
            dcc.Dropdown(
                id="theme-dropdown",
                options=[
                    {"label": "Light", "value": "lux"},
                    {"label": "Dark", "value": "darkly"},
                    {"label": "Flatly", "value": "flatly"},
                    {"label": "Cyborg", "value": "cyborg"},
                    {"label": "Magenta", "value": "magenta"},
                ],
                value="lux",
                clearable=False,
                style={"width": "120px", "marginLeft": "12px"},
            ),
        ]),
        color="light",
        sticky="top",
        className="shadow-sm",
    ),

    dbc.Breadcrumb(id="breadcrumbs", items=[{"label": "Dashboard", "active": True}], className="mt-2 ms-3"),

    # Main content wrappers
    html.Div(id="dashboard-section", children=[
        html.H2("Inventory Search Dashboard"),

        html.Button(
            html.Span([
                html.I(className="fa-solid fa-book fa-stack-2x"),
                html.I(className="fa-solid fa-circle-info fa-stack-1x fa-inverse")
            ], className="fa-stack fa-2x me-1"),
            id="tour-btn",
            title="Start tour",
            className="btn btn-outline-primary ms-2",
        ),
        dbc.Tooltip("Start guided tour", target="tour-btn", placement="bottom"),
        html.A(
            html.I(className="fa-solid fa-circle-question fa-lg"),
            id="help-link",
            href="https://example.com/faq",  # replace with real FAQ/support URL
            target="_blank",
            className="position-absolute top-0 end-0 m-3 text-secondary",
        ),
        html.Div(id="tour-dummy", style={"display": "none"}),

# ----- Undo toast and timer -----
dbc.Toast(
    [
        html.Span(id="toast-msg"),
        dbc.Button("Undo", id="undo-btn", color="link", size="sm", className="ms-2"),
    ],
    id="undo-toast",
    header="Action performed",
    is_open=False,
    dismissable=True,
    icon="warning",
    style={"position": "fixed", "bottom": 20, "right": 20, "minWidth": "250px", "zIndex": 2000},
),
# interval ticks every 1s; separate callback closes toast after 50s
dcc.Interval(id="undo-interval", interval=1000, disabled=True),
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
dcc.Store(id="table-settings", storage_type="local"),
# Audit log of last 10 edits
dcc.Store(id="audit-log", data=[], storage_type="session"),
# Store to keep last action details for undo
dcc.Store(id="last-action", storage_type="session"),

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
              editable=True,
             style_header={"backgroundColor": "#343a40", "color": "#ffffff", "fontWeight": "bold"},
            page_size=20,
            row_selectable="single",
            selected_rows=[],
            style_table={"overflowX": "auto", "maxHeight": "60vh", "overflowY": "auto"},
            style_cell={"textAlign": "left", "color": "#000"},
        ),
        html.Button(html.I(className="fa-solid fa-pen"), id="edit-btn", n_clicks=0, disabled=True, className="btn btn-secondary mt-2"),
html.Button(html.I(className="fa-solid fa-trash"), id="delete-btn", n_clicks=0, disabled=True, className="btn btn-danger mt-2 ms-2"),
html.Button(html.I(className="fa-solid fa-rotate-right"), id="restock-btn", n_clicks=0, disabled=True, className="btn btn-success mt-2 ms-2"),
# Tooltips for action buttons
dbc.Tooltip("Edit selected row", target="edit-btn", placement="top"),
dbc.Tooltip("Delete row", target="delete-btn", placement="top"),
dbc.Tooltip("Restock item", target="restock-btn", placement="top"),

        # Audit trail toggle and panel
        dbc.Button("Recent Edits", id="audit-toggle", color="secondary", className="mt-3"),
        dbc.Collapse(
            dbc.ListGroup(id="audit-list"),
            id="audit-collapse",
            is_open=False,
            className="mt-2"
        ),

        # Detail offcanvas
        dbc.Offcanvas(
            id="detail-drawer",
            title="Item Details",
            is_open=False,
            placement="end",
            style={"width": "350px"},
            children=html.Div(id="drawer-body", className="p-2")
        ),
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
    className='app-container'
 ),
 # Placeholder content for other tabs
 html.Div(
     id="placeholder-section",
     style={"display": "none"},
     children=html.Div("Content coming soon…", className="p-4"),
 ),
])


def df_to_json(df: pd.DataFrame) -> str:
    """Serialize DataFrame to JSON (split orient) for dcc.Store."""
    return df.to_json(date_format="iso", orient="split")


def json_to_df(data: str | None) -> pd.DataFrame | None:
    if not data:
        return None
    from io import StringIO  # noqa: WPS433
    return pd.read_json(StringIO(data), orient="split")


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
    df = get_df(url)

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
    Output("result-table", "data", allow_duplicate=True),
    Output("result-table", "columns", allow_duplicate=True),
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


# (KPI cards removed at user request)


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



# ---------- Audit panel toggle ----------
@app.callback(Output("audit-collapse","is_open"), Input("audit-toggle","n_clicks"), State("audit-collapse","is_open"), prevent_initial_call=True)
def _toggle_audit(n, open_):
    return not open_ if n else open_

# ---------- Update audit list ----------
@app.callback(Output("audit-list","children"), Input("audit-log","data"))
def _render_audit(log):
    if not log:
        return [dbc.ListGroupItem("No edits yet.")]
    items=[]
    for i, entry in enumerate(reversed(log)):
        txt=f"[{entry['time']}] Row {entry['row']+1} – {entry['column']}: {entry['old']} → {entry['new']}"
        items.append(
            dbc.ListGroupItem([
                txt,
                dbc.Button("Revert", id={"type":"revert","index":i}, size="sm", color="link", className="float-end")
            ], className="py-1")
        )
    return items

# ---------- Revert edit ----------
@app.callback(Output("audit-log","data",allow_duplicate=True), Input({"type":"revert","index":ALL},"n_clicks"), State("audit-log","data"), State("url-input","value"), prevent_initial_call=True)
def _do_revert(clicks, log, url):
    ctx=dash.callback_context
    if not ctx.triggered or not log:
        raise dash.exceptions.PreventUpdate
    tid=ctx.triggered[0]["prop_id"].split(".")[0]
    import json as _j
    idx=_j.loads(tid)["index"]
    entry=log[-(idx+1)]
    try:
        df=get_df(url)
        df.at[entry['row'], entry['column']]=entry['old']
        update_row(url, entry['row'], df.iloc[entry['row']].tolist())
    except Exception as exc:
        print("[Warning] revert failed",exc)
    log.pop(-(idx+1))
    return log

# ---------- Row select opens detail drawer ----------
@app.callback(
    Output("detail-drawer", "is_open"),
    Output("drawer-body", "children"),
    Input("result-table", "selected_rows"),
    State("data-store", "data"),
    prevent_initial_call=False,
)
def _open_drawer(selected_rows, data_json):
    if not selected_rows:
        return False, dash.no_update
    df = json_to_df(data_json)
    if df is None or selected_rows[0] >= len(df):
        return False, dash.no_update
    row = df.iloc[selected_rows[0]]
    # Determine image source: if 'picture' column contains URL else placeholder
    img_src = None
    if isinstance(row.get("picture"), str) and row.get("picture").startswith("http"):
        img_src = row.get("picture")
    body = []
    if img_src:
        body.append(html.Img(src=img_src, style={"maxWidth": "100%", "marginBottom": "1rem"}))
    for col in df.columns:
        val = row[col]
        body.append(html.P([html.Strong(f"{col}: "), str(val)]))
    return True, body

# ---------- Enable/disable Edit button ----------
@app.callback(
    Output("edit-btn", "disabled"),
    Output("delete-btn", "disabled"),
    Output("restock-btn", "disabled"),
    Input("result-table", "selected_rows"),
)
def _toggle_edit_btn(selected_rows):
    # Disable action buttons when nothing is selected
    disabled = not bool(selected_rows)
    return disabled, disabled, disabled

# ---------- Navigation callbacks ----------
@app.callback(
    Output("dashboard-section", "style"),
    Output("placeholder-section", "style"),
    Output("breadcrumbs", "items"),
    [Input("tab-dashboard", "n_clicks"), Input("tab-products", "n_clicks"), Input("tab-orders", "n_clicks"), Input("tab-reports", "n_clicks")],
    prevent_initial_call=False,
)
def _switch_tabs(n1, n2, n3, n4):
    ctx = dash.callback_context
    if not ctx.triggered:
        tab = "dashboard"
    else:
        tab = ctx.triggered[0]["prop_id"].split(".")[0].replace("tab-", "")
    if tab == "dashboard":
        breadcrumbs = [{"label": "Dashboard", "active": True}]
        return {}, {"display": "none"}, breadcrumbs
    else:
        label = tab.capitalize()
        breadcrumbs = [
            {"label": "Dashboard", "active": False},
            {"label": label, "active": True},
        ]
        return {"display": "none"}, {}, breadcrumbs

# ---------- Undo toast logic ----------
@app.callback(
    Output("undo-toast", "is_open"),
    Output("undo-interval", "disabled"),
    Output("toast-msg", "children"),
    Output("last-action", "data", allow_duplicate=True),
    Input("delete-btn", "n_clicks"),
    Input("restock-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _show_toast(del_clicks, restock_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
    action = "Deleted" if btn_id == "delete-btn" else "Restocked"
    return True, False, f"{action} item – you have 50 s to undo.", {"action": action}

@app.callback(
    Output("undo-toast", "is_open", allow_duplicate=True),
    Output("undo-interval", "disabled", allow_duplicate=True),
    Input("undo-interval", "n_intervals"),
    Input("undo-btn", "n_clicks"),
    State("undo-toast", "is_open"),
    prevent_initial_call=True,
)
def _handle_undo(ticks, undo_clicks, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger == "undo-btn":
        # TODO: implement actual undo logic (reload data or revert backend)
        return False, True
    # interval tick: close after 50s (ticks start at 0)
    if ticks >= 50 and is_open:
        return False, True
    raise dash.exceptions.PreventUpdate

# ---------- Table settings persistence ----------
@app.callback(
    Output("table-settings", "data", allow_duplicate=True),
    Input("result-table", "filter_query"),
    Input("result-table", "sort_by"),
    Input("result-table", "page_current"),
    Input("result-table", "page_size"),
    prevent_initial_call=True,
)
def _save_table_settings(filter_q, sort_by, page_cur, page_size):
    return {
        "filter_query": filter_q,
        "sort_by": sort_by,
        "page_current": page_cur,
        "page_size": page_size,
    }

app.clientside_callback(
    """
    function(settings){
        if(!settings){return ['', [], 0, 20];}
        return [settings.filter_query||'', settings.sort_by||[], settings.page_current||0, settings.page_size||20];
    }
    """,
    Output('result-table','filter_query', allow_duplicate=True),
    Output('result-table','sort_by', allow_duplicate=True),
    Output('result-table','page_current', allow_duplicate=True),
    Output('result-table','page_size', allow_duplicate=True),
    Input('table-settings','data'),
    prevent_initial_call=True,
)

# ---------- Theme toggle ----------
app.clientside_callback(
    """
    function(theme){
        const link=document.getElementById('theme-css');
        if(!link){return ''}
        const base='https://cdn.jsdelivr.net/npm/bootswatch@5.3.2/dist/';
        const map={lux:'lux', darkly:'darkly', flatly:'flatly', cyborg:'cyborg', magenta:'darkly'};
        const css=map[theme]||'lux';
        link.href=`${base}${css}/bootstrap.min.css`;
        document.body.classList.remove('dark-mode','magenta-mode');
        if(theme==='darkly' || theme==='cyborg'){document.body.classList.add('dark-mode');}
        if(theme==='magenta'){document.body.classList.add('magenta-mode');}
        localStorage.setItem('themeName', theme);
        return '';
    }
    """,
    Output('tour-dummy','children', allow_duplicate=True),
    Input('theme-dropdown','value'),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(n){
        const theme=localStorage.getItem('themeName')||'lux';
        return theme;
    }
    """,
    Output('theme-dropdown','value'),
    Input('url-input','value'),
    prevent_initial_call=False,
)

# (global search callback would go here later)

# ---------- Clientside tour launcher (first load) ----------
# ---------- Manual Start Tour button ----------
app.clientside_callback(
    """
    function(n) {
        if (!n) {return '';}
        if (typeof introJs === 'undefined') {return '';}
        introJs().setOptions({
            steps: [
                {element: '#url-input',  intro: 'Paste your Google Sheets link here.', position: 'bottom'},
                {element: '#search-btn', intro: 'Click to search (or press Enter) to find items.', position: 'right'},
                {element: '#result-table', intro: 'Results appear here. Select a row to enable action icons.', position: 'top'},
                {element: '#edit-btn', intro: 'Use these icons to edit, delete, or restock the item.', position: 'left'},
                {element: '#upload-btn', intro: 'Add new items quickly using this form.', position: 'bottom'}
            ],
            nextLabel: 'Next', prevLabel: 'Back', doneLabel: 'Finish'
        }).start();
        return '';
    }
    """,
    Output('tour-dummy', 'children', allow_duplicate=True),
    Input('tour-btn','n_clicks'),
    prevent_initial_call=True,
)

# ---------- Clientside tour launcher on first load ----------
app.clientside_callback(
    """
    function(value) {
        if (typeof introJs === 'undefined') {return ''}
        if (!localStorage.getItem('tourSeen')) {
            introJs().setOptions({
                steps: [
                    {element: '#url-input',  intro: 'Paste your Google Sheets link here.', position: 'bottom'},
                    {element: '#search-btn', intro: 'Click to search (or press Enter) to find items.', position: 'right'},
                    {element: '#result-table', intro: 'Results appear here. Select a row to enable action icons.', position: 'top'},
                    {element: '#edit-btn', intro: 'Use these icons to edit, delete, or restock the item.', position: 'left'},
                    {element: '#upload-btn', intro: 'Add new items quickly using this form.', position: 'bottom'}
                ],
                nextLabel: 'Next', prevLabel: 'Back', doneLabel: 'Finish'
            }).oncomplete(function(){localStorage.setItem('tourSeen','1')})
              .onexit(function(){localStorage.setItem('tourSeen','1')})
              .start();
        }
        return '';
    }
    """,
    Output('tour-dummy', 'children', allow_duplicate=True),
    Input('url-input', 'value'),
    prevent_initial_call=True,
)

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
    if ctx.triggered_id == "cancel-btn" or not selected_rows:
        return False, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    df = json_to_df(data_json)
    if df is None:
        return False, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    row = df.iloc[selected_rows[0]]
    return True, row.get("name"), row.get("qr code"), row.get("picture"), row.get("picture by shelf"), row.get("is it green?"), row.get("notes"), row.get("VISIBLE/ NOT")

# ---------- Inline cell edit save ----------
@app.callback(
    Output("result-table", "data", allow_duplicate=True),
    Input("result-table", "data_timestamp"),
    State("result-table", "data"),
    State("result-table", "data_previous"),
    State("url-input", "value"),
    prevent_initial_call=True,
)
def _inline_save(ts, new_data, old_data, url):
    if ts is None or old_data is None:
        raise dash.exceptions.PreventUpdate
    # find first difference
    for idx, (new_row, old_row) in enumerate(zip(new_data, old_data)):
        if new_row != old_row:
            # validation for boolean columns (Yes/No)
            for col in ["picture", "picture by shelf", "is it green?", "VISIBLE/ NOT"]:
                if col in new_row and new_row[col] not in ("Yes", "No", "yes", "no"):
                    # revert invalid edit
                    new_row[col] = old_row[col]
                    return new_data
            # update backend sheet
            try:
                df_all = get_df(url)
                row_idx = idx  # assuming displayed table includes all rows and not filtered
                df_all.loc[row_idx, new_row.keys()] = list(new_row.values())
                update_row(url, row_idx, df_all.loc[row_idx].tolist())
            except Exception as exc:  # noqa: BLE001
                print("[Warning] Failed to write row:", exc)
            break
    return new_data

# ---------- Save edits back to sheet ----------
@app.callback(
    Output("data-store", "data", allow_duplicate=True),
    Output("edit-modal", "is_open", allow_duplicate=True),
    Output("result-table", "data", allow_duplicate=True),
    Output("result-table", "columns", allow_duplicate=True),
    Output("result-table", "selected_rows", allow_duplicate=True),
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
    State("query-input", "value"),
    State("field-dropdown", "value"),
    prevent_initial_call=True,
)
def _save_row(n_clicks, selected_rows, url, name, qr, picture, shelfpic, green, notes, visible, query, field):
    if n_clicks == 0 or not selected_rows:
        raise dash.exceptions.PreventUpdate
    # Determine the actual sheet row corresponding to the selected row in the (possibly) filtered table
    df_all = get_df(url)
    if query:
        current_view = search(df_all, query, field=field)
    else:
        current_view = df_all

    # selected_rows index refers to the position within the current view, so map it back to df_all index
    row_idx = current_view.index[selected_rows[0]]  # 0-based index within the Google Sheet
    df = df_all.copy()
    # apply edits
    # apply edits to the correct row in the full DataFrame
    df.at[row_idx, "name"] = name
    df.at[row_idx, "qr code"] = qr
    df.at[row_idx, "picture"] = picture
    df.at[row_idx, "picture by shelf"] = shelfpic
    df.at[row_idx, "is it green?"] = green
    df.at[row_idx, "notes"] = notes
    df.at[row_idx, "VISIBLE/ NOT"] = visible

    # write single row to sheet
    try:
        row_vals = [str(v) if hasattr(v, 'dtype') or isinstance(v, (int, float)) else v for v in df.iloc[row_idx].tolist()]
        update_row(url, row_idx, row_vals)
    except Exception as exc:  # noqa: BLE001
        print("[Warning] Failed to write row:", exc)

    # after write, reflect updates in df (already modified above) and prepare table data
    if query:
        result = search(df, query, field=field)
    else:
        result = df
    cols = [c for c in DEFAULT_COLUMNS if c in result.columns]
    if not cols:
        cols = list(result.columns)
    table_data = current_view.assign(**df.loc[current_view.index][cols]).to_dict("records") if query else df[cols].to_dict("records")
    table_cols = [{"name": c, "id": c} for c in cols]
    return df_to_json(df), False, table_data, table_cols, []

# ---------- Refresh table when store changes ----------
@app.callback(
    Output("result-table", "data", allow_duplicate=True),
    Output("result-table", "columns", allow_duplicate=True),
    Input("data-store", "data"),
    State("query-input", "value"),
    State("field-dropdown", "value"),
    prevent_initial_call=True,
)
def _refresh_table(data_json, query, field):
    if not data_json:
        raise dash.exceptions.PreventUpdate
    df = json_to_df(data_json)
    if df is None:
        raise dash.exceptions.PreventUpdate
    if query:
        result = search(df, query, field=field)
    else:
        result = df
    cols = [c for c in DEFAULT_COLUMNS if c in result.columns]
    if not cols:
        cols = list(result.columns)
    return result[cols].to_dict("records"), [{"name": c, "id": c} for c in cols]

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