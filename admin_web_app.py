import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import requests
import json
import base64
import io
from datetime import datetime, timedelta
import yagmail
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import inch
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API endpoints
BASE_API_URL = "http://localhost:8000"
TOURNAMENT_API_URL = "http://localhost:8000/tournament"

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "Minigolf Tournament Admin"

# Navigation bar
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Entities", href="/entities")),
        dbc.NavItem(dbc.NavLink("Tournament Control", href="/tournament")),
        dbc.NavItem(dbc.NavLink("Team Management", href="/teams")),
        dbc.NavItem(dbc.NavLink("Cards", href="/cards")),
        dbc.NavItem(dbc.NavLink("Leaderboards", href="/leaderboards")),
        dbc.NavItem(dbc.NavLink("Scorecards", href="/scorecards")),
    ],
    brand="Minigolf Tournament Admin",
    brand_href="/",
    color="primary",
    dark=True,
)

# Layout
app.layout = dbc.Container([
    dcc.Location(id="url", refresh=False),
    navbar,
    html.Div(id="page-content", style={"margin-top": "20px"}),
    dcc.Interval(id="leaderboard-refresh", interval=30000, disabled=True),
    dcc.Store(id="refresh-settings", data={"interval": 30000, "enabled": False}),
])

# Home page
def create_home_page():
    return dbc.Container([
        html.H1("Minigolf Tournament Administration", className="text-center mb-4"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Entity Management", className="card-title"),
                        html.P("Manage all tournament entities and relationships"),
                        dbc.Button("Go to Entities", color="primary", href="/entities")
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Tournament Control", className="card-title"),
                        html.P("Start, stop, and manage tournaments"),
                        dbc.Button("Go to Tournament", color="success", href="/tournament")
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Team Management", className="card-title"),
                        html.P("Manage teams and assign players"),
                        dbc.Button("Go to Teams", color="info", href="/teams")
                    ])
                ])
            ], width=4),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Cards & PDFs", className="card-title"),
                        html.P("Generate printable team and hole cards"),
                        dbc.Button("Go to Cards", color="warning", href="/cards")
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Leaderboards", className="card-title"),
                        html.P("View team and player rankings"),
                        dbc.Button("Go to Leaderboards", color="secondary", href="/leaderboards")
                    ])
                ])
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Scorecards", className="card-title"),
                        html.P("View and manage scorecards"),
                        dbc.Button("Go to Scorecards", color="dark", href="/scorecards")
                    ])
                ])
            ], width=4),
        ])
    ])

# Entity management page
def create_entity_page():
    return dbc.Container([
        html.H2("Entity Management"),
        dbc.Tabs([
            dbc.Tab(label="Players", tab_id="players"),
            dbc.Tab(label="Teams", tab_id="teams"),
            dbc.Tab(label="Tournaments", tab_id="tournaments"),
            dbc.Tab(label="Locations", tab_id="locations"),
            dbc.Tab(label="Courses", tab_id="courses"),
            dbc.Tab(label="Holes", tab_id="holes"),
            dbc.Tab(label="Departments", tab_id="departments"),
            dbc.Tab(label="Relationships", tab_id="relationships"),
        ], id="entity-tabs", active_tab="players"),
        html.Div(id="entity-content", style={"margin-top": "20px"}),
    ])

# Tournament control page
def create_tournament_page():
    return dbc.Container([
        html.H2("Tournament Control"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Tournament Selection"),
                        dcc.Dropdown(id="tournament-dropdown", placeholder="Select Tournament"),
                        html.Div(id="tournament-status", style={"margin-top": "10px"}),
                    ])
                ])
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Tournament Actions"),
                        dbc.ButtonGroup([
                            dbc.Button("Start Tournament", id="start-tournament-btn", color="success"),
                            dbc.Button("End Tournament", id="end-tournament-btn", color="danger"),
                            dbc.Button("Update Leaderboard", id="update-leaderboard-btn", color="primary"),
                        ]),
                        html.Div(id="tournament-action-result", style={"margin-top": "10px"}),
                    ])
                ])
            ], width=6),
        ])
    ])

