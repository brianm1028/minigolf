#!/usr/bin/env python3
"""
Tournament Simulator - Simulates 25 teams playing in a tournament
Mimics the behavior of the mobile/index.html app for testing purposes
"""

import threading
import time
import random
import requests
from urllib3.exceptions import InsecureRequestWarning
import json
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import logging

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API endpoints
MAIN_API_BASE = "https://10.0.0.204:8000"
TOURNAMENT_API_BASE = "https://10.0.0.204:8000/tournament"

class TeamSimulator:
    def __init__(self, team_number):
        self.team_number = team_number
        self.tournament_name = "Raiders of the Lost Par"
        self.players = []
        self.active_players = []
        self.course_name = "Red Course" if team_number % 2 == 0 else "Black Course"
        self.starting_hole = int(team_number / 2) + 1
        self.current_hole = self.starting_hole
        self.holes_played = 0

    def run(self):
        """Main execution method for team simulation"""
        try:
            # Step 3: Wait random time and get team players
            wait_time = random.uniform(1, 3)
            time.sleep(wait_time)

            self.get_team_players()

            # Step 4: Randomly remove players (1% chance per player)
            self.remove_random_players()

            # Step 5: Activate team round
            self.activate_team_round()

            # Step 6: Activate player rounds
            self.activate_player_rounds()

            # Step 7: Print starting info
            print(f'Team {self.team_number} Starting Round on {self.course_name} at hole {self.starting_hole}')

            # Steps 8-10: Play all 18 holes
            self.play_round()

            # Step 11: End player rounds
            self.end_player_rounds()

            # Step 12: End team round
            self.end_team_round()

            # Step 13: Print completion
            print(f'Team {self.team_number} round completed')

        except Exception as e:
            logger.error(f'Team {self.team_number} encountered error: {e}')

    def get_team_players(self):
        """Step 3: Get players for the team"""
        try:
            response = requests.get(f'{MAIN_API_BASE}/teams/{self.team_number}/players',verify=False)
            response.raise_for_status()

            players_data = response.json()
            self.players = players_data if isinstance(players_data, list) else []
            self.active_players = self.players.copy()

            logger.info(f'Team {self.team_number}: Retrieved {len(self.players)} players')

        except Exception as e:
            logger.error(f'Team {self.team_number}: Failed to get players - {e}')
            # Create dummy players if API fails
            self.players = [
                {"number": (self.team_number - 1) * 5 + i + 1, "name": f"Player {(self.team_number - 1) * 5 + i + 1}"}
                for i in range(5)
            ]
            self.active_players = self.players.copy()

    def remove_random_players(self):
        """Step 4: Randomly remove players with 1% probability"""
        original_count = len(self.active_players)
        self.active_players = [
            player for player in self.active_players 
            if random.random() > 0.01  # 99% chance to keep player
        ]

        # Ensure at least one player remains
        if not self.active_players and self.players:
            self.active_players = [self.players[0]]

        removed_count = original_count - len(self.active_players)
        if removed_count > 0:
            logger.info(f'Team {self.team_number}: {removed_count} player(s) not playing')

    def activate_team_round(self):
        """Step 5: Activate team round"""
        try:
            payload = {
                "tournament_name": self.tournament_name,
                "team_number": self.team_number
            }

            response = requests.post(
                f'{TOURNAMENT_API_BASE}/activate-team-round',
                json=payload,
                headers={'Content-Type': 'application/json'},verify=False
            )
            response.raise_for_status()

            logger.info(f'Team {self.team_number}: Team round activated')

        except Exception as e:
            logger.error(f'Team {self.team_number}: Failed to activate team round - {e}')
            raise

    def activate_player_rounds(self):
        """Step 6: Activate player rounds"""
        for player in self.active_players:
            try:
                payload = {
                    "tournament_name": self.tournament_name,
                    "team_number": self.team_number,
                    "player_number": player["number"]
                }

                response = requests.post(
                    f'{TOURNAMENT_API_BASE}/activate-player-round',
                    json=payload,
                    headers={'Content-Type': 'application/json'},verify=False
                )
                response.raise_for_status()

            except Exception as e:
                logger.error(f'Team {self.team_number}: Failed to activate round for player {player["number"]} - {e}')
                raise

        logger.info(f'Team {self.team_number}: Activated rounds for {len(self.active_players)} players')

    def generate_score(self):
        """Step 8: Generate random score using normal distribution centered at 3"""
        # Normal distribution centered at 3 with standard deviation of 1
        score = np.random.normal(3, 1)
        # Clamp to valid range 1-6
        score = max(1, min(6, round(score)))
        return int(score)

    def record_scores_for_hole(self, hole_number):
        """Steps 8-9: Generate and record scores for current hole"""
        # Step 8: Calculate random scores
        hole_scores = {}
        for player in self.active_players:
            hole_scores[player["number"]] = self.generate_score()

        # Step 9: Wait random time then record scores
        wait_time = random.uniform(5, 15)
        time.sleep(wait_time)

        for player in self.active_players:
            try:
                payload = {
                    "player_number": player["number"],
                    "course_name": self.course_name,
                    "hole_number": hole_number,
                    "score": hole_scores[player["number"]]
                }

                response = requests.post(
                    f'{TOURNAMENT_API_BASE}/record-score',
                    json=payload,
                    headers={'Content-Type': 'application/json'},verify=False
                )
                response.raise_for_status()

            except Exception as e:
                logger.error(f'Team {self.team_number}: Failed to record score for player {player["number"]} on hole {hole_number} - {e}')
                raise

        logger.info(f'Team {self.team_number}: Recorded scores for hole {hole_number}')

    def get_next_hole(self):
        """Calculate next hole in shotgun format"""
        next_hole = self.current_hole + 1
        if next_hole > 18:
            next_hole = 1
        return next_hole

    def play_round(self):
        """Step 10: Play all 18 holes in shotgun format"""
        holes_to_play = []
        current = self.starting_hole

        # Build list of holes in shotgun order
        for i in range(18):
            holes_to_play.append(current)
            current += 1
            if current > 18:
                current = 1

        # Play each hole
        for hole_number in holes_to_play:
            self.record_scores_for_hole(hole_number)
            self.holes_played += 1

    def end_player_rounds(self):
        """Step 11: End all player rounds"""
        for player in self.active_players:
            try:
                # Random delay between player round endings
                wait_time = random.uniform(3, 5)
                time.sleep(wait_time)

                payload = {
                    "tournament_name": self.tournament_name,
                    "player_number": player["number"]
                }

                response = requests.post(
                    f'{TOURNAMENT_API_BASE}/end-player-round',
                    json=payload,
                    headers={'Content-Type': 'application/json'},verify=False
                )
                response.raise_for_status()

            except Exception as e:
                logger.error(f'Team {self.team_number}: Failed to end round for player {player["number"]} - {e}')
                raise

        logger.info(f'Team {self.team_number}: Ended rounds for all players')

    def end_team_round(self):
        """Step 12: End team round"""
        try:
            payload = {
                "tournament_name": self.tournament_name,
                "team_number": self.team_number
            }

            response = requests.post(
                f'{TOURNAMENT_API_BASE}/end-team-round',
                json=payload,
                headers={'Content-Type': 'application/json'},verify=False
            )
            response.raise_for_status()

            logger.info(f'Team {self.team_number}: Team round ended')

        except Exception as e:
            logger.error(f'Team {self.team_number}: Failed to end team round - {e}')
            raise


