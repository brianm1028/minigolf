#!/usr/bin/env python3
"""
Hole Card QR Code Generator

This script uses the admin web app API to get course information and the
tournament API to generate QR codes, then creates 5"x7" PDF cards for each hole.
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
from reportlab.lib.utils import ImageReader
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
ADMIN_API_BASE = os.getenv('ADMIN_API_BASE', 'http://localhost:8002')
BASE_API = os.getenv('BASE_API', 'http://localhost:8000')
API_TIMEOUT = 30

# PDF Configuration
CARD_WIDTH = 5 * inch  # 5 inches
CARD_HEIGHT = 7 * inch  # 7 inches
MARGIN = 0.25 * inch

class HoleCardGenerator:
    def __init__(self):
        self.output_dir = Path('holecards')
        self.tournament_api = TOURNAMENT_API_BASE
        self.admin_api = ADMIN_API_BASE
        self.base_api = BASE_API
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

        # Test admin API
        try:
            response = requests.get(f'{self.admin_api}/', timeout=5)
            if response.status_code == 200:
                logger.info(f"Successfully connected to admin API at {self.admin_api}")
            else:
                logger.warning(f"Admin API responded with status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to connect to admin API: {e}")
            logger.error(f"Make sure admin_web_app.py is running at {self.admin_api}")
            sys.exit(1)

    def setup_output_directory(self):
        """Create output directory if it doesn't exist"""
        self.output_dir.mkdir(exist_ok=True)
        logger.info(f"Output directory: {self.output_dir.absolute()}")

    def get_courses_from_admin_api(self):
        """Get list of all courses from admin web app API"""
        try:
            response = requests.get(f'{self.base_api}/courses', timeout=API_TIMEOUT)

            if response.status_code == 200:
                courses_data = response.json()
                logger.info(f"Retrieved {len(courses_data)} courses from admin API")
                return courses_data
            else:
                logger.error(f"Admin API returned status {response.status_code} for courses")
                return []

        except requests.RequestException as e:
            logger.error(f"Error getting courses from admin API: {e}")
            return []

    def get_course_holes_from_admin_api(self, course_name):
        """Get holes for a specific course from admin API"""
        try:
            response = requests.get(
                f'{self.base_api}/courses/{course_name}/holes',
                timeout=API_TIMEOUT
            )

            if response.status_code == 200:
                holes_data = response.json()
                logger.info(f"Retrieved {len(holes_data)} holes for course {course_name}")
                return holes_data
            else:
                logger.warning(f"Admin API returned status {response.status_code} for {course_name} holes")
                return []

        except requests.RequestException as e:
            logger.error(f"Error getting holes for {course_name} from admin API: {e}")
            return []

    def get_all_holes_from_apis(self):
        """Get all holes from all courses using both admin and tournament APIs"""
        all_holes = []

        # Get courses from admin API
        courses = self.get_courses_from_admin_api()
        if not courses:
            logger.error("No courses found from admin API")
            return []

        # Process each course
        for course in courses:
            course_name = course.get('name', course.get('course_name', 'Unknown'))
            logger.info(f"Processing course: {course_name}")

            # Get holes for this course from admin API
            course_holes = self.get_course_holes_from_admin_api(course_name)

            if not course_holes:
                logger.warning(f"No holes found for course {course_name}")
                continue

            # Generate hole cards for each hole
            for hole_info in course_holes:
                hole_number = hole_info.get('number', hole_info.get('hole_number', 1))

                try:
                    # Get QR code and detailed hole data from tournament API
                    qr_buffer, detailed_hole_data = self.generate_qr_code_from_tournament_api(
                        course_name, hole_number
                    )

                    if qr_buffer and detailed_hole_data:
                        # Combine admin API data with tournament API data
                        combined_hole_data = {
                            'course_name': course_name,
                            'hole_number': hole_number,
                            'par': detailed_hole_data.get('par', hole_info.get('par', 4)),
                            'hole_name': detailed_hole_data.get('hole_name', hole_info.get('name', f"Hole {hole_number}")),
                            'qr_code_buffer': qr_buffer
                        }
                        all_holes.append(combined_hole_data)
                        logger.info(f"Successfully processed {course_name} - Hole {hole_number}")
                    else:
                        logger.warning(f"Could not get QR code for {course_name} hole {hole_number}")

                except Exception as e:
                    logger.error(f"Error processing {course_name} hole {hole_number}: {e}")
                    continue

        logger.info(f"Successfully processed {len(all_holes)} holes total")
        return all_holes

    def generate_qr_code_from_tournament_api(self, course_name, hole_number):
        """Get QR code and hole data from tournament API"""
        try:
            # Use the correct endpoint format for the tournament API
            response = requests.post(
                f'{self.tournament_api}/generate-hole-card',  # Note the dash, not underscore
                json={
                    'course_name': course_name,
                    'hole_number': hole_number
                },
                headers={'Content-Type': 'application/json'},
                timeout=API_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()

                if 'qr_code_base64' in data and 'encoded_data' in data:
                    # Decode base64 QR code image
                    qr_image_data = base64.b64decode(data['qr_code_base64'])
                    qr_image_buffer = io.BytesIO(qr_image_data)

                    # Parse hole data from encoded_data
                    hole_info = data['encoded_data']

                    return qr_image_buffer, hole_info
                else:
                    logger.error(f"Tournament API response missing QR code data for {course_name} hole {hole_number}")
                    return None, None
            else:
                logger.error(f"Tournament API error {response.status_code} for {course_name} hole {hole_number}")
                if response.text:
                    logger.error(f"Response: {response.text}")
                return None, None

        except requests.RequestException as e:
            logger.error(f"Network error getting QR code for {course_name} hole {hole_number}: {e}")
            return None, None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding tournament API response for {course_name} hole {hole_number}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error getting QR code for {course_name} hole {hole_number}: {e}")
            return None, None

    def get_specific_courses_holes(self, course_names):
        """Get holes for specific courses only"""
        all_holes = []

        for course_name in course_names:
            logger.info(f"Processing specified course: {course_name}")

            # Get holes for this course from admin API
            course_holes = self.get_course_holes_from_admin_api(course_name)

            if not course_holes:
                logger.warning(f"No holes found for course {course_name}")
                continue

            # Generate hole cards for each hole
            for hole_info in course_holes:
                hole_number = hole_info.get('number', hole_info.get('hole_number', 1))

                try:
                    # Get QR code and detailed hole data from tournament API
                    qr_buffer, detailed_hole_data = self.generate_qr_code_from_tournament_api(
                        course_name, hole_number
                    )

                    if qr_buffer and detailed_hole_data:
                        # Combine admin API data with tournament API data
                        combined_hole_data = {
                            'course_name': course_name,
                            'hole_number': hole_number,
                            'par': detailed_hole_data.get('par', hole_info.get('par', 4)),
                            'hole_name': detailed_hole_data.get('hole_name', hole_info.get('name', f"Hole {hole_number}")),
                            'qr_code_buffer': qr_buffer
                        }
                        all_holes.append(combined_hole_data)
                        logger.info(f"Successfully processed {course_name} - Hole {hole_number}")
                    else:
                        logger.warning(f"Could not get QR code for {course_name} hole {hole_number}")

                except Exception as e:
                    logger.error(f"Error processing {course_name} hole {hole_number}: {e}")
                    continue

        logger.info(f"Successfully processed {len(all_holes)} holes for specified courses")
        return all_holes

    def create_hole_card_pdf(self, hole_data, qr_image_buffer):
        """Create a 5x7 inch PDF card for a hole"""
        try:
            # Create filename
            course_safe = "".join(c for c in hole_data['course_name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"hole_card_{course_safe}_hole_{hole_data['hole_number']:02d}.pdf"
            filepath = self.output_dir / filename

            # Create PDF canvas
            c = canvas.Canvas(str(filepath), pagesize=(CARD_WIDTH, CARD_HEIGHT))

            # Colors
            if hole_data['course_name']=='Black Course':
                primary_color = HexColor('#000000')
            elif hole_data['course_name']=='Red Course':
                primary_color = HexColor('#CC0000')
            else:
                primary_color = HexColor('#2E86AB')  # Blue
            secondary_color = HexColor('#A23B72')  # Purple
            accent_color = HexColor('#666666')  # Orange
            text_color = HexColor('#0B0C10')  # Dark

            # Background
            c.setFillColor(white)
            c.rect(0, 0, CARD_WIDTH, CARD_HEIGHT, fill=1)

            # Header background
            c.setFillColor(primary_color)
            c.rect(0, CARD_HEIGHT - 1.5*inch, CARD_WIDTH, 1.5*inch, fill=1)

            # Course name
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 16)
            course_text = hole_data['course_name']
            text_width = c.stringWidth(course_text, "Helvetica-Bold", 16)
            c.drawString((CARD_WIDTH - text_width) / 2, CARD_HEIGHT - 0.4*inch, course_text)

            # Hole name and number - large display
            c.setFont("Helvetica-Bold", 36)
            hole_text = f"{hole_data['hole_number']} - {hole_data['hole_name']}"
            text_width = c.stringWidth(hole_text, "Helvetica-Bold", 36)
            c.drawString((CARD_WIDTH - text_width) / 2, CARD_HEIGHT - 1.2*inch, hole_text)

            # Par information
            c.setFillColor(accent_color)
            par_y = CARD_HEIGHT - 1.8*inch
            c.rect(MARGIN, par_y - 0.3*inch, CARD_WIDTH - 2*MARGIN, 0.6*inch, fill=1)

            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 24)
            par_text = f"PAR {hole_data['par']}"
            text_width = c.stringWidth(par_text, "Helvetica-Bold", 24)
            c.drawString((CARD_WIDTH - text_width) / 2, par_y - 0.1*inch, par_text)

            # QR Code
            if qr_image_buffer:
                qr_size = 2.2 * inch
                qr_x = (CARD_WIDTH - qr_size) / 2
                qr_y = 0.8 * inch

                # QR code background
                c.setFillColor(white)
                c.rect(qr_x - 0.1*inch, qr_y - 0.1*inch, qr_size + 0.2*inch, qr_size + 0.2*inch, fill=1)
                c.setStrokeColor(primary_color)
                c.setLineWidth(2)
                c.rect(qr_x - 0.1*inch, qr_y - 0.1*inch, qr_size + 0.2*inch, qr_size + 0.2*inch, fill=0)

                image = Image.open(qr_image_buffer)
                # Draw QR code
                c.drawInlineImage(image, qr_x, qr_y, qr_size, qr_size)

                # QR code label
                c.setFillColor(text_color)
                c.setFont("Helvetica", 10)
                label_text = "Scan to load hole information"
                text_width = c.stringWidth(label_text, "Helvetica", 10)
                c.drawString((CARD_WIDTH - text_width) / 2, qr_y - 0.3*inch, label_text)


            # Footer
            c.setFillColor(HexColor('#666666'))
            c.setFont("Helvetica", 8)
            footer_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} via API"
            c.drawString(MARGIN, 0.2*inch, footer_text)

            # Save PDF
            c.save()
            logger.info(f"Created hole card: {filename}")
            return filepath

        except Exception as e:
            logger.error(f"Error creating PDF for hole {hole_data['hole_number']}: {e}")
            return None

    def generate_all_cards(self):
        """Generate hole cards for all holes using both admin and tournament APIs"""
        logger.info("Starting hole card generation using admin and tournament APIs...")

        # Get all holes from all courses
        holes = self.get_all_holes_from_apis()

        if not holes:
            logger.error("No holes found via APIs. Please check:")
            logger.error("1. Admin web app is running and accessible")
            logger.error("2. Tournament API is running and accessible") 
            logger.error("3. Database contains Course and Hole data")
            logger.error("4. API endpoints are working correctly")
            return

        successful = 0
        failed = 0

        for hole_data in holes:
            try:
                logger.info(f"Creating PDF for {hole_data['course_name']} - Hole {hole_data['hole_number']}")

                # Use QR code buffer from hole data
                qr_image_buffer = hole_data.get('qr_code_buffer')

                if not qr_image_buffer:
                    logger.warning(f"No QR code available for {hole_data['course_name']} hole {hole_data['hole_number']}")
                    failed += 1
                    continue

                # Create PDF
                pdf_path = self.create_hole_card_pdf(hole_data, qr_image_buffer)
                if pdf_path:
                    successful += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"Error processing hole {hole_data['hole_number']}: {e}")
                failed += 1

        logger.info(f"Hole card generation complete!")
        logger.info(f"Successfully created: {successful} cards")
        logger.info(f"Failed: {failed} cards")
        logger.info(f"Output directory: {self.output_dir.absolute()}")

    def generate_specific_cards(self, course_names):
        """Generate cards for specific courses only"""
        logger.info(f"Generating cards for specific courses: {', '.join(course_names)}")

        holes = self.get_specific_courses_holes(course_names)

        if not holes:
            logger.error("No holes found for specified courses")
            return

        successful = 0
        failed = 0

        for hole_data in holes:
            try:
                logger.info(f"Creating PDF for {hole_data['course_name']} - Hole {hole_data['hole_number']}")

                # Use QR code buffer from hole data
                qr_image_buffer = hole_data.get('qr_code_buffer')

                if not qr_image_buffer:
                    failed += 1
                    continue

                # Create PDF
                pdf_path = self.create_hole_card_pdf(hole_data, qr_image_buffer)
                if pdf_path:
                    successful += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"Error processing hole {hole_data['hole_number']}: {e}")
                failed += 1

        logger.info(f"Specific hole card generation complete!")
        logger.info(f"Successfully created: {successful} cards")
        logger.info(f"Failed: {failed} cards")

    def list_available_courses(self):
        """List all available courses from admin API"""
        logger.info("Fetching available courses...")

        courses = self.get_courses_from_admin_api()

        if courses:
            logger.info("Available courses:")
            for course in courses:
                course_name = course.get('name', course.get('course_name', 'Unknown'))
                logger.info(f"  - {course_name}")
            return [course.get('name', course.get('course_name', 'Unknown')) for course in courses]
        else:
            logger.info("No courses found")
            return []

    def close(self):
        """Cleanup (no database connection to close)"""
        pass