# Team management page with drag and drop
def create_team_management_page():
    return dbc.Container([
        html.H2("Team Management"),
        dbc.Row([
            dbc.Col([
                html.H4("Available Players"),
                html.Div(id="available-players", style={
                    "border": "2px dashed #ccc",
                    "min-height": "400px",
                    "padding": "10px",
                    "margin-bottom": "20px"
                }),
            ], width=6),
            dbc.Col([
                html.H4("Teams"),
                html.Div(id="team-containers", style={"margin-bottom": "20px"}),
                dbc.Button("Refresh Teams", id="refresh-teams-btn", color="primary"),
            ], width=6),
        ]),
        html.Div(id="team-update-result"),
    ])

# Cards generation page
def create_cards_page():
    return dbc.Container([
        html.H2("Card Generation"),
        dbc.Tabs([
            dbc.Tab(label="Team Cards", tab_id="team-cards"),
            dbc.Tab(label="Hole Cards", tab_id="hole-cards"),
        ], id="cards-tabs", active_tab="team-cards"),
        html.Div(id="cards-content", style={"margin-top": "20px"}),
    ])

# Leaderboards page
def create_leaderboards_page():
    return dbc.Container([
        html.H2("Leaderboards"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Controls"),
                        dcc.Dropdown(
                            id="leaderboard-tournament-dropdown",
                            placeholder="Select Tournament"
                        ),
                        html.Br(),
                        dbc.Button("Update Leaderboard", id="manual-update-btn", color="primary"),
                        html.Br(),
                        html.Label("Auto Refresh:"),
                        dcc.Dropdown(
                            id="refresh-interval-dropdown",
                            options=[
                                {"label": "Never", "value": 0},
                                {"label": "Every 5 seconds", "value": 5000},
                                {"label": "Every 30 seconds", "value": 30000},
                                {"label": "Every 1 minute", "value": 60000},
                                {"label": "Every 5 minutes", "value": 300000},
                            ],
                            value=0
                        ),
                    ])
                ])
            ], width=3),
            dbc.Col([
                dbc.Tabs([
                    dbc.Tab(label="Team Leaderboard", tab_id="team-leaderboard"),
                    dbc.Tab(label="Player Leaderboard", tab_id="player-leaderboard"),
                ], id="leaderboard-tabs", active_tab="team-leaderboard"),
                html.Div(id="leaderboard-content"),
            ], width=9),
        ])
    ])

# Scorecards page
def create_scorecards_page():
    return dbc.Container([
        html.H2("Scorecards"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Tournament Selection"),
                        dcc.Dropdown(id="scorecard-tournament-dropdown", placeholder="Select Tournament"),
                        html.Br(),
                        dbc.Button("Generate PDF Scorecards", id="generate-scorecards-btn", color="primary"),
                        html.Br(),
                        html.Label("Email Settings:"),
                        dbc.Input(id="email-user", placeholder="Gmail Username", type="text"),
                        dbc.Input(id="email-pass", placeholder="Gmail App Password", type="password"),
                        dbc.Button("Email Scorecards", id="email-scorecards-btn", color="success"),
                    ])
                ])
            ], width=3),
            dbc.Col([
                html.Div(id="scorecards-display"),
            ], width=9),
        ])
    ])

# Utility functions
def make_api_request(method, endpoint, data=None):
    """Make API request to the backend services"""
    try:
        url = f"{BASE_API_URL}{endpoint}" if not endpoint.startswith("/tournament") else f"{TOURNAMENT_API_URL}{endpoint[11:]}"

        if method.upper() == "GET":
            response = requests.get(url)
        elif method.upper() == "POST":
            response = requests.post(url, json=data)
        elif method.upper() == "PUT":
            response = requests.put(url, json=data)
        elif method.upper() == "DELETE":
            response = requests.delete(url)

        if response.status_code in [200, 201]:
            return response.json()
        else:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"API request error: {e}")
        return None

