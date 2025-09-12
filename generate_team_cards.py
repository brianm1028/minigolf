#!/usr/bin/env python3
"""
Team Card QR Code Generator

This script retrieves team information from the main API and uses the
tournament API to generate QR codes, then creates 5"x7" PDF cards for each team.
"""

import os
import sys
import json
import base64
import requests
import logging
from datetime import datetime
from pathlib import Path

# PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black, white

import io
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Configuration
TOURNAMENT_API_BASE = os.getenv('TOURNAMENT_API_BASE', 'http://localhost:8000/tournament')
MAIN_API_BASE = os.getenv('ADMIN_API_BASE', 'http://localhost:8000')
API_TIMEOUT = 30

# PDF Configuration
CARD_WIDTH = 5 * inch  # 5 inches
CARD_HEIGHT = 7 * inch  # 7 inches
MARGIN = 0.25 * inch

class TeamCardGenerator:
    def __init__(self):
        self.output_dir = Path('teamcards')
        self.tournament_api = TOURNAMENT_API_BASE
        self.main_api = MAIN_API_BASE
        self.setup_api_connections()
        self.setup_output_directory()

    def setup_api_connections(self):
        """Test connections to both APIs"""
        # Test tournament API
        try:
            response = requests.get(f'{self.tournament_api}/health', timeout=5)
            if response.status_code == 200:
                logger.info(f"Successfully connected to tournament API at {self.tournament_api}")
            else:
                logger.warning(f"Tournament API responded with status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to connect to tournament API: {e}")
            logger.error(f"Make sure tournament_app.py is running at {self.tournament_api}")
            sys.exit(1)

        # Test main API
        try:
            response = requests.get(f'{self.main_api}/health', timeout=5)
            if response.status_code == 200:
                logger.info(f"Successfully connected to main API at {self.main_api}")
            else:
                logger.warning(f"Main API responded with status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to connect to main API: {e}")
            logger.error(f"Make sure main.py is running at {self.main_api}")
            sys.exit(1)

    def setup_output_directory(self):
        """Create output directory if it doesn't exist"""
        self.output_dir.mkdir(exist_ok=True)
        logger.info(f"Output directory: {self.output_dir.absolute()}")

    def get_teams_from_main_api(self):
        """Get list of all teams from main API"""
        try:
            response = requests.get(f'{self.main_api}/teams', timeout=API_TIMEOUT)

            if response.status_code == 200:
                teams_data = response.json()
                logger.info(f"Retrieved {len(teams_data)} teams from main API")
                return teams_data
            else:
                logger.error(f"Main API returned status {response.status_code} for teams")
                return []

        except requests.RequestException as e:
            logger.error(f"Error getting teams from main API: {e}")
            return []

    def get_team_qr_from_tournament_api(self, team_number):
        """Get QR code and team data from tournament API"""
        try:
            response = requests.post(
                f'{self.tournament_api}/generate-team-card',
                json={'team_number': team_number},
                headers={'Content-Type': 'application/json'},
                timeout=API_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()

                if 'qr_code_base64' in data and 'encoded_data' in data:
                    # Decode base64 QR code image
                    qr_image_data = base64.b64decode(data['qr_code_base64'])
                    qr_image_buffer = io.BytesIO(qr_image_data)

                    # Parse team data from encoded_data
                    team_info = data['encoded_data']

                    return qr_image_buffer, team_info
                else:
                    logger.error(f"Tournament API response missing QR code data for team {team_name}")
                    return None, None
            else:
                logger.error(f"Tournament API error {response.status_code} for team {team_name}")
                if response.text:
                    logger.error(f"Response: {response.text}")
                return None, None

        except requests.RequestException as e:
            logger.error(f"Network error getting QR code for team {team_name}: {e}")
            return None, None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding tournament API response for team {team_name}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error getting QR code for team {team_name}: {e}")
            return None, None

    def get_all_teams_with_qr(self):
        """Get all teams from main API and their QR codes from tournament API"""
        all_teams = []

        # Get teams from main API
        teams = self.get_teams_from_main_api()
        if not teams:
            logger.error("No teams found from main API")
            return []

        # Process each team
        for team in teams:
            team_name = team.get('name', 'Unknown Team')
            team_number = team.get('number', team.get('team_number', 0))

            logger.info(f"Processing team: {team_name} (#{team_number})")

            try:
                # Get QR code and detailed team data from tournament API
                qr_buffer, detailed_team_data = self.get_team_qr_from_tournament_api(team_number)

                if qr_buffer and detailed_team_data:
                    # Combine main API data with tournament API data
                    combined_team_data = {
                        'team_name': team_name,
                        'team_number': team_number,
                        'players': detailed_team_data.get('players', []),
                        'tournaments': detailed_team_data.get('tournaments', []),
                        'generated_at': detailed_team_data.get('generated_at', ''),
                        'qr_code_buffer': qr_buffer
                    }
                    all_teams.append(combined_team_data)
                    logger.info(f"Successfully processed team {team_name}")
                else:
                    logger.warning(f"Could not get QR code for team {team_name}")

            except Exception as e:
                logger.error(f"Error processing team {team_name}: {e}")
                continue

        logger.info(f"Successfully processed {len(all_teams)} teams total")
        return all_teams

    def get_specific_teams_with_qr(self, team_names):
        """Get specific teams only"""
        all_teams = []

        # Get all teams from main API first
        all_available_teams = self.get_teams_from_main_api()
        if not all_available_teams:
            logger.error("No teams found from main API")
            return []

        # Filter for requested teams
        for team_name in team_names:
            # Find team in available teams
            team_found = False
            for team in all_available_teams:
                if team.get('name', '').lower() == team_name.lower():
                    team_found = True
                    team_number = team.get('number', team.get('team_number', 0))

                    logger.info(f"Processing specified team: {team_name} (#{team_number})")

                    try:
                        # Get QR code and detailed team data from tournament API
                        qr_buffer, detailed_team_data = self.get_team_qr_from_tournament_api(team_number)

                        if qr_buffer and detailed_team_data:
                            # Combine main API data with tournament API data
                            combined_team_data = {
                                'team_name': team_name,
                                'team_number': team_number,
                                'players': detailed_team_data.get('players', []),
                                'tournaments': detailed_team_data.get('tournaments', []),
                                'generated_at': detailed_team_data.get('generated_at', ''),
                                'qr_code_buffer': qr_buffer
                            }
                            all_teams.append(combined_team_data)
                            logger.info(f"Successfully processed team {team_name}")
                        else:
                            logger.warning(f"Could not get QR code for team {team_name}")

                    except Exception as e:
                        logger.error(f"Error processing team {team_name}: {e}")
                    break

            if not team_found:
                logger.warning(f"Team '{team_name}' not found in available teams")

        logger.info(f"Successfully processed {len(all_teams)} teams for specified teams")
        return all_teams

    def create_team_card_pdf(self, team_data, qr_image_buffer):
        """Create a 5x7 inch PDF card for a team"""
        try:
            # Create filename
            team_name_safe = "".join(c for c in team_data['team_name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"team_card_{team_name_safe}_#{team_data['team_number']:03d}.pdf"
            filepath = self.output_dir / filename

            # Create PDF canvas
            c = canvas.Canvas(str(filepath), pagesize=(CARD_WIDTH, CARD_HEIGHT))

            # Colors
            primary_color = HexColor('#1B4332')  # Dark Green
            secondary_color = HexColor('#2D6A4F')  # Medium Green  
            accent_color = HexColor('#40916C')  # Light Green
            text_color = HexColor('#081C15')  # Very Dark Green
            highlight_color = HexColor('#F1C40F')  # Gold

            # Background
            c.setFillColor(white)
            c.rect(0, 0, CARD_WIDTH, CARD_HEIGHT, fill=1)

            # Header background
            c.setFillColor(primary_color)
            c.rect(0, CARD_HEIGHT - 1.8*inch, CARD_WIDTH, 1.8*inch, fill=1)

            # Team name
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 18)
            team_name_text = team_data['team_name']
            text_width = c.stringWidth(team_name_text, "Helvetica-Bold", 18)
            c.drawString((CARD_WIDTH - text_width) / 2, CARD_HEIGHT - 0.5*inch, team_name_text)

            # Team number - large display
            c.setFont("Helvetica-Bold", 56)
            team_number_text = f"#{team_data['team_number']}"
            text_width = c.stringWidth(team_number_text, "Helvetica-Bold", 56)
            c.drawString((CARD_WIDTH - text_width) / 2, CARD_HEIGHT - 1.4*inch, team_number_text)

            # Player count information
            player_count = len(team_data.get('players', []))
            c.setFillColor(accent_color)
            info_y = CARD_HEIGHT - 2.1*inch
            c.rect(MARGIN, info_y - 0.25*inch, CARD_WIDTH - 2*MARGIN, 0.5*inch, fill=1)

            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 16)
            players_text = f"{player_count} Players"
            text_width = c.stringWidth(players_text, "Helvetica-Bold", 16)
            c.drawString((CARD_WIDTH - text_width) / 2, info_y - 0.05*inch, players_text)

            # Player Names Section
            players = team_data.get('players', [])
            if players:
                c.setFillColor(text_color)
                c.setFont("Helvetica", 11)

                # Start position for player names
                players_start_y = info_y - 0.6*inch
                current_y = players_start_y

                # Calculate available width for player names (with margins)
                available_width = CARD_WIDTH - 2 * MARGIN

                # Display player names with numbers
                players_per_line = 2  # Two players per line for better readability
                line_height = 0.15*inch

                for i, player in enumerate(players[:8]):  # Limit to 8 players to fit on card
                    player_name = player.get('name', 'Unknown Player')
                    player_number = player.get('number', 'N/A')

                    # Format: "Name (#123)"
                    player_text = f"{player_name} (#{player_number})"

                    # Truncate if too long
                    max_char_per_name = 20  # Adjust based on font size
                    if len(player_text) > max_char_per_name:
                        truncated_name = player_name[:15] + "..."
                        player_text = f"{truncated_name} (#{player_number})"

                    # Position calculation
                    if i % players_per_line == 0:
                        # Left column
                        x_pos = MARGIN + 0.1*inch
                    else:
                        # Right column
                        x_pos = CARD_WIDTH / 2 + 0.1*inch

                    # Draw player name
                    c.drawString(x_pos, current_y, player_text)

                    # Move to next line after every 2 players
                    if i % players_per_line == 1:
                        current_y -= line_height

                # Show "and X more..." if there are more than 8 players
                if len(players) > 8:
                    c.setFont("Helvetica-Oblique", 9)
                    more_text = f"...and {len(players) - 8} more players"
                    text_width = c.stringWidth(more_text, "Helvetica-Oblique", 9)
                    c.drawString((CARD_WIDTH - text_width) / 2, current_y - 0.1*inch, more_text)
                    current_y -= 0.15*inch

            # QR Code (repositioned to accommodate player names)
            if qr_image_buffer:
                qr_size = 1.8 * inch  # Slightly smaller to fit more content
                qr_x = (CARD_WIDTH - qr_size) / 2

                # Position QR code based on available space
                if players:
                    qr_y = max(current_y - qr_size - 0.2*inch, 0.8*inch)  # Ensure minimum bottom margin
                else:
                    qr_y = 1.2 * inch  # Default position if no players

                # QR code background
                c.setFillColor(white)
                c.rect(qr_x - 0.1*inch, qr_y - 0.1*inch, qr_size + 0.2*inch, qr_size + 0.2*inch, fill=1)
                c.setStrokeColor(primary_color)
                c.setLineWidth(3)
                c.rect(qr_x - 0.1*inch, qr_y - 0.1*inch, qr_size + 0.2*inch, qr_size + 0.2*inch, fill=0)

                image = Image.open(qr_image_buffer)
                # Draw QR code
                c.drawInlineImage(image, qr_x, qr_y, qr_size, qr_size)

                # QR code label
                c.setFillColor(text_color)
                c.setFont("Helvetica-Bold", 10)
                label_text = "SCAN TO LOAD TEAM"
                text_width = c.stringWidth(label_text, "Helvetica-Bold", 10)
                c.drawString((CARD_WIDTH - text_width) / 2, qr_y - 0.25*inch, label_text)

            # Tournament information (if available and space permits)
            tournaments = team_data.get('tournaments', [])
            tournament_y_position = qr_y - 0.35*inch

            # Only show tournaments if there's enough space (avoid overlapping with footer)
            if tournaments and tournament_y_position > 0.6*inch:
                c.setFillColor(text_color)
                c.setFont("Helvetica", 9)

                # Show first tournament only to save space
                tournament = tournaments[0]
                tournament_name = tournament.get('tournament_name', 'Unknown Tournament')

                # Truncate tournament name if too long
                max_tournament_length = 35
                if len(tournament_name) > max_tournament_length:
                    tournament_name = tournament_name[:max_tournament_length] + "..."

                text_width = c.stringWidth(tournament_name, "Helvetica", 9)
                c.drawString((CARD_WIDTH - text_width) / 2, tournament_y_position, tournament_name)

                # Show count if multiple tournaments
                if len(tournaments) > 1:
                    more_text = f"(+{len(tournaments) - 1} more)"
                    text_width = c.stringWidth(more_text, "Helvetica", 8)
                    c.setFont("Helvetica", 8)
                    c.drawString((CARD_WIDTH - text_width) / 2, tournament_y_position - 0.12*inch, more_text)

            # Footer
            c.setFillColor(HexColor('#666666'))
            c.setFont("Helvetica", 8)
            footer_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Team ID: {team_data.get('team_number', 'N/A')}"
            c.drawString(MARGIN, 0.2*inch, footer_text)

            # Add a decorative border
            c.setStrokeColor(secondary_color)
            c.setLineWidth(2)
            c.rect(MARGIN/2, MARGIN/2, CARD_WIDTH - MARGIN, CARD_HEIGHT - MARGIN, fill=0)

            # Save PDF
            c.save()
            logger.info(f"Created team card: {filename}")
            return filepath

        except Exception as e:
            logger.error(f"Error creating PDF for team {team_data['team_name']}: {e}")
            return None

    def generate_all_cards(self):
        """Generate team cards for all teams using both main and tournament APIs"""
        logger.info("Starting team card generation using main and tournament APIs...")

        # Get all teams with QR codes
        teams = self.get_all_teams_with_qr()

        if not teams:
            logger.error("No teams found via APIs. Please check:")
            logger.error("1. Main API is running and accessible")
            logger.error("2. Tournament API is running and accessible") 
            logger.error("3. Database contains Team data")
            logger.error("4. API endpoints are working correctly")
            return

        successful = 0
        failed = 0

        for team_data in teams:
            try:
                logger.info(f"Creating PDF for {team_data['team_name']} (#{team_data['team_number']})")

                # Use QR code buffer from team data
                qr_image_buffer = team_data.get('qr_code_buffer')

                if not qr_image_buffer:
                    logger.warning(f"No QR code available for team {team_data['team_name']}")
                    failed += 1
                    continue

                # Create PDF
                pdf_path = self.create_team_card_pdf(team_data, qr_image_buffer)
                if pdf_path:
                    successful += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"Error processing team {team_data['team_name']}: {e}")
                failed += 1

        logger.info(f"Team card generation complete!")
        logger.info(f"Successfully created: {successful} cards")
        logger.info(f"Failed: {failed} cards")
        logger.info(f"Output directory: {self.output_dir.absolute()}")

    def generate_specific_cards(self, team_names):
        """Generate cards for specific teams only"""
        logger.info(f"Generating cards for specific teams: {', '.join(team_names)}")

        teams = self.get_specific_teams_with_qr(team_names)

        if not teams:
            logger.error("No teams found for specified team names")
            return

        successful = 0
        failed = 0

        for team_data in teams:
            try:
                logger.info(f"Creating PDF for {team_data['team_name']} (#{team_data['team_number']})")

                # Use QR code buffer from team data
                qr_image_buffer = team_data.get('qr_code_buffer')

                if not qr_image_buffer:
                    failed += 1
                    continue

                # Create PDF
                pdf_path = self.create_team_card_pdf(team_data, qr_image_buffer)
                if pdf_path:
                    successful += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"Error processing team {team_data['team_name']}: {e}")
                failed += 1

        logger.info(f"Specific team card generation complete!")
        logger.info(f"Successfully created: {successful} cards")
        logger.info(f"Failed: {failed} cards")

    def list_available_teams(self):
        """List all available teams from main API"""
        logger.info("Fetching available teams...")

        teams = self.get_teams_from_main_api()

        if teams:
            logger.info("Available teams:")
            for team in teams:
                team_name = team.get('name', 'Unknown Team')
                team_number = team.get('number', team.get('team_number', 'N/A'))
                logger.info(f"  - {team_name} (#{team_number})")
            return [team.get('name', 'Unknown Team') for team in teams]
        else:
            logger.info("No teams found")
            return []

    def close(self):
        """Cleanup (no database connection to close)"""
        pass