def start_tournament():
    """Step 1: Start the tournament"""
    try:
        payload = {"tournament_name": "Raiders of the Lost Par"}

        response = requests.post(
            f'{TOURNAMENT_API_BASE}/start-tournament',
            json=payload,
            headers={'Content-Type': 'application/json'},verify=False
        )
        response.raise_for_status()

        logger.info('Tournament "Raiders of the Lost Par" started successfully')
        return True

    except Exception as e:
        logger.error(f'Failed to start tournament: {e}')
        return False


def simulate_tournament():
    """Main simulation function"""
    print("="*60)
    print("TOURNAMENT SIMULATOR STARTING")
    print("Simulating 25 teams in 'Raiders of the Lost Par'")
    print("="*60)

    # Step 1: Start tournament
    if not start_tournament():
        print("Failed to start tournament. Exiting.")
        return

    # Step 2: Create and start 25 team threads
    team_simulators = [TeamSimulator(team_num) for team_num in range(1, 26)]

    # Use ThreadPoolExecutor to manage all team threads
    with ThreadPoolExecutor(max_workers=25) as executor:
        # Submit all team simulations
        futures = [executor.submit(simulator.run) for simulator in team_simulators]

        # Wait for all teams to complete
        for future in futures:
            try:
                future.result()  # This will raise any exceptions that occurred
            except Exception as e:
                logger.error(f'Team simulation failed: {e}')

    # Step 14: All threads ended, program exits
    print("="*60)
    print("ALL TEAMS COMPLETED - TOURNAMENT SIMULATION FINISHED")
    print("="*60)


if __name__ == "__main__":
    try:
        simulate_tournament()
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
    except Exception as e:
        logger.error(f'Simulation failed: {e}')
        print(f"Simulation failed: {e}")