def generate_pdf_card(card_type, data, qr_code_base64):
    """Generate PDF card with QR code"""
    buffer = io.BytesIO()

    # Create PDF with custom size (8.5" x 5.5")
    c = canvas.Canvas(buffer, pagesize=(8.5*inch, 5.5*inch))

    # Add title
    c.setFont("Helvetica-Bold", 24)
    if card_type == "team":
        title = f"Team: {data.get('team_name', 'Unknown')}"
    else:
        title = f"Hole {data.get('hole_number', '?')}: {data.get('hole_name', 'Unknown')}"

    c.drawString(0.5*inch, 4.5*inch, title)

    # Add QR code
    if qr_code_base64:
        qr_image_data = base64.b64decode(qr_code_base64)
        qr_image = ImageReader(io.BytesIO(qr_image_data))
        c.drawImage(qr_image, 5.5*inch, 1*inch, width=2.5*inch, height=2.5*inch)

    # Add details
    c.setFont("Helvetica", 12)
    y_pos = 3.5*inch

    if card_type == "team":
        c.drawString(0.5*inch, y_pos, f"Team Number: {data.get('team_number', 'N/A')}")
        y_pos -= 0.3*inch
        if data.get('players'):
            c.drawString(0.5*inch, y_pos, "Players:")
            y_pos -= 0.2*inch
            for player in data.get('players', [])[:10]:  # Limit to 10 players
                c.drawString(0.7*inch, y_pos, f"• {player.get('name', 'Unknown')} (#{player.get('number', 'N/A')})")
                y_pos -= 0.2*inch
    else:
        c.drawString(0.5*inch, y_pos, f"Course: {data.get('course_name', 'N/A')}")
        y_pos -= 0.3*inch
        c.drawString(0.5*inch, y_pos, f"Par: {data.get('hole_par', 'N/A')}")
        y_pos -= 0.3*inch
        c.drawString(0.5*inch, y_pos, f"Location: {data.get('location_name', 'N/A')}")

    c.save()
    buffer.seek(0)
    return buffer

def generate_scorecard_pdf(team_data, course_data, scores_data):
    """Generate PDF scorecard for a team"""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 750, f"Scorecard - Team: {team_data.get('name', 'Unknown')}")

    # Course info
    c.setFont("Helvetica", 12)
    c.drawString(50, 720, f"Course: {course_data.get('name', 'Unknown')} (Par: {course_data.get('par', 'N/A')})")

    # Table headers
    c.setFont("Helvetica-Bold", 10)
    headers = ["Hole", "Name", "Par"] + [f"Player {i+1}" for i in range(4)]
    x_positions = [50, 100, 150, 200, 250, 300, 350]

    y_pos = 680
    for i, header in enumerate(headers):
        if i < len(x_positions):
            c.drawString(x_positions[i], y_pos, header)

    # Draw table lines
    c.line(45, y_pos-10, 400, y_pos-10)

    # Table data
    c.setFont("Helvetica", 9)
    y_pos -= 25

    for hole_num in range(1, 19):  # 18 holes
        hole_info = next((h for h in course_data.get('holes', []) if h.get('number') == hole_num), {})
        c.drawString(x_positions[0], y_pos, str(hole_num))
        c.drawString(x_positions[1], y_pos, hole_info.get('name', f'Hole {hole_num}'))
        c.drawString(x_positions[2], y_pos, str(hole_info.get('par', 3)))

        # Player scores
        for i in range(4):
            score = scores_data.get(f'hole_{hole_num}_player_{i+1}', '')
            if i+3 < len(x_positions):
                c.drawString(x_positions[i+3], y_pos, str(score))

        y_pos -= 15
        if y_pos < 100:  # New page if needed
            c.showPage()
            y_pos = 750

    c.save()
    buffer.seek(0)
    return buffer

# Callbacks

@app.callback(Output("page-content", "children"), [Input("url", "pathname")])
def display_page(pathname):
    if pathname == "/entities":
        return create_entity_page()
    elif pathname == "/tournament":
        return create_tournament_page()
    elif pathname == "/teams":
        return create_team_management_page()
    elif pathname == "/cards":
        return create_cards_page()
    elif pathname == "/leaderboards":
        return create_leaderboards_page()
    elif pathname == "/scorecards":
        return create_scorecards_page()
    else:
        return create_home_page()

@app.callback(
    Output("tournament-dropdown", "options"),
    [Input("tournament-dropdown", "id")]
)
def update_tournament_options(_):
    tournaments = make_api_request("GET", "/tournaments")
    if tournaments:
        return [{"label": t["name"], "value": t["name"]} for t in tournaments]
    return []

@app.callback(
    [Output("start-tournament-btn", "disabled"),
     Output("end-tournament-btn", "disabled"),
     Output("tournament-status", "children")],
    [Input("tournament-dropdown", "value")]
)
def update_tournament_controls(tournament_name):
    if not tournament_name:
        return True, True, ""

    # Check tournament status (simplified - would need more complex logic)
    return False, False, f"Selected: {tournament_name}"

