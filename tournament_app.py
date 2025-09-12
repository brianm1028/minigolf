from fastapi import FastAPI, HTTPException, Response
from neo4j import GraphDatabase
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
from contextlib import contextmanager
import qrcode
import io
import base64
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Minigolf Tournament Application API", version="1.0.0")

# Neo4j connection settings
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "minigolf"
NEO4J_DATABASE = "minigolf"

# Neo4j driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

@contextmanager
def get_db_session():
    """Context manager for Neo4j database sessions"""
    session = driver.session(database=NEO4J_DATABASE)
    try:
        yield session
    finally:
        session.close()

# Pydantic Models
class RecordScoreRequest(BaseModel):
    player_number: int
    course_name: str
    hole_number: int
    score: int

class TeamLeaderboardEntry(BaseModel):
    team_name: str
    total: int
    average: float
    rank: int
    holes_played: int

class PlayerLeaderboardEntry(BaseModel):
    player_name: str
    total: int
    average: float
    rank: int
    holes_played: int

class LeaderboardResponse(BaseModel):
    message: str
    updated_player_rounds: int
    updated_team_rounds: int

class EndPlayerRoundRequest(BaseModel):
    player_number: int
    tournament_name: str

class EndTeamRoundRequest(BaseModel):
    team_number: int
    tournament_name: str

class EndRoundResponse(BaseModel):
    message: str
    total: int
    average: float
    holes_played: int

class EndTournamentRequest(BaseModel):
    tournament_name: str

class StartTournamentRequest(BaseModel):
    tournament_name: str

class ActivateTeamRoundRequest(BaseModel):
    tournament_name: str
    team_number: int

class ActivatePlayerRoundRequest(BaseModel):
    tournament_name: str
    team_number: int
    player_number: int

class TournamentManagementResponse(BaseModel):
    message: str
    affected_count: int

class GenerateTeamCardRequest(BaseModel):
    team_number: int

class GenerateHoleCardRequest(BaseModel):
    course_name: str
    hole_number: int

class QRCodeResponse(BaseModel):
    message: str
    qr_code_base64: str
    encoded_data: Dict[str, Any]

# Application Layer Endpoints

@app.post("/update-leaderboard", response_model=LeaderboardResponse)
async def update_leaderboard():
    """
    Calculates the total and average scores for each PlayerRound and TeamRound 
    based on the scores of the PLAYED_HOLE relationships. 
    Calculates the player and team ranks by comparing the total scores.
    """
    try:
        with get_db_session() as session:
            # Update PlayerRound totals and averages
            player_update_query = """
            MATCH (pr:PlayerRound)-[ph:PLAYED_HOLE]->(h:Hole)
            WHERE pr.active = true
            WITH pr, collect(ph.score) as scores
            SET pr.total = reduce(sum = 0, score IN scores | sum + score),
                pr.average = reduce(sum = 0, score IN scores | sum + score) * 1.0 / size(scores)
            RETURN count(pr) as updated_players
            """
            player_result = session.run(player_update_query)
            updated_players = player_result.single()["updated_players"]

            # Update PlayerRound ranks
            player_rank_query = """
            MATCH (pr:PlayerRound)
            WHERE pr.active = true AND pr.total IS NOT NULL
            WITH pr ORDER BY pr.total ASC
            WITH collect(pr) as player_rounds
            UNWIND range(0, size(player_rounds)-1) as i
            WITH player_rounds[i] as pr, i+1 as rank
            SET pr.rank = rank
            """
            session.run(player_rank_query)

            # Update TeamRound totals and averages based on PlayerRounds
            team_update_query = """
            MATCH (t:Team)-[:PLAYED_ROUND]->(tr:TeamRound)
            WHERE tr.active = true
            MATCH (p:Player)-[:MEMBER_OF]->(t)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)
            WHERE pr.active = true AND pr.total IS NOT NULL
            MATCH (pr)-[:PLAYED_ROUND]->(tr)
            WITH tr, collect(pr.total) as player_totals
            SET tr.total = reduce(sum = 0, total IN player_totals | sum + total),
                tr.average = reduce(sum = 0, total IN player_totals | sum + total) * 1.0 / size(player_totals)
            RETURN count(tr) as updated_teams
            """
            team_result = session.run(team_update_query)
            updated_teams = team_result.single()["updated_teams"]

            # Update TeamRound ranks
            team_rank_query = """
            MATCH (tr:TeamRound)
            WHERE tr.active = true AND tr.total IS NOT NULL
            WITH tr ORDER BY tr.total ASC
            WITH collect(tr) as team_rounds
            UNWIND range(0, size(team_rounds)-1) as i
            WITH team_rounds[i] as tr, i+1 as rank
            SET tr.rank = rank
            """
            session.run(team_rank_query)

            return LeaderboardResponse(
                message="Leaderboard updated successfully",
                updated_player_rounds=updated_players,
                updated_team_rounds=updated_teams
            )

    except Exception as e:
        logger.error(f"Error updating leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/record-score")