def main():
    """Main function"""
    try:
        generator = HoleCardGenerator()

        # Check for command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == '--help' or sys.argv[1] == '-h':
                print("Hole Card Generator")
                print("Usage:")
                print("  python generate_hole_cards.py                    # Generate cards for all courses")
                print("  python generate_hole_cards.py --list-courses     # List available courses")
                print("  python generate_hole_cards.py --courses [names]  # Generate cards for specific courses")
                print("  python generate_hole_cards.py --help             # Show this help")
                print()
                print("Examples:")
                print("  python generate_hole_cards.py --courses 'Pebble Beach' 'Augusta National'")
                print()
                print("Configuration:")
                print(f"  Tournament API: {TOURNAMENT_API_BASE}")
                print(f"  Admin API: {ADMIN_API_BASE}")
                print("  Set TOURNAMENT_API_BASE and ADMIN_API_BASE environment variables to change URLs")
                return

            elif sys.argv[1] == '--list-courses':
                # List available courses
                available_courses = generator.list_available_courses()
                if available_courses:
                    print("\nTo generate cards for specific courses, use:")
                    course_list = ' '.join([f"'{course}'" for course in available_courses[:3]])
                    print(f"python generate_hole_cards.py --courses {course_list} ...")
                return

            elif sys.argv[1] == '--courses':
                # Generate cards for specific courses
                if len(sys.argv) < 3:
                    logger.error("Please specify course names after --courses")
                    logger.error("Use --list-courses to see available courses")
                    sys.exit(1)

                course_names = sys.argv[2:]
                logger.info(f"Generating cards for specified courses: {', '.join(course_names)}")
                generator.generate_specific_cards(course_names)

            else:
                logger.error(f"Unknown argument: {sys.argv[1]}")
                logger.error("Use --help for usage information")
                sys.exit(1)
        else:
            # Generate cards for all courses
            generator.generate_all_cards()

        generator.close()

    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