@app.callback(
    Output("tournament-action-result", "children"),
    [Input("start-tournament-btn", "n_clicks"),
     Input("end-tournament-btn", "n_clicks"),
     Input("update-leaderboard-btn", "n_clicks")],
    [State("tournament-dropdown", "value")]
)
def handle_tournament_actions(start_clicks, end_clicks, update_clicks, tournament_name):
    if not tournament_name:
        return ""

    ctx = callback_context
    if not ctx.triggered:
        return ""

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if button_id == "start-tournament-btn":
        result = make_api_request("POST", "/tournament/start-tournament", {"tournament_name": tournament_name})
        if result:
            return dbc.Alert(f"Tournament started: {result['message']}", color="success")
    elif button_id == "end-tournament-btn":
        result = make_api_request("POST", "/tournament/end-tournament", {"tournament_name": tournament_name})
        if result:
            return dbc.Alert(f"Tournament ended: {result['message']}", color="info")
    elif button_id == "update-leaderboard-btn":
        result = make_api_request("POST", "/tournament/update-leaderboard")
        if result:
            return dbc.Alert(f"Leaderboard updated: {result['message']}", color="success")

    return dbc.Alert("Action failed", color="danger")

@app.callback(
    [Output("leaderboard-tournament-dropdown", "options"),
     Output("scorecard-tournament-dropdown", "options")],
    [Input("url", "pathname")]
)
def update_all_tournament_dropdowns(pathname):
    tournaments = make_api_request("GET", "/tournaments")
    options = []
    if tournaments:
        options = [{"label": t["name"], "value": t["name"]} for t in tournaments]
    return options, options

@app.callback(
    Output("leaderboard-content", "children"),
    [Input("leaderboard-tabs", "active_tab"),
     Input("leaderboard-tournament-dropdown", "value"),
     Input("manual-update-btn", "n_clicks"),
     Input("leaderboard-refresh", "n_intervals")]
)
def update_leaderboard_content(active_tab, tournament_name, update_clicks, n_intervals):
    if not tournament_name:
        return html.P("Please select a tournament")

    if active_tab == "team-leaderboard":
        data = make_api_request("GET", f"/tournament/team-leaderboard/{tournament_name}")
        if data:
            df = pd.DataFrame(data)
            return dash_table.DataTable(
                data=df.to_dict('records'),
                columns=[{"name": i, "id": i} for i in df.columns],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left'}
            )
    else:
        data = make_api_request("GET", f"/tournament/player-leaderboard/{tournament_name}")
        if data:
            df = pd.DataFrame(data)
            return dash_table.DataTable(
                data=df.to_dict('records'),
                columns=[{"name": i, "id": i} for i in df.columns],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left'}
            )

    return html.P("No data available")

@app.callback(
    [Output("leaderboard-refresh", "interval"),
     Output("leaderboard-refresh", "disabled")],
    [Input("refresh-interval-dropdown", "value")]
)
def update_refresh_interval(interval_value):
    if interval_value == 0:
        return 30000, True  # Disabled
    return interval_value, False

@app.callback(
    Output("cards-content", "children"),
    [Input("cards-tabs", "active_tab")]
)
def update_cards_content(active_tab):
    if active_tab == "team-cards":
        teams = make_api_request("GET", "/teams")
        if teams:
            options = [{"label": t["name"], "value": t["name"]} for t in teams]
            return html.Div([
                dcc.Dropdown(id="team-card-dropdown", options=options, placeholder="Select Team"),
                html.Br(),
                dbc.Button("Generate Team Card PDF", id="generate-team-card-btn", color="primary"),
                html.Div(id="team-card-result")
            ])
    else:
        courses = make_api_request("GET", "/courses")
        if courses:
            course_options = [{"label": c["name"], "value": c["name"]} for c in courses]
            return html.Div([
                dcc.Dropdown(id="hole-card-course-dropdown", options=course_options, placeholder="Select Course"),
                dbc.Input(id="hole-card-number-input", placeholder="Hole Number", type="number"),
                html.Br(),
                dbc.Button("Generate Hole Card PDF", id="generate-hole-card-btn", color="primary"),
                html.Div(id="hole-card-result")
            ])
    return html.P("No data available")

if __name__ == "__main__":
    app.run(debug=True, port=8002)