def main():
    """Main function"""
    try:
        generator = TeamCardGenerator()

        # Check for command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == '--help' or sys.argv[1] == '-h':
                print("Team Card Generator")
                print("Usage:")
                print("  python generate_team_cards.py                    # Generate cards for all teams")
                print("  python generate_team_cards.py --list-teams       # List available teams")
                print("  python generate_team_cards.py --teams [names]    # Generate cards for specific teams")
                print("  python generate_team_cards.py --help             # Show this help")
                print()
                print("Examples:")
                print("  python generate_team_cards.py --teams 'Thunder Hawks' 'Lightning Bolts'")
                print()
                print("Configuration:")
                print(f"  Tournament API: {TOURNAMENT_API_BASE}")
                print(f"  Main API: {MAIN_API_BASE}")
                print("  Set TOURNAMENT_API_BASE and MAIN_API_BASE environment variables to change URLs")
                return

            elif sys.argv[1] == '--list-teams':
                # List available teams
                available_teams = generator.list_available_teams()
                if available_teams:
                    print("\nTo generate cards for specific teams, use:")
                    teamlist = ' '.join([f"'{team}'" for team in available_teams[:3]])
                    print(f"python generate_team_cards.py --teams {teamlist}")
                return

            elif sys.argv[1] == '--teams':
                # Generate cards for specific teams
                if len(sys.argv) < 3:
                    logger.error("Please specify team names after --teams")
                    logger.error("Use --list-teams to see available teams")
                    sys.exit(1)

                team_names = sys.argv[2:]
                logger.info(f"Generating cards for specified teams: {', '.join(team_names)}")
                generator.generate_specific_cards(team_names)

            else:
                logger.error(f"Unknown argument: {sys.argv[1]}")
                logger.error("Use --help for usage information")
                sys.exit(1)
        else:
            # Generate cards for all teams
            generator.generate_all_cards()

        generator.close()

    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