async def record_score(request: RecordScoreRequest):
    """
    Takes a player number, course name, hole number, and score as input.
    Identifies the active PlayerRound for the given player, course, and hole
    and creates or updates the PLAYED_HOLE relationship.
    """
    try:
        with get_db_session() as session:
            # Find the hole
            hole_query = """
            MATCH (c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole {number: $hole_number})
            RETURN elementId(h) as hole_id
            """
            hole_result = session.run(hole_query, 
                                    course_name=request.course_name, 
                                    hole_number=request.hole_number)
            hole_record = hole_result.single()
            if not hole_record:
                raise HTTPException(status_code=404, detail="Hole not found for the specified course")

            hole_id = hole_record["hole_id"]

            # Find the active PlayerRound for the player
            player_round_query = """
            MATCH (p:Player {number: $player_number})-[:PLAYED_ROUND]->(pr:PlayerRound)
            WHERE pr.active = true
            MATCH (pr)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t:Tournament)
            WHERE t.active = true
            MATCH (t)-[:USES]->(c:Course {name: $course_name})
            RETURN elementId(pr) as player_round_id
            """
            pr_result = session.run(player_round_query, 
                                  player_number=request.player_number,
                                  course_name=request.course_name)
            pr_record = pr_result.single()
            if not pr_record:
                raise HTTPException(status_code=404, detail="Active PlayerRound not found for the specified player and course")

            player_round_id = pr_record["player_round_id"]

            # Check if PLAYED_HOLE relationship already exists and update or create
            upsert_query = """
            MATCH (pr:PlayerRound) WHERE elementId(pr) = $player_round_id
            MATCH (h:Hole) WHERE elementId(h) = $hole_id
            MERGE (pr)-[ph:PLAYED_HOLE]->(h)
            SET ph.score = $score
            RETURN ph.score as recorded_score
            """
            upsert_result = session.run(upsert_query,
                                      player_round_id=player_round_id,
                                      hole_id=hole_id,
                                      score=request.score)

            recorded_score = upsert_result.single()["recorded_score"]

            return {
                "message": "Score recorded successfully",
                "player_number": request.player_number,
                "course_name": request.course_name,
                "hole_number": request.hole_number,
                "score": recorded_score
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording score: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/team-leaderboard/{tournament_name}", response_model=List[TeamLeaderboardEntry])
async def get_team_leaderboard(tournament_name: str):
    """
    Given a Tournament name, returns the Team name, total, average, and rank values
    and the number of holes played for the active TeamRound in that Tournament,
    ordered by rank descending.
    """
    try:
        with get_db_session() as session:
            query = """
            MATCH (t:Tournament {name: $tournament_name, active: true})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound {active: true})
            MATCH (tr)-[:IN_TOURNAMENT]->(t)
            OPTIONAL MATCH (p:Player)-[:MEMBER_OF]->(team)
            OPTIONAL MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound {active: true})
            OPTIONAL MATCH (pr)-[:PLAYED_ROUND]->(tr)
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            WITH team, tr, count(DISTINCT h) as holes_played
            WHERE tr.total IS NOT NULL AND tr.average IS NOT NULL AND tr.rank IS NOT NULL
            RETURN team.name as team_name, 
                   tr.total as total, 
                   tr.average as average, 
                   tr.rank as rank,
                   holes_played
            ORDER BY tr.rank DESC
            """

            result = session.run(query, tournament_name=tournament_name)

            leaderboard = []
            for record in result:
                leaderboard.append(TeamLeaderboardEntry(
                    team_name=record["team_name"],
                    total=record["total"],
                    average=record["average"],
                    rank=record["rank"],
                    holes_played=record["holes_played"]
                ))

            return leaderboard

    except Exception as e:
        logger.error(f"Error getting team leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/player-leaderboard/{tournament_name}", response_model=List[PlayerLeaderboardEntry])
async def get_player_leaderboard(tournament_name: str):
    """
    Given a Tournament name, returns the Player name, total, average, and rank values
    and the number of holes played for the active PlayerRound in that Tournament,
    ordered by rank descending.
    """
    try:
        with get_db_session() as session:
            query = """
            MATCH (t:Tournament {name: $tournament_name, active: true})-[:HAS_TEAM]->(team:Team)
            MATCH (p:Player)-[:MEMBER_OF]->(team)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound {active: true})
            MATCH (pr)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            WITH p, pr, count(h) as holes_played
            WHERE pr.total IS NOT NULL AND pr.average IS NOT NULL AND pr.rank IS NOT NULL
            RETURN p.name as player_name,
                   pr.total as total,
                   pr.average as average,
                   pr.rank as rank,
                   holes_played
            ORDER BY pr.rank DESC
            """

            result = session.run(query, tournament_name=tournament_name)

            leaderboard = []
            for record in result:
                leaderboard.append(PlayerLeaderboardEntry(
                    player_name=record["player_name"],
                    total=record["total"],
                    average=record["average"],
                    rank=record["rank"],
                    holes_played=record["holes_played"]
                ))

            return leaderboard

    except Exception as e:
        logger.error(f"Error getting player leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/end-player-round", response_model=EndRoundResponse)
async def end_player_round(request: EndPlayerRoundRequest):
    """
    Marks a PlayerRound as inactive and runs a final calculation 
    of the player's total and average scores.
    """
    try:
        with get_db_session() as session:
            # Find and validate the active PlayerRound
            find_query = """
            MATCH (p:Player {number: $player_number})-[:PLAYED_ROUND]->(pr:PlayerRound {active: true})
            MATCH (pr)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t:Tournament {name: $tournament_name})
            RETURN elementId(pr) as player_round_id, pr.total as current_total, pr.average as current_average
            """

            find_result = session.run(find_query, 
                                    player_number=request.player_number,
                                    tournament_name=request.tournament_name)
            find_record = find_result.single()

            if not find_record:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Active PlayerRound not found for player {request.player_number} in tournament {request.tournament_name}"
                )

            player_round_id = find_record["player_round_id"]

            # Calculate final scores and mark as inactive
            final_calc_query = """
            MATCH (pr:PlayerRound) WHERE elementId(pr) = $player_round_id
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            WITH pr, collect(ph.score) as scores
            SET pr.active = false, pr.completed = true,
                pr.total = CASE 
                    WHEN size(scores) > 0 THEN reduce(sum = 0, score IN scores | sum + score)
                    ELSE 0
                END,
                pr.average = CASE 
                    WHEN size(scores) > 0 THEN reduce(sum = 0, score IN scores | sum + score) * 1.0 / size(scores)
                    ELSE 0.0
                END
            RETURN pr.total as total, pr.average as average, size(scores) as holes_played
            """

            calc_result = session.run(final_calc_query, player_round_id=player_round_id)
            calc_record = calc_result.single()

            return EndRoundResponse(
                message=f"Player round ended successfully for player {request.player_number}",
                total=calc_record["total"],
                average=calc_record["average"],
                holes_played=calc_record["holes_played"]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/end-team-round", response_model=EndRoundResponse)
async def end_team_round(request: EndTeamRoundRequest):
    """
    Marks a TeamRound as inactive and runs a final calculation 
    of the team's total and average scores.
    """
    try:
        with get_db_session() as session:
            # Find and validate the active TeamRound
            find_query = """
            MATCH (team:Team {number: $team_number})-[:PLAYED_ROUND]->(tr:TeamRound {active: true})
            MATCH (tr)-[:IN_TOURNAMENT]->(t:Tournament {name: $tournament_name})
            RETURN elementId(tr) as team_round_id, tr.total as current_total, tr.average as current_average
            """

            find_result = session.run(find_query,
                                    team_number=request.team_number,
                                    tournament_name=request.tournament_name)
            find_record = find_result.single()

            if not find_record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Active TeamRound not found for team {request.team_number} in tournament {request.tournament_name}"
                )

            team_round_id = find_record["team_round_id"]

            # Calculate final scores based on associated PlayerRounds and mark as inactive
            final_calc_query = """
            MATCH (tr:TeamRound) WHERE elementId(tr) = $team_round_id
            MATCH (team:Team)-[:PLAYED_ROUND]->(tr)
            OPTIONAL MATCH (p:Player)-[:MEMBER_OF]->(team)
            OPTIONAL MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)
            OPTIONAL MATCH (pr)-[:PLAYED_ROUND]->(tr)
            OPTIONAL MATCH (pr)-[ph:PLAYED_HOLE]->(h:Hole)
            WITH tr, pr, collect(ph.score) as player_scores
            WITH tr, collect(CASE 
                WHEN size(player_scores) > 0 
                THEN reduce(sum = 0, score IN player_scores | sum + score)
                ELSE 0
            END) as player_totals
            WITH tr, player_totals, 
                 reduce(holes = 0, pt IN player_totals | 
                    CASE WHEN pt > 0 THEN holes + (pt / 3) ELSE holes END) as total_holes
            SET tr.active = false, tr.completed = true,
                tr.total = reduce(sum = 0, total IN player_totals | sum + total),
                tr.average = CASE 
                    WHEN size(player_totals) > 0 AND reduce(sum = 0, total IN player_totals | sum + total) > 0
                    THEN reduce(sum = 0, total IN player_totals | sum + total) * 1.0 / size(player_totals)
                    ELSE 0.0
                END
            RETURN tr.total as total, tr.average as average, size(player_totals) as holes_played
            """

            calc_result = session.run(final_calc_query, team_round_id=team_round_id)
            calc_record = calc_result.single()

            return EndRoundResponse(
                message=f"Team round ended successfully for team {request.team_number}",
                total=calc_record["total"],
                average=calc_record["average"], 
                holes_played=calc_record["holes_played"]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/activate-player-round", response_model=TournamentManagementResponse)
async def activate_player_round(request: ActivatePlayerRoundRequest):
    """
    Given a Tournament name, Team, and Player, updates all PlayerRounds related 
    to that team round as active and resets their total, average, and rank values to 0.
    """
    try:
        with get_db_session() as session:
            # Find and activate PlayerRounds for the specific player in the team/tournament
            activate_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team {number: $team_number})
            MATCH (p:Player {number: $player_number})-[:MEMBER_OF]->(team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            SET pr.active = true,
                pr.total = 0,
                pr.average = 0.0,
                pr.rank = 0
            RETURN count(pr) as activated_count
            """

            result = session.run(activate_query,
                               tournament_name=request.tournament_name,
                               team_number=request.team_number,
                               player_number=request.player_number)

            activated_count = result.single()["activated_count"]

            if activated_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No PlayerRounds found for player {request.player_number} in team {request.team_number} for tournament {request.tournament_name}"
                )

            return TournamentManagementResponse(
                message=f"Activated {activated_count} PlayerRound(s) for player {request.player_number}",
                affected_count=activated_count
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating player round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/activate-team-round", response_model=TournamentManagementResponse)
async def activate_team_round(request: ActivateTeamRoundRequest):
    """
    Given a tournament name and team name, marks a TeamRound as active and resets 
    the total, average, and rank values to 0, then calls activate_player_round 
    for all PlayerRounds connected to it.
    """
    try:
        with get_db_session() as session:
            # Activate the TeamRound
            activate_team_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team {number: $team_number})
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            SET tr.active = true,
                tr.total = 0,
                tr.average = 0.0,
                tr.rank = 0
            RETURN count(tr) as activated_teams
            """

            team_result = session.run(activate_team_query,
                                    tournament_name=request.tournament_name,
                                    team_number=request.team_number)

            activated_teams = team_result.single()["activated_teams"]

            if activated_teams == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"No TeamRound found for team {request.team_number} in tournament {request.tournament_name}"
                )

            return TournamentManagementResponse(
                message=f"Activated TeamRound for {request.team_number}",
                affected_count=activated_teams
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating team round: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/start-tournament", response_model=TournamentManagementResponse)
async def start_tournament(request: StartTournamentRequest):
    """
    Given a tournament name, calls activate_team_round for all Teams in the Tournament.
    """
    try:
        with get_db_session() as session:
            # Activate all TeamRounds and their associated PlayerRounds
            activate_all_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            SET tr.active = true,
                tr.total = 0,
                tr.average = 0.0,
                tr.rank = 0
            WITH count(tr) as activated_teams
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p:Player)-[:MEMBER_OF]->(team)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            SET pr.active = true,
                pr.total = 0,
                pr.average = 0.0,
                pr.rank = 0
            RETURN activated_teams, count(pr) as activated_players
            """

            result = session.run(activate_all_query, tournament_name=request.tournament_name)
            record = result.single()

            if not record or (record["activated_teams"] == 0 and record["activated_players"] == 0):
                raise HTTPException(
                    status_code=404,
                    detail=f"No teams or players found for tournament {request.tournament_name}"
                )

            activated_teams = record["activated_teams"]
            activated_players = record["activated_players"]
            total_affected = activated_teams + activated_players

            return TournamentManagementResponse(
                message=f"Tournament {request.tournament_name} started with {activated_teams} teams and {activated_players} player rounds activated",
                affected_count=total_affected
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/end-tournament", response_model=TournamentManagementResponse)
async def end_tournament(request: EndTournamentRequest):
    """
    Given a tournament name, marks all PlayerRounds and TeamRounds in the tournament 
    as inactive and calls update_leaderboard to finalize scores and rankings.
    """
    try:
        with get_db_session() as session:
            # Deactivate all PlayerRounds and TeamRounds in the tournament
            deactivate_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            SET tr.active = false
            WITH count(tr) as deactivated_teams
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p:Player)-[:MEMBER_OF]->(team)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            SET pr.active = false
            RETURN deactivated_teams, count(pr) as deactivated_players
            """

            result = session.run(deactivate_query, tournament_name=request.tournament_name)
            record = result.single()

            if not record or (record["deactivated_teams"] == 0 and record["deactivated_players"] == 0):
                raise HTTPException(
                    status_code=404,
                    detail=f"No active rounds found for tournament {request.tournament_name}"
                )

            deactivated_teams = record["deactivated_teams"]
            deactivated_players = record["deactivated_players"]

            # Call update_leaderboard to finalize scores and rankings
            # We need to temporarily reactivate rounds for the final calculation
            temp_activate_query = """
            MATCH (t:Tournament {name: $tournament_name})-[:HAS_TEAM]->(team:Team)
            MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)-[:IN_TOURNAMENT]->(t)
            MATCH (p:Player)-[:MEMBER_OF]->(team)
            MATCH (p)-[:PLAYED_ROUND]->(pr:PlayerRound)-[:PLAYED_ROUND]->(tr)
            SET pr.active = true, tr.active = true
            """
            session.run(temp_activate_query, tournament_name=request.tournament_name)

            # Perform final leaderboard calculation
            await update_leaderboard()

            # Set them back to inactive
            session.run(deactivate_query, tournament_name=request.tournament_name)

            total_affected = deactivated_teams + deactivated_players

            return TournamentManagementResponse(
                message=f"Tournament {request.tournament_name} ended with final leaderboard calculated. Deactivated {deactivated_teams} teams and {deactivated_players} player rounds",
                affected_count=total_affected
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending tournament: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-team-card", response_model=QRCodeResponse)
async def generate_team_card(request: GenerateTeamCardRequest):
    """
    Takes a team name and generates a QR code with the team information encoded into it.
    """
    try:
        with get_db_session() as session:
            # Get team information including players
            team_query = """
            MATCH (team:Team {number: $team_number})
            OPTIONAL MATCH (p:Player)-[:MEMBER_OF]->(team)
            OPTIONAL MATCH (team)-[:PLAYED_ROUND]->(tr:TeamRound)
            OPTIONAL MATCH (tr)-[:IN_TOURNAMENT]->(t:Tournament)
            WITH team, collect(DISTINCT {
                name: p.name,
                number: p.number,
                email: p.email
            }) as players, collect(DISTINCT {
                tournament_name: t.name,
                team_round_active: tr.active,
                total: tr.total,
                average: tr.average,
                rank: tr.rank
            }) as tournaments
            RETURN team.name as team_name,
                   team.number as team_number,
                   players,
                   tournaments
            """

            result = session.run(team_query, team_number=request.team_number)
            record = result.single()

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Team {request.team_number} not found"
                )

            # Prepare team data for QR code
            team_data = {
                "type": "team_card",
                "team_name": record["team_name"],
                "team_number": record["team_number"],
                "players": [p for p in record["players"] if p["name"] is not None],
                "tournaments": [t for t in record["tournaments"] if t["tournament_name"] is not None],
                "generated_at": "2025-08-23T00:00:00Z"
            }

            # Generate QR code
            qr_data = json.dumps(team_data)
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            # Create QR code image
            qr_image = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            img_buffer = io.BytesIO()
            qr_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            qr_base64 = base64.b64encode(img_buffer.getvalue()).decode()

            return QRCodeResponse(
                message=f"QR code generated successfully for team {request.team_number}",
                qr_code_base64=qr_base64,
                encoded_data=team_data
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating team card: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-hole-card", response_model=QRCodeResponse)
async def generate_hole_card(request: GenerateHoleCardRequest):
    """
    Takes a course name and hole number and generates a QR code with the course and hole information encoded into it.
    """
    try:
        with get_db_session() as session:
            # Get hole and course information
            hole_query = """
            MATCH (c:Course {name: $course_name})-[:HAS_HOLE]->(h:Hole {number: $hole_number})
            OPTIONAL MATCH (l:Location)-[:HAS_COURSE]->(c)
            OPTIONAL MATCH (t:Tournament)-[:USES]->(c)
            WITH c, h, l, collect(DISTINCT {
                tournament_name: t.name,
                tournament_active: t.active
            }) as tournaments
            RETURN c.name as course_name,
                   c.par as course_par,
                   h.name as hole_name,
                   h.number as hole_number,
                   h.par as hole_par,
                   l.name as location_name,
                   tournaments
            """

            result = session.run(hole_query, 
                               course_name=request.course_name,
                               hole_number=request.hole_number)
            record = result.single()

            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Hole {request.hole_number} not found on course {request.course_name}"
                )

            # Prepare hole data for QR code
            hole_data = {
                "type": "hole_card",
                "course_name": record["course_name"],
                "course_par": record["course_par"],
                "hole_name": record["hole_name"],
                "hole_number": record["hole_number"],
                "hole_par": record["hole_par"],
                "location_name": record["location_name"],
                "tournaments": [t for t in record["tournaments"] if t["tournament_name"] is not None],
                "generated_at": "2025-08-23T00:00:00Z"
            }

            # Generate QR code
            qr_data = json.dumps(hole_data)
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            # Create QR code image
            qr_image = qr.make_image(fill_color="black", back_color="white")

            # Convert to base64
            img_buffer = io.BytesIO()
            qr_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            qr_base64 = base64.b64encode(img_buffer.getvalue()).decode()

            return QRCodeResponse(
                message=f"QR code generated successfully for hole {request.hole_number} on {request.course_name}",
                qr_code_base64=qr_base64,
                encoded_data=hole_data
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating hole card: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    try:
        with get_db_session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            if record and record['test'] == 1:
                return {"status": "healthy", "database": "connected"}
            else:
                return {"status": "unhealthy", "database": "connection_failed"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "database": "connection_failed", "error": str(e)}

# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown():
    driver.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
